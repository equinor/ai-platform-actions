"""
Wait-for operations for Inner Loop Action.
"""

import os
import time
from typing import Annotated, Callable, Optional, Any

import requests
import typer
from azure.core.exceptions import HttpResponseError, ResourceNotFoundError
from azure.identity import DefaultAzureCredential

from .util import (
    get_workspace_client,
    load_safe_tags,
    empty_string_to_none,
    get_ref_properties,
    get_deployment_ref_properties,
    github_output,
    Credential,
)

POLL_INTERVAL_SECONDS = 10
# Default timeout in minutes, can be overridden via TIMEOUT_MINUTES environment variable
DEFAULT_TIMEOUT_MINUTES = 30
# Buffer time in seconds before token expiry to trigger refresh
TOKEN_REFRESH_BUFFER_SECONDS = 5 * 60  # 5 minutes before expiry

SUCCESS_STATES = {"succeeded", "success", "completed", "ready"}
FAILURE_STATES = {
    "failed",
    "canceled",
    "cancelled",
    "error",
    "timeout",
    "timedout",
    "notresponding",
    "not responding",
}
ENDPOINT_SUCCESS_STATES = {"succeeded"}
ENDPOINT_FAILURE_STATES = {"failed", "canceled", "cancelled", "deleting"}

# Azure REST API version for Machine Learning Services
REST_API_VERSION = "2025-09-01" #"2025-01-01-preview"

app = typer.Typer()


def _get_timeout_seconds() -> int:
    """Get timeout in seconds from environment variable or default."""
    timeout_minutes_str = os.environ.get("TIMEOUT_MINUTES", "")
    if timeout_minutes_str:
        try:
            timeout_minutes = int(timeout_minutes_str)
            if timeout_minutes > 0:
                print(f"[waitfor] Using custom timeout of {timeout_minutes} minutes from TIMEOUT_MINUTES environment variable.")
                return timeout_minutes * 60
            else:
                print(f"[waitfor] Invalid TIMEOUT_MINUTES value '{timeout_minutes_str}', using default of {DEFAULT_TIMEOUT_MINUTES} minutes.")
        except ValueError:
            print(f"[waitfor] Invalid TIMEOUT_MINUTES value '{timeout_minutes_str}', using default of {DEFAULT_TIMEOUT_MINUTES} minutes.")
    return DEFAULT_TIMEOUT_MINUTES * 60


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
            # Initialize credential for dynamic token refresh
            self._credential = DefaultAzureCredential()
    
    def get_token(self) -> str:
        """
        Get a valid access token, refreshing if necessary.
        
        Returns:
            A valid access token string.
        """
        if self._static_token and self._static_expires_on:
            # Check if static token is still valid
            current_time = int(time.time())
            if current_time >= self._static_expires_on - TOKEN_REFRESH_BUFFER_SECONDS:
                print("[TokenManager] Warning: Static token is expiring soon or has expired. Cannot refresh static tokens.")
            return self._static_token
        
        # Use dynamic credential
        if self._credential:
            current_time = int(time.time())
            
            # Check if we need to refresh the token
            if (self._cached_token is None or 
                self._cached_expires_on is None or
                current_time >= self._cached_expires_on - TOKEN_REFRESH_BUFFER_SECONDS):
                
                print("[TokenManager] Refreshing access token...")
                token_response = self._credential.get_token("https://management.azure.com/.default")
                self._cached_token = token_response.token
                self._cached_expires_on = token_response.expires_on
                print(f"[TokenManager] Token refreshed, valid until {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self._cached_expires_on))}")
            
            return self._cached_token
        
        raise RuntimeError("No credential available to get access token")


def _get_access_token(token: Optional[str], expires_on: Optional[int]) -> str:
    """Get access token for Azure REST API calls. DEPRECATED: Use TokenManager instead."""
    if token and expires_on:
        return token
    else:
        credential = DefaultAzureCredential()
        token_response = credential.get_token("https://management.azure.com/.default")
        return token_response.token


