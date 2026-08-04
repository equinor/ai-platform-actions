"""
Azure Resource Manager access for AzureML assets.

Every versioned AzureML asset is two ARM resources: a container at
`.../{collection}/{name}` and its versions at `.../{collection}/{name}/versions/{version}`.
The SDK hides that split, which makes an archived container with active versions
invisible and unfixable. This module exposes both layers directly.
"""

import datetime
import re
import time
import urllib.parse
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import requests
from azure.identity import DefaultAzureCredential

ARM_BASE_URL = "https://management.azure.com"
ARM_SCOPE = "https://management.azure.com/.default"
ML_PROVIDER = "Microsoft.MachineLearningServices"

# The currently last API VERSION to have the necessary results
REST_API_VERSION = "2025-10-01-preview"

REQUEST_TIMEOUT_SECONDS = 30
# Buffer time in seconds before token expiry to trigger refresh
TOKEN_REFRESH_BUFFER_SECONDS = 5 * 60

ASSET_COLLECTIONS = {
    "data": "data",
    "environment": "environments",
    "component": "components",
    "model": "models",
}

LIST_VIEW_ACTIVE = "ActiveOnly"
LIST_VIEW_ALL = "All"

_RESOURCE_GROUP_PATTERN = re.compile(r"/resourceGroups/([^/]+)/", re.IGNORECASE)
_FRACTIONAL_SECONDS_PATTERN = re.compile(r"\.(\d{1,})")

Transport = Callable[[str, str, dict[str, str], Optional[dict]], tuple[int, Optional[dict]]]


class ArmError(RuntimeError):
    """Azure Resource Manager returned an error response."""


class TokenManager:
    """
    Manages access tokens for Azure REST API calls with automatic refresh.

    When a static token is provided (from GitHub Actions), it will be used directly.
    When using DefaultAzureCredential, tokens are refreshed automatically before expiry.
    """

    def __init__(self, token: Optional[str] = None, expires_on: Optional[int] = None):
        self._static_token = token
        self._static_expires_on = expires_on
        self._credential: Optional[DefaultAzureCredential] = None
        self._cached_token: Optional[str] = None
        self._cached_expires_on: Optional[int] = None

        if not (token and expires_on):
            self._credential = DefaultAzureCredential()

    def get_token(self) -> str:
        """Get a valid access token, refreshing if necessary."""
        if self._static_token and self._static_expires_on:
            current_time = int(time.time())
            if current_time >= self._static_expires_on - TOKEN_REFRESH_BUFFER_SECONDS:
                print("[TokenManager] Warning: Static token is expiring soon or has expired. Cannot refresh static tokens.")
            return self._static_token

        if self._credential:
            current_time = int(time.time())

            if (self._cached_token is None or
                self._cached_expires_on is None or
                current_time >= self._cached_expires_on - TOKEN_REFRESH_BUFFER_SECONDS):

                print("[TokenManager] Refreshing access token...")
                token_response = self._credential.get_token(ARM_SCOPE)
                self._cached_token = token_response.token
                self._cached_expires_on = token_response.expires_on
                print(f"[TokenManager] Token refreshed, valid until {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self._cached_expires_on))}")

            return self._cached_token or ""

        raise RuntimeError("No credential available to get access token")


def _get_rest_api_base_url(
    subscription_id: str,
    resource_group: str,
    workspace_name: str,
) -> str:
    """Build the base URL for Azure ML REST API."""
    return (
        f"{ARM_BASE_URL}/subscriptions/{subscription_id}"
        f"/resourceGroups/{resource_group}"
        f"/providers/{ML_PROVIDER}/workspaces/{workspace_name}"
    )


def _call_rest_api(
    url: str,
    access_token: str,
) -> Optional[dict]:
    """Call Azure REST API and return the JSON response."""
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    try:
        response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as exc:
        print(f"[REST API] HTTP error: {exc}")
        return None
    except requests.exceptions.RequestException as exc:
        print(f"[REST API] Request error: {exc}")
        return None


def _requests_transport(
    method: str,
    url: str,
    headers: dict[str, str],
    body: Optional[dict],
) -> tuple[int, Optional[dict]]:
    response = requests.request(
        method,
        url,
        headers=headers,
        json=body,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    if not response.content:
        return response.status_code, None
    try:
        return response.status_code, response.json()
    except ValueError:
        return response.status_code, None


def _parse_timestamp(value: Any) -> Optional[datetime.datetime]:
    if not isinstance(value, str) or not value:
        return None
    # ARM emits up to 7 fractional digits; fromisoformat accepts at most 6.
    normalised = _FRACTIONAL_SECONDS_PATTERN.sub(lambda m: "." + m.group(1)[:6], value)
    try:
        parsed = datetime.datetime.fromisoformat(normalised)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    return parsed


def _error_message(payload: Optional[dict]) -> str:
    if not isinstance(payload, dict):
        return "no error body"
    error = payload.get("error")
    if isinstance(error, dict):
        return f"{error.get('code', 'Unknown')}: {error.get('message', '')}".strip()
    return str(payload)[:500]


@dataclass(frozen=True)
class AssetVersion:
    """One `.../{collection}/{name}/versions/{version}` resource."""
    name: str
    version: str
    id: str = ""
    tags: dict[str, Any] = field(default_factory=dict)
    properties: dict[str, Any] = field(default_factory=dict)
    created_at: Optional[datetime.datetime] = None
    is_archived: bool = False


@dataclass(frozen=True)
class AssetContainer:
    """One `.../{collection}/{name}` resource."""
    name: str
    id: str = ""
    latest_version: Optional[str] = None
    is_archived: bool = False
    tags: dict[str, Any] = field(default_factory=dict)
    body: dict[str, Any] = field(default_factory=dict)


class AssetClient:
    """
    Reads AzureML asset containers and versions over the ARM REST API.

    Build it with `for_workspace` or `for_registry` rather than directly.
    """

    def __init__(
        self,
        base_url: str,
        token_manager: TokenManager,
        scope_label: str,
        is_registry: bool = False,
        transport: Transport = _requests_transport,
    ):
        self._base_url = base_url
        self._token_manager = token_manager
        self._scope_label = scope_label
        self._is_registry = is_registry
        self._transport = transport

    @property
    def is_registry(self) -> bool:
        return self._is_registry

    @property
    def scope_label(self) -> str:
        return self._scope_label

    @classmethod
    def for_workspace(
        cls,
        subscription_id: str,
        resource_group: str,
        workspace_name: str,
        token: Optional[str] = None,
        expires_on: Optional[int] = None,
        transport: Transport = _requests_transport,
    ) -> "AssetClient":
        return cls(
            base_url=_get_rest_api_base_url(subscription_id, resource_group, workspace_name),
            token_manager=TokenManager(token, expires_on),
            scope_label=f"workspace '{workspace_name}'",
            is_registry=False,
            transport=transport,
        )

    @classmethod
    def for_registry(
        cls,
        registry_name: str,
        subscription_id: str,
        token: Optional[str] = None,
        expires_on: Optional[int] = None,
        transport: Transport = _requests_transport,
    ) -> "AssetClient":
        """
        ARM paths need the registry's resource group, which MLClient never had to know,
        so it is resolved by listing the registries in the workspace's subscription.
        """
        token_manager = TokenManager(token, expires_on)
        resource_group = _resolve_registry_resource_group(
            registry_name=registry_name,
            subscription_id=subscription_id,
            token_manager=token_manager,
            transport=transport,
        )
        base_url = (
            f"{ARM_BASE_URL}/subscriptions/{subscription_id}"
            f"/resourceGroups/{resource_group}"
            f"/providers/{ML_PROVIDER}/registries/{registry_name}"
        )
        return cls(
            base_url=base_url,
            token_manager=token_manager,
            scope_label=f"registry '{registry_name}'",
            is_registry=True,
            transport=transport,
        )

    def _url(self, path: str, **query: Any) -> str:
        query.setdefault("api-version", REST_API_VERSION)
        params = {k: v for k, v in query.items() if v is not None}
        return f"{self._base_url}/{path}?{urllib.parse.urlencode(params)}"

    def _request(self, method: str, url: str, body: Optional[dict] = None) -> Optional[dict]:
        headers = {
            "Authorization": f"Bearer {self._token_manager.get_token()}",
            "Content-Type": "application/json",
        }
        status, payload = self._transport(method, url, headers, body)
        if status == 404:
            return None
        if status >= 400:
            raise ArmError(f"{method} {url.split('?')[0]} failed with HTTP {status}. {_error_message(payload)}")
        return payload or {}

    def container_url(self, kind: str, name: str) -> str:
        return self._url(f"{_collection(kind)}/{urllib.parse.quote(name)}")

    def get_container(self, kind: str, name: str) -> Optional[AssetContainer]:
        """Returns None when the container does not exist. Archived containers ARE returned."""
        body = self._request("GET", self.container_url(kind, name))
        if body is None:
            return None
        properties = body.get("properties") or {}
        return AssetContainer(
            name=body.get("name") or name,
            id=body.get("id") or "",
            latest_version=properties.get("latestVersion"),
            is_archived=bool(properties.get("isArchived")),
            tags=properties.get("tags") or {},
            body=body,
        )

    def get_version(self, kind: str, name: str, version: str) -> Optional[AssetVersion]:
        """Returns None when the version does not exist."""
        url = self._url(
            f"{_collection(kind)}/{urllib.parse.quote(name)}/versions/{urllib.parse.quote(str(version))}"
        )
        body = self._request("GET", url)
        if body is None:
            return None
        return _to_asset_version(body, name)

    def list_versions(
        self,
        kind: str,
        name: str,
        list_view_type: str = LIST_VIEW_ALL,
    ) -> list[AssetVersion]:
        """
        Lists versions under one container, following `nextLink`.

        `list_view_type` defaults to All because archived versions still occupy their
        version number and must be counted when deriving the next one.

        No `$top` or `$orderBy`: the component version API rejects both outright.
        """
        url = self._url(
            f"{_collection(kind)}/{urllib.parse.quote(name)}/versions",
            **{"listViewType": list_view_type},
        )
        versions: list[AssetVersion] = []
        while url:
            body = self._request("GET", url)
            if body is None:
                break
            for item in body.get("value") or []:
                versions.append(_to_asset_version(item, name))
            url = body.get("nextLink")
        return versions

    def unarchive_container(self, kind: str, name: str) -> bool:
        """
        Clears `isArchived` on the container and confirms it by re-reading.

        An archived container hides its versions from every list operation even when
        the versions themselves are active. The SDK cannot reach this flag.
        """
        container = self.get_container(kind, name)
        if container is None:
            return False
        properties = container.body.get("properties") or {}
        payload: dict[str, Any] = {
            "properties": {
                "tags": properties.get("tags") or {},
                "properties": properties.get("properties") or {},
                "isArchived": False,
            }
        }
        description = properties.get("description")
        if description is not None:
            payload["properties"]["description"] = description
        self._request("PUT", self.container_url(kind, name), payload)
        confirmed = self.get_container(kind, name)
        return confirmed is not None and not confirmed.is_archived


def _collection(kind: str) -> str:
    collection = ASSET_COLLECTIONS.get(kind)
    if not collection:
        raise ValueError(f"Unknown asset kind '{kind}'. Expected one of {sorted(ASSET_COLLECTIONS)}.")
    return collection


def _to_asset_version(body: dict, asset_name: str) -> AssetVersion:
    properties = body.get("properties") or {}
    system_data = body.get("systemData") or {}
    return AssetVersion(
        name=asset_name,
        version=str(body.get("name") or ""),
        id=body.get("id") or "",
        tags=properties.get("tags") or {},
        properties=properties,
        created_at=_parse_timestamp(system_data.get("createdAt")),
        is_archived=bool(properties.get("isArchived")),
    )


def _resolve_registry_resource_group(
    registry_name: str,
    subscription_id: str,
    token_manager: TokenManager,
    transport: Transport,
) -> str:
    url = (
        f"{ARM_BASE_URL}/subscriptions/{subscription_id}"
        f"/providers/{ML_PROVIDER}/registries?api-version={REST_API_VERSION}"
    )
    headers = {
        "Authorization": f"Bearer {token_manager.get_token()}",
        "Content-Type": "application/json",
    }
    while url:
        status, payload = transport("GET", url, headers, None)
        if status >= 400:
            raise ArmError(
                f"❌ Could not list registries in subscription '{subscription_id}' "
                f"(HTTP {status}). {_error_message(payload)}"
            )
        payload = payload or {}
        for item in payload.get("value") or []:
            if item.get("name") == registry_name:
                match = _RESOURCE_GROUP_PATTERN.search(item.get("id") or "")
                if match:
                    return match.group(1)
        url = payload.get("nextLink")
    raise ArmError(
        f"❌ Registry '{registry_name}' was not found in subscription '{subscription_id}'. "
        "Registries in another subscription are not supported."
    )