def _get_rest_api_base_url(
    subscription_id: str,
    resource_group: str,
    workspace_name: str,
) -> str:
    """Build the base URL for Azure ML REST API."""
    return (
        f"https://management.azure.com/subscriptions/{subscription_id}"
        f"/resourceGroups/{resource_group}"
        f"/providers/Microsoft.MachineLearningServices/workspaces/{workspace_name}"
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
        response = requests.get(url, headers=headers, timeout=30)
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


def _get_provisioning_state_from_rest(
    asset_type: str,
    subscription_id: str,
    resource_group: str,
    workspace_name: str,
    name: str,
    version: Optional[str],
    access_token: str,
) -> Optional[str]:
    """
    Get provisioning state of an asset via Azure REST API.
    
    The SDK objects don't expose provisioning_state, so we need to call
    the REST API directly to get this information.
    
    Supported asset types: environment, component, data, model
    """
    base_url = _get_rest_api_base_url(subscription_id, resource_group, workspace_name)
    
    # Build the URL based on asset type
    asset_type_map = {
        "environment": "environments",
        "component": "components",
        "data": "data",
        "model": "models",
    }
    
    rest_asset_type = asset_type_map.get(asset_type)
    if not rest_asset_type:
        print(f"[REST API] Unknown asset type: {asset_type}")
        return None
    
    if version:
        url = f"{base_url}/{rest_asset_type}/{name}/versions/{version}?api-version={REST_API_VERSION}"
    else:
        url = f"{base_url}/{rest_asset_type}/{name}?api-version={REST_API_VERSION}"
    
    response_data = _call_rest_api(url, access_token)
    if not response_data:
        return None
    
    # Extract provisioning state from response
    properties = response_data.get("properties", {})
    provisioning_state = properties.get("provisioningState")
    if asset_type=='environment':
        image_exists = properties.get("imageDetails").get("exists")
        if provisioning_state=='Succeeded' and not image_exists:
            provisioning_state='Running'
    
    if provisioning_state:
        return str(provisioning_state).strip().lower()
    
    return None


def _get_job_state_from_rest(
    subscription_id: str,
    resource_group: str,
    workspace_name: str,
    job_name: str,
    access_token: str,
) -> Optional[str]:
    """
    Get job status via Azure REST API.
    
    Jobs use a different endpoint pattern and return 'status' instead of 'provisioningState'.
    """
    base_url = _get_rest_api_base_url(subscription_id, resource_group, workspace_name)
    url = f"{base_url}/jobs/{job_name}?api-version={REST_API_VERSION}"
    
    response_data = _call_rest_api(url, access_token)
    if not response_data:
        return None
    
    # Jobs return status in the properties
    properties = response_data.get("properties", {})
    status = properties.get("status")
    
    if status:
        return str(status).strip().lower()
    
    return None


def _get_online_endpoint_state_from_rest(
    subscription_id: str,
    resource_group: str,
    workspace_name: str,
    endpoint_name: str,
    access_token: str,
) -> Optional[str]:
    """
    Get online endpoint provisioning state via Azure REST API.
    """
    base_url = _get_rest_api_base_url(subscription_id, resource_group, workspace_name)
    url = f"{base_url}/onlineEndpoints/{endpoint_name}?api-version={REST_API_VERSION}"
    
    response_data = _call_rest_api(url, access_token)
    if not response_data:
        return None
    
    properties = response_data.get("properties", {})
    provisioning_state = properties.get("provisioningState")
    
    if provisioning_state:
        return str(provisioning_state).strip().lower()
    
    return None


def _get_online_deployment_state_from_rest(
    subscription_id: str,
    resource_group: str,
    workspace_name: str,
    endpoint_name: str,
    deployment_name: str,
    access_token: str,
) -> Optional[str]:
    """
    Get online deployment provisioning state via Azure REST API.
    """
    base_url = _get_rest_api_base_url(subscription_id, resource_group, workspace_name)
    url = f"{base_url}/onlineEndpoints/{endpoint_name}/deployments/{deployment_name}?api-version={REST_API_VERSION}"
    
    response_data = _call_rest_api(url, access_token)
    if not response_data:
        return None
    
    properties = response_data.get("properties", {})
    provisioning_state = properties.get("provisioningState")
    
    if provisioning_state:
        return str(provisioning_state).strip().lower()
    
    return None


def _normalize_state(state: Optional[Any]) -> Optional[str]:
    if state is None:
        return None
    value = getattr(state, "value", state)
    return str(value).strip().lower()


def _tags_match(asset_tags: Optional[dict[str, Any]], expected: Optional[dict[str, Any]]) -> bool:
    if not expected:
        return True
    if not asset_tags:
        return False
    for key, value in expected.items():
        if key not in asset_tags:
            return False
        if value and asset_tags[key] != value:
            return False
    return True


def _extract_state(entity: Any) -> Optional[str]:
    direct_attrs = ["provisioning_state", "provisioning_status", "status", "state", "creation_state"]
    for attr in direct_attrs:
        state = getattr(entity, attr, None)
        if state:
            normalized = _normalize_state(state)
            if normalized:
                return normalized
    props = getattr(entity, "properties", None)
    if isinstance(props, dict):
        for key in [
            "provisioning_state",
            "provisioningState",
            "status",
            "state",
            "creation_state",
        ]:
            state = props.get(key)
            if state:
                normalized = _normalize_state(state)
                if normalized:
                    return normalized
    return None


def _wait_for_asset(
    subject: str,
    fetch_entity: Callable[[], Any],
    tags: Optional[dict[str, Any]] = None,
    fetch_state: Optional[Callable[[], Optional[str]]] = None,
    token_manager: Optional[TokenManager] = None,
) -> tuple[Any, Optional[str]]:
    """
    Wait for an asset to reach a terminal state.
    
    Args:
        subject: Name of the asset type for logging purposes.
        fetch_entity: Callable to fetch the entity from the SDK.
        tags: Optional tags to match against the entity.
        fetch_state: Optional callable to fetch the provisioning state via REST API.
                     If provided, this is used instead of _extract_state.
                     The callable receives a fresh access token as parameter.
        token_manager: Optional TokenManager for refreshing tokens during long waits.
    """
    timeout_seconds = _get_timeout_seconds()
    start = time.monotonic()
    attempt = 0
    while True:
        attempt += 1
        elapsed = time.monotonic() - start
        remaining = timeout_seconds - elapsed
        if remaining <= 0:
            print(f"[waitfor {subject}] ❌ Timed out after {timeout_seconds // 60} minutes.")
            raise typer.Exit(code=1)
        try:
            entity = fetch_entity()
        except ResourceNotFoundError:
            entity = None
        except HttpResponseError as exc:
            print(
                f"[waitfor {subject}] Attempt {attempt}: Azure response error '{exc}'. Waiting before retry."
            )
            entity = None
        except Exception as exc:
            print(f"[waitfor {subject}] Attempt {attempt}: Unexpected error '{exc}'. Waiting before retry.")
            entity = None

        if entity and not _tags_match(getattr(entity, "tags", None), tags):
            entity = None
            print(
                f"[waitfor {subject}] Attempt {attempt}: asset found but tags do not match request; waiting."
            )

        if entity:
            # Use REST API to fetch state if provided, otherwise fall back to SDK extraction
            if fetch_state:
                # Get fresh token from token manager if available
                if token_manager:
                    fresh_token = token_manager.get_token()
                    state = fetch_state(fresh_token)
                else:
                    state = fetch_state(None)
            else:
                state = _extract_state(entity)
            normalized_state = _normalize_state(state)
            if normalized_state in SUCCESS_STATES:
                print(
                    f"[waitfor {subject}] ✅ Asset ready with state '{normalized_state or 'available'}'."
                )
                return entity, normalized_state
            if normalized_state in FAILURE_STATES:
                print(f"[waitfor {subject}] ❌ Asset entered failure state '{normalized_state}'.")
                raise typer.Exit(code=1)
            print(
                f"[waitfor {subject}] Attempt {attempt}: state='{normalized_state or 'unknown'}', remaining {int(remaining)}s."
            )
        else:
            print(
                f"[waitfor {subject}] Attempt {attempt}: asset not found yet, remaining {int(remaining)}s."
            )

        sleep_window = min(POLL_INTERVAL_SECONDS, max(1, int(remaining)))
        time.sleep(sleep_window)


def _emit_github_output(entity: Any) -> None:
    name = getattr(entity, "name", None)
    version = getattr(entity, "version", None)
    resource_id = getattr(entity, "id", None)
    output: dict[str, str] = {}
    if name:
        if version:
            output["reference"] = f"azureml:{name}:{version}"
            output["version"] = str(version)
        else:
            output["reference"] = f"azureml:{name}"
            output["version"] = str(name)
    if resource_id:
        output["resource-id"] = resource_id
    if output:
        github_output(output)


def _emit_endpoint_github_output(entity: Any) -> None:
    """Emit GitHub output for online endpoints."""
    name = getattr(entity, "name", None)
    resource_id = getattr(entity, "id", None)
    scoring_uri = getattr(entity, "scoring_uri", None)
    output: dict[str, str] = {}
    if name:
        output["reference"] = f"azureml:{name}"
        output["version"] = str(name)
    if resource_id:
        output["resource-id"] = resource_id
    if scoring_uri:
        output["scoring-uri"] = scoring_uri
    if output:
        github_output(output)


def _emit_deployment_github_output(entity: Any, endpoint_name: str) -> None:
    """Emit GitHub output for online deployments."""
    name = getattr(entity, "name", None)
    resource_id = getattr(entity, "id", None)
    output: dict[str, str] = {}
    if name:
        output["reference"] = f"azureml:{endpoint_name}/deployments/{name}"
        output["version"] = str(name)
    if resource_id:
        output["resource-id"] = resource_id
    if output:
        github_output(output)


def _require_version(subject: str, version: Optional[str]) -> str:
    if not version:
        raise typer.BadParameter(
            f"waitfor {subject} requires a reference with an explicit version to avoid ambiguous polling."
        )
    return version


@app.command()
def data(
    subscription_id: Annotated[str, typer.Option("--subscription", "-s")],
    resource_group: Annotated[str, typer.Option("--resource-group", "-g")],
    workspace_name: Annotated[str, typer.Option("--workspace-name", "-w")],
    data_ref: str,
    token: Optional[str] = None,
    expires_on: Optional[int] = None,
    tags: Annotated[
        Optional[str],
        typer.Option(help="Tags in the config file to use", callback=load_safe_tags),
    ] = None,
    registry_name: Annotated[Optional[str], typer.Option("--registry-name", callback=empty_string_to_none)] = None,
    promote_stage: Annotated[Optional[str], typer.Option("--promote-stage", callback=empty_string_to_none)] = None,
    image_build_compute: Annotated[Optional[str], typer.Option("--image-build-compute", callback=empty_string_to_none)] = None,
    aml_token: Annotated[Optional[str], typer.Option("--aml-token", callback=empty_string_to_none)] = None,
    traffic_allocation: Annotated[Optional[str], typer.Option("--traffic-allocation", callback=empty_string_to_none)] = None,
):
    print(f"[waitfor data] Waiting for data asset {data_ref}")
    data_props = get_ref_properties(data_ref)
    data_version = _require_version("data", data_props.version)

    client = get_workspace_client(
        subscription_id=subscription_id,
        resource_group=resource_group,
        workspace_name=workspace_name,
        token=token,
        expires_on=expires_on,
    )

    # Create token manager for automatic token refresh during long waits
    token_manager = TokenManager(token=token, expires_on=expires_on)

    entity, final_state = _wait_for_asset(
        subject="data",
        fetch_entity=lambda: client.data.get(name=data_props.name, version=data_version),
        tags=tags,
        fetch_state=lambda access_token: _get_provisioning_state_from_rest(
            asset_type="data",
            subscription_id=subscription_id,
            resource_group=resource_group,
            workspace_name=workspace_name,
            name=data_props.name,
            version=data_version,
            access_token=access_token,
        ),
        token_manager=token_manager,
    )

    print(
        f"[waitfor data] ✅ Data asset '{entity.name}' version '{entity.version}' reached state '{final_state or 'available'}'."
    )
    _emit_github_output(entity)


@app.command()
def environment(
    subscription_id: Annotated[str, typer.Option("--subscription", "-s")],
    resource_group: Annotated[str, typer.Option("--resource-group", "-g")],
    workspace_name: Annotated[str, typer.Option("--workspace-name", "-w")],
    env_ref: str,
    token: Optional[str] = None,
    expires_on: Optional[int] = None,
    tags: Annotated[
        Optional[str],
        typer.Option(help="Tags in the config file to use", callback=load_safe_tags),
    ] = None,
    registry_name: Annotated[Optional[str], typer.Option("--registry-name", callback=empty_string_to_none)] = None,
    promote_stage: Annotated[Optional[str], typer.Option("--promote-stage", callback=empty_string_to_none)] = None,
    image_build_compute: Annotated[Optional[str], typer.Option("--image-build-compute", callback=empty_string_to_none)] = None,
    aml_token: Annotated[Optional[str], typer.Option("--aml-token", callback=empty_string_to_none)] = None,
    traffic_allocation: Annotated[Optional[str], typer.Option("--traffic-allocation", callback=empty_string_to_none)] = None,
):
    print(f"[waitfor environment] Waiting for environment {env_ref}")
    env_props = get_ref_properties(env_ref)
    env_version = _require_version("environment", env_props.version)

    client = get_workspace_client(
        subscription_id=subscription_id,
        resource_group=resource_group,
        workspace_name=workspace_name,
        token=token,
        expires_on=expires_on,
    )

    # Create token manager for automatic token refresh during long waits
    token_manager = TokenManager(token=token, expires_on=expires_on)

    entity, final_state = _wait_for_asset(
        subject="environment",
        fetch_entity=lambda: client.environments.get(name=env_props.name, version=env_version),
        tags=tags,
        fetch_state=lambda access_token: _get_provisioning_state_from_rest(
            asset_type="environment",
            subscription_id=subscription_id,
            resource_group=resource_group,
            workspace_name=workspace_name,
            name=env_props.name,
            version=env_version,
            access_token=access_token,
        ),
        token_manager=token_manager,
    )

    print(
        f"[waitfor environment] ✅ Environment '{entity.name}' version '{entity.version}' reached state '{final_state}'."
    )
    _emit_github_output(entity)


@app.command()
def component(
    subscription_id: Annotated[str, typer.Option("--subscription", "-s")],
    resource_group: Annotated[str, typer.Option("--resource-group", "-g")],
    workspace_name: Annotated[str, typer.Option("--workspace-name", "-w")],
    component_ref: str,
    token: Optional[str] = None,
    expires_on: Optional[int] = None,
    tags: Annotated[
        Optional[str],
        typer.Option(help="Tags in the config file to use", callback=load_safe_tags),
    ] = None,
    registry_name: Annotated[Optional[str], typer.Option("--registry-name", callback=empty_string_to_none)] = None,
    promote_stage: Annotated[Optional[str], typer.Option("--promote-stage", callback=empty_string_to_none)] = None,
    image_build_compute: Annotated[Optional[str], typer.Option("--image-build-compute", callback=empty_string_to_none)] = None,
    aml_token: Annotated[Optional[str], typer.Option("--aml-token", callback=empty_string_to_none)] = None,
    traffic_allocation: Annotated[Optional[str], typer.Option("--traffic-allocation", callback=empty_string_to_none)] = None,
):
    print(f"[waitfor component] Waiting for component {component_ref}")
    comp_props = get_ref_properties(component_ref)
    comp_version = _require_version("component", comp_props.version)

    client = get_workspace_client(
        subscription_id=subscription_id,
        resource_group=resource_group,
        workspace_name=workspace_name,
        token=token,
        expires_on=expires_on,
    )

    # Create token manager for automatic token refresh during long waits
    token_manager = TokenManager(token=token, expires_on=expires_on)

    entity, final_state = _wait_for_asset(
        subject="component",
        fetch_entity=lambda: client.components.get(name=comp_props.name, version=comp_version),
        tags=tags,
        fetch_state=lambda access_token: _get_provisioning_state_from_rest(
            asset_type="component",
            subscription_id=subscription_id,
            resource_group=resource_group,
            workspace_name=workspace_name,
            name=comp_props.name,
            version=comp_version,
            access_token=access_token,
        ),
        token_manager=token_manager,
    )

    print(
        f"[waitfor component] ✅ Component '{entity.name}' version '{entity.version}' reached state '{final_state}'."
    )
    _emit_github_output(entity)


@app.command()
def model(
    subscription_id: Annotated[str, typer.Option("--subscription", "-s")],
    resource_group: Annotated[str, typer.Option("--resource-group", "-g")],
    workspace_name: Annotated[str, typer.Option("--workspace-name", "-w")],
    model_ref: str,
    token: Optional[str] = None,
    expires_on: Optional[int] = None,
    tags: Annotated[
        Optional[str],
        typer.Option(help="Tags in the config file to use", callback=load_safe_tags),
    ] = None,
    registry_name: Annotated[Optional[str], typer.Option("--registry-name", callback=empty_string_to_none)] = None,
    promote_stage: Annotated[Optional[str], typer.Option("--promote-stage", callback=empty_string_to_none)] = None,
    image_build_compute: Annotated[Optional[str], typer.Option("--image-build-compute", callback=empty_string_to_none)] = None,
    aml_token: Annotated[Optional[str], typer.Option("--aml-token", callback=empty_string_to_none)] = None,
    traffic_allocation: Annotated[Optional[str], typer.Option("--traffic-allocation", callback=empty_string_to_none)] = None,
):
    print(f"[waitfor model] Waiting for model {model_ref}")
    model_props = get_ref_properties(model_ref)
    model_version = _require_version("model", model_props.version)

    client = get_workspace_client(
        subscription_id=subscription_id,
        resource_group=resource_group,
        workspace_name=workspace_name,
        token=token,
        expires_on=expires_on,
    )

    # Create token manager for automatic token refresh during long waits
    token_manager = TokenManager(token=token, expires_on=expires_on)

    entity, final_state = _wait_for_asset(
        subject="model",
        fetch_entity=lambda: client.models.get(name=model_props.name, version=model_version),
        tags=tags,
        fetch_state=lambda access_token: _get_provisioning_state_from_rest(
            asset_type="model",
            subscription_id=subscription_id,
            resource_group=resource_group,
            workspace_name=workspace_name,
            name=model_props.name,
            version=model_version,
            access_token=access_token,
        ),
        token_manager=token_manager,
    )

    print(
        f"[waitfor model] ✅ Model '{entity.name}' version '{entity.version}' reached state '{final_state}'."
    )
    _emit_github_output(entity)


@app.command()
def job(
    subscription_id: Annotated[str, typer.Option("--subscription", "-s")],
    resource_group: Annotated[str, typer.Option("--resource-group", "-g")],
    workspace_name: Annotated[str, typer.Option("--workspace-name", "-w")],
    job_name: str,
    token: Optional[str] = None,
    expires_on: Optional[int] = None,
    tags: Annotated[
        Optional[str],
        typer.Option(help="Tags in the config file to use", callback=load_safe_tags),
    ] = None,
    registry_name: Annotated[Optional[str], typer.Option("--registry-name", callback=empty_string_to_none)] = None,
    promote_stage: Annotated[Optional[str], typer.Option("--promote-stage", callback=empty_string_to_none)] = None,
    image_build_compute: Annotated[Optional[str], typer.Option("--image-build-compute", callback=empty_string_to_none)] = None,
    aml_token: Annotated[Optional[str], typer.Option("--aml-token", callback=empty_string_to_none)] = None,
    traffic_allocation: Annotated[Optional[str], typer.Option("--traffic-allocation", callback=empty_string_to_none)] = None,
):
    print(f"[waitfor job] Waiting for job {job_name}")

    client = get_workspace_client(
        subscription_id=subscription_id,
        resource_group=resource_group,
        workspace_name=workspace_name,
        token=token,
        expires_on=expires_on,
    )

    # Create token manager for automatic token refresh during long waits
    token_manager = TokenManager(token=token, expires_on=expires_on)

    entity, final_state = _wait_for_asset(
        subject="job",
        fetch_entity=lambda: client.jobs.get(name=job_name),
        tags=tags,
        fetch_state=lambda access_token: _get_job_state_from_rest(
            subscription_id=subscription_id,
            resource_group=resource_group,
            workspace_name=workspace_name,
            job_name=job_name,
            access_token=access_token,
        ),
        token_manager=token_manager,
    )

    if final_state not in SUCCESS_STATES:
        print(f"[waitfor job] ❌ Job reached terminal state '{final_state}'.")
        raise typer.Exit(code=1)

    print(f"[waitfor job] ✅ Job '{entity.name}' completed with state '{final_state}'.")
    _emit_github_output(entity)


@app.command()
def online_endpoint(
    subscription_id: Annotated[str, typer.Option("--subscription", "-s")],
    resource_group: Annotated[str, typer.Option("--resource-group", "-g")],
    workspace_name: Annotated[str, typer.Option("--workspace-name", "-w")],
    endpoint_name: str,
    token: Optional[str] = None,
    expires_on: Optional[int] = None,
    tags: Annotated[
        Optional[str],
        typer.Option(help="Tags in the config file to use", callback=load_safe_tags),
    ] = None,
    registry_name: Annotated[Optional[str], typer.Option("--registry-name", callback=empty_string_to_none)] = None,
    promote_stage: Annotated[Optional[str], typer.Option("--promote-stage", callback=empty_string_to_none)] = None,
    image_build_compute: Annotated[Optional[str], typer.Option("--image-build-compute", callback=empty_string_to_none)] = None,
    aml_token: Annotated[Optional[str], typer.Option("--aml-token", callback=empty_string_to_none)] = None,
    traffic_allocation: Annotated[Optional[str], typer.Option("--traffic-allocation", callback=empty_string_to_none)] = None,
):
    """Wait for an online endpoint to reach a terminal state."""
    print(f"[waitfor online-endpoint] Waiting for online endpoint {endpoint_name}")

    client = get_workspace_client(
        subscription_id=subscription_id,
        resource_group=resource_group,
        workspace_name=workspace_name,
        token=token,
        expires_on=expires_on,
    )

    token_manager = TokenManager(token=token, expires_on=expires_on)

    entity, final_state = _wait_for_asset(
        subject="online-endpoint",
        fetch_entity=lambda: client.online_endpoints.get(name=endpoint_name),
        tags=tags,
        fetch_state=lambda access_token: _get_online_endpoint_state_from_rest(
            subscription_id=subscription_id,
            resource_group=resource_group,
            workspace_name=workspace_name,
            endpoint_name=endpoint_name,
            access_token=access_token,
        ),
        token_manager=token_manager,
    )

    if final_state not in ENDPOINT_SUCCESS_STATES:
        print(f"[waitfor online-endpoint] ❌ Online endpoint reached terminal state '{final_state}'.")
        raise typer.Exit(code=1)

    print(f"[waitfor online-endpoint] ✅ Online endpoint '{entity.name}' reached state '{final_state}'.")
    _emit_endpoint_github_output(entity)


@app.command()
def online_deployment(
    subscription_id: Annotated[str, typer.Option("--subscription", "-s")],
    resource_group: Annotated[str, typer.Option("--resource-group", "-g")],
    workspace_name: Annotated[str, typer.Option("--workspace-name", "-w")],
    deployment_resource: str,
    token: Optional[str] = None,
    expires_on: Optional[int] = None,
    tags: Annotated[
        Optional[str],
        typer.Option(help="Tags in the config file to use", callback=load_safe_tags),
    ] = None,
    registry_name: Annotated[Optional[str], typer.Option("--registry-name", callback=empty_string_to_none)] = None,
    promote_stage: Annotated[Optional[str], typer.Option("--promote-stage", callback=empty_string_to_none)] = None,
    image_build_compute: Annotated[Optional[str], typer.Option("--image-build-compute", callback=empty_string_to_none)] = None,
    aml_token: Annotated[Optional[str], typer.Option("--aml-token", callback=empty_string_to_none)] = None,
    traffic_allocation: Annotated[Optional[str], typer.Option("--traffic-allocation", callback=empty_string_to_none)] = None,
):
    """Wait for an online deployment to reach a terminal state."""
    deployment_ref = get_deployment_ref_properties(deployment_resource)
    endpoint_name = deployment_ref.endpoint_name
    deployment_name = deployment_ref.deployment_name

    print(f"[waitfor online-deployment] Waiting for deployment {deployment_name} on endpoint {endpoint_name}")

    client = get_workspace_client(
        subscription_id=subscription_id,
        resource_group=resource_group,
        workspace_name=workspace_name,
        token=token,
        expires_on=expires_on,
    )

    token_manager = TokenManager(token=token, expires_on=expires_on)

    entity, final_state = _wait_for_asset(
        subject="online-deployment",
        fetch_entity=lambda: client.online_deployments.get(
            endpoint_name=endpoint_name,
            name=deployment_name,
        ),
        tags=tags,
        fetch_state=lambda access_token: _get_online_deployment_state_from_rest(
            subscription_id=subscription_id,
            resource_group=resource_group,
            workspace_name=workspace_name,
            endpoint_name=endpoint_name,
            deployment_name=deployment_name,
            access_token=access_token,
        ),
        token_manager=token_manager,
    )

    if final_state not in ENDPOINT_SUCCESS_STATES:
        print(f"[waitfor online-deployment] ❌ Online deployment reached terminal state '{final_state}'.")
        raise typer.Exit(code=1)

    print(f"[waitfor online-deployment] ✅ Deployment '{entity.name}' on endpoint '{endpoint_name}' reached state '{final_state}'.")
    _emit_deployment_github_output(entity, endpoint_name)


if __name__ == "__main__":
    app()
