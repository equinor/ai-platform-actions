"""
Shared utilities for the Outer Loop Action.

Provides:
- MLFlowBackend: Protocol defining the shared interface for all MLFlow backends
- MLFlowProxyClient: authenticated HTTP client for the MLFlow proxy API (https://)
- AzureMLBackend: MLFlow backend using direct MLflow REST API calls against an AzureML workspace
- create_mlflow_client: factory that selects the correct backend from the URL/URI scheme
- github_output / github_step_summary: GitHub Actions integration helpers
- Auth helpers (token credential, DefaultAzureCredential passthrough)
"""

import os
import time
import uuid
from pathlib import Path
from typing import Any, Optional, Protocol, runtime_checkable

import requests
import typer
import yaml
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from azure.core.credentials import AccessToken
from azure.identity import DefaultAzureCredential

AML_SCOPE = "https://ml.azure.com/.default"
MANAGEMENT_SCOPE = "https://management.azure.com/.default"


# ---------------------------------------------------------------------------
# MLFlow backend protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class MLFlowBackend(Protocol):
    """Shared interface for all MLFlow data-access backends.

    Implementations must return run data as plain dicts with the shape::

        {"run_id": str, "status": str, "metrics": dict[str, float], "tags": dict[str, str]}
    """

    def get_experiment_runs(
        self, experiment_name: str, max_results: int = 100, run_name: Optional[str] = None
    ) -> list[dict]:
        """Return a list of runs for an experiment, most recent first.

        If ``run_name`` is supplied, only runs whose ``mlflow.runName`` tag matches
        exactly are returned.
        """
        ...

    def get_run_metrics(self, run_id: str) -> dict[str, float]:
        """Return the final metric values for a single run."""
        ...

    def compare_runs(
        self,
        experiment_name: str,
        run_ids: Optional[list[str]] = None,
        run_name: Optional[str] = None,
    ) -> list[dict]:
        """Return comparison data for multiple runs in an experiment.

        ``run_ids`` takes precedence over ``run_name`` when both are supplied.
        """
        ...

    def get_run_artifacts(self, run_id: str) -> list[dict]:
        """List artifacts for a run."""
        ...

    def get_monitoring_run(self, experiment_name: str) -> Optional[dict]:
        """Return the latest monitoring run for a model/experiment, or None."""
        ...


# ---------------------------------------------------------------------------
# Credential helpers (mirror of inner-loop pattern)
# ---------------------------------------------------------------------------

class Credential:
    """
    Credential wrapper that returns a pre-fetched access token.
    Used when running inside GitHub Actions where a token is injected.
    """

    def __init__(self, access_token: str, expires_on: int):
        self._access_token = AccessToken(token=access_token, expires_on=expires_on)

    def get_token(self, *scopes: str, **kwargs) -> AccessToken:
        return self._access_token


def get_credential(token: Optional[str] = None, expires_on: Optional[int] = None):
    """Return a credential object suitable for Azure SDK calls."""
    if token and expires_on:
        return Credential(token, int(expires_on))
    return DefaultAzureCredential()


def get_bearer_token(credential, scope: str = MANAGEMENT_SCOPE) -> str:
    """Obtain a raw bearer token string from a credential."""
    return credential.get_token(scope).token


# ---------------------------------------------------------------------------
# MLFlow Proxy client
# ---------------------------------------------------------------------------

def _make_requests_session() -> requests.Session:
    """Create a ``requests.Session`` with retry logic for transient server errors."""
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=[502, 503, 504],
        allowed_methods=["GET", "POST"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


class MLFlowProxyClient:
    """
    Thin HTTP client for the MLFlow proxy API.

    Uses a persistent ``requests.Session`` with automatic retry on transient
    server errors.  The bearer token is cached and only refreshed when it is
    within 60 seconds of expiry.
    All methods raise ``requests.HTTPError`` on non-2xx responses (except where
    noted).
    """

    def __init__(self, base_url: str, credential, scope: str = MANAGEMENT_SCOPE):
        if not base_url.startswith(("http://", "https://")):
            raise ValueError(
                f"mlflow-proxy-url must be an http(s) URL of the MLFlow proxy service "
                f"(e.g. https://mlflow-proxy.cluster.aurora.equinor.com), got: {base_url!r}. "
                "This input is NOT the AzureML MLflow tracking URI (azureml://...); "
                "it is the URL of the FastAPI mlflow-proxy that fronts MLflow."
            )
        self._base_url = base_url.rstrip("/")
        self._credential = credential
        self._scope = scope
        self._session = _make_requests_session()
        self._cached_token = None

    def _headers(self) -> dict[str, str]:
        now = int(time.time())
        if self._cached_token is None or self._cached_token.expires_on - now < 60:
            self._cached_token = self._credential.get_token(self._scope)
        return {
            "Authorization": f"Bearer {self._cached_token.token}",
            "Accept": "application/json",
        }

    def _get(self, path: str, params: Optional[dict] = None) -> Any:
        url = f"{self._base_url}{path}"
        response = self._session.get(url, headers=self._headers(), params=params, timeout=30)
        response.raise_for_status()
        return response.json()

    # --- Experiment endpoints ---

    def get_experiment_runs(
        self, experiment_name: str, max_results: int = 100, run_name: Optional[str] = None
    ) -> list[dict]:
        """Return a list of runs for an experiment, most recent first.

        If ``run_name`` is supplied, the returned list is filtered client-side to runs
        whose ``mlflow.runName`` tag matches exactly.  The proxy API is external and
        uncontrolled, so filtering is performed after fetching.
        """
        data = self._get(
            f"/experiments/{experiment_name}/runs",
            params={"max_results": max_results},
        )
        runs = data.get("runs", [])
        if run_name:
            runs = [r for r in runs if r.get("tags", {}).get("mlflow.runName") == run_name]
        return runs

    def get_run_metrics(self, run_id: str) -> dict[str, float]:
        """Return the final metric values for a single run."""
        data = self._get(f"/runs/{run_id}/metrics")
        return data.get("metrics", {})

    def compare_runs(
        self,
        experiment_name: str,
        run_ids: Optional[list[str]] = None,
        run_name: Optional[str] = None,
    ) -> list[dict]:
        """Return comparison data for multiple runs in an experiment.

        ``run_ids`` takes precedence over ``run_name`` when both are supplied.

        Raises ``RuntimeError`` with a clear message if the proxy does not
        support the ``/experiments/{name}/compare`` endpoint (HTTP 404).
        """
        params: dict[str, Any] = {}
        if run_ids:
            params["run_ids"] = ",".join(run_ids)
        try:
            data = self._get(f"/experiments/{experiment_name}/compare", params=params)
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 404:
                raise RuntimeError(
                    f"The MLFlow proxy does not support the /experiments/compare endpoint "
                    f"(received 404 for experiment '{experiment_name}'). "
                    "Ensure your proxy version supports server-side run comparison."
                ) from exc
            raise
        runs = data.get("runs", [])
        if run_name and not run_ids:
            runs = [r for r in runs if r.get("tags", {}).get("mlflow.runName") == run_name]
        return runs

    def get_run_artifacts(self, run_id: str) -> list[dict]:
        """List artifacts for a run."""
        data = self._get(f"/runs/{run_id}/artifacts")
        return data.get("artifacts", [])

    def get_monitoring_run(self, experiment_name: str) -> Optional[dict]:
        """Return the latest monitoring run for a model/experiment."""
        runs = self.get_experiment_runs(experiment_name, max_results=1)
        return runs[0] if runs else None


# ---------------------------------------------------------------------------
# AzureML backend (azureml:// tracking URI → direct MLflow REST API over HTTPS)
# ---------------------------------------------------------------------------

def _azureml_uri_to_https(uri: str) -> str:
    """Convert an ``azureml://`` tracking URI to the equivalent ``https://`` REST base URL.

    The two schemes share the same host and path, so the conversion is a simple
    prefix replacement::

        azureml://swedencentral.api.azureml.ms/mlflow/v1.0/...
        → https://swedencentral.api.azureml.ms/mlflow/v1.0/...
    """
    return "https://" + uri[len("azureml://"):]


class AzureMLBackend:
    """MLFlow backend that talks directly to an AzureML workspace via the MLflow REST API.

    The ``azureml://`` tracking URI encodes the same host and path as the HTTPS
    MLflow tracking server, so authentication reuses the same bearer-token
    mechanism as :class:`MLFlowProxyClient` (scope: ``AML_SCOPE``).  This avoids
    any dependency on the ``azureml-mlflow`` SDK plugin and its internal
    credential chain.

    MLflow REST API reference:
    https://mlflow.org/docs/latest/rest-api.html
    """

    def __init__(self, tracking_uri: str, credential):
        self._base_url = _azureml_uri_to_https(tracking_uri).rstrip("/")
        self._credential = credential
        self._scope = AML_SCOPE
        self._session = _make_requests_session()
        self._cached_token = None

    def _headers(self) -> dict[str, str]:
        now = int(time.time())
        if self._cached_token is None or self._cached_token.expires_on - now < 60:
            self._cached_token = self._credential.get_token(self._scope)
        return {
            "Authorization": f"Bearer {self._cached_token.token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _get(self, path: str, params: Optional[dict] = None) -> Any:
        url = f"{self._base_url}{path}"
        response = self._session.get(url, headers=self._headers(), params=params, timeout=30)
        response.raise_for_status()
        return response.json()

    def _post(self, path: str, body: dict) -> Any:
        url = f"{self._base_url}{path}"
        response = self._session.post(url, headers=self._headers(), json=body, timeout=30)
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _normalize_run(run: dict) -> dict:
        """Normalize a MLflow REST API run object to the standard backend dict shape.

        The MLflow REST API returns metrics as ``[{"key": k, "value": v, ...}]``
        rather than a flat dict, so we convert them here.
        """
        info = run.get("info", {})
        data = run.get("data", {})
        # AzureML's MLflow proxy omits "value" for NaN metrics, since JSON has no NaN.
        metrics = {m["key"]: m["value"] for m in data.get("metrics", []) if "value" in m}
        tags = {t["key"]: t["value"] for t in data.get("tags", [])}
        return {
            "run_id": info.get("run_id", ""),
            "status": info.get("status", ""),
            "metrics": metrics,
            "tags": tags,
        }

    def get_experiment_runs(
        self, experiment_name: str, max_results: int = 100, run_name: Optional[str] = None
    ) -> list[dict]:
        """Return a list of runs for an experiment, most recent first.

        If ``run_name`` is supplied, the filter is pushed to the MLflow REST API
        search query (server-side), which avoids over-fetching runs.
        """
        try:
            data = self._get(
                "/api/2.0/mlflow/experiments/get-by-name",
                params={"experiment_name": experiment_name},
            )
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 404:
                return []
            raise
        experiment_id = data["experiment"]["experiment_id"]
        body: dict[str, Any] = {
            "experiment_ids": [experiment_id],
            "max_results": max_results,
            "order_by": ["start_time DESC"],
        }
        if run_name:
            body["filter"] = f"tags.`mlflow.runName` = '{run_name}'"
        runs_data = self._post("/api/2.0/mlflow/runs/search", body)
        return [self._normalize_run(r) for r in runs_data.get("runs", [])]

    def get_run_metrics(self, run_id: str) -> dict[str, float]:
        """Return the final metric values for a single run."""
        data = self._get("/api/2.0/mlflow/runs/get", params={"run_id": run_id})
        run_data = data.get("run", {}).get("data", {})
        # AzureML's MLflow proxy omits "value" for NaN metrics, since JSON has no NaN.
        return {m["key"]: m["value"] for m in run_data.get("metrics", []) if "value" in m}

    def compare_runs(
        self,
        experiment_name: str,
        run_ids: Optional[list[str]] = None,
        run_name: Optional[str] = None,
    ) -> list[dict]:
        """Return comparison data for multiple runs in an experiment.

        ``run_ids`` takes precedence over ``run_name`` when both are supplied.
        """
        if run_ids:
            runs = []
            for rid in run_ids:
                data = self._get("/api/2.0/mlflow/runs/get", params={"run_id": rid})
                runs.append(self._normalize_run(data.get("run", {})))
            return runs
        return self.get_experiment_runs(experiment_name, max_results=100, run_name=run_name)

    def get_run_artifacts(self, run_id: str) -> list[dict]:
        """List artifacts for a run."""
        data = self._get("/api/2.0/mlflow/artifacts/list", params={"run_id": run_id})
        return [{"path": f.get("path", ""), "size": f.get("file_size", 0)} for f in data.get("files", [])]

    def get_monitoring_run(self, experiment_name: str) -> Optional[dict]:
        """Return the latest monitoring run for a model/experiment, or None."""
        runs = self.get_experiment_runs(experiment_name, max_results=1)
        return runs[0] if runs else None


# ---------------------------------------------------------------------------
# Backend factory
# ---------------------------------------------------------------------------

def create_mlflow_client(url: str, credential) -> MLFlowBackend:
    """Return the correct MLFlow backend based on the URL/URI scheme.

    - ``https://`` or ``http://`` → :class:`MLFlowProxyClient` (HTTP proxy service)
    - ``azureml://``              → :class:`AzureMLBackend`    (AzureML tracking URI)

    Raises :class:`ValueError` for any other scheme.
    """
    if url.startswith(("http://", "https://")):
        return MLFlowProxyClient(url, credential)
    if url.startswith("azureml://"):
        return AzureMLBackend(url, credential)
    raise ValueError(
        f"mlflow-url must be an https:// proxy URL or an azureml:// tracking URI, got: {url!r}. "
        "Examples:\n"
        "  https://mlflow-proxy.cluster.aurora.equinor.com\n"
        "  azureml://swedencentral.api.azureml.ms/mlflow/v1.0/subscriptions/<sub>/..."
    )


# ---------------------------------------------------------------------------
# YAML config loaders
# ---------------------------------------------------------------------------

def load_yaml_file(path: str, label: str) -> dict:
    """Load a YAML file and return its contents as a dict."""
    p = Path(path)
    if not p.exists():
        typer.echo(f"[outer-loop] ERROR: {label} file not found: {path}", err=True)
        raise typer.Exit(1)
    with p.open() as f:
        return yaml.safe_load(f) or {}


# ---------------------------------------------------------------------------
# GitHub Actions integration
# ---------------------------------------------------------------------------

def github_output(outputs: dict[str, str]) -> None:
    """Write key=value pairs to GITHUB_OUTPUT.

    Multi-line values use the heredoc delimiter syntax required by GitHub Actions::

        key<<ghadelimiter_<uuid>
        multi
        line
        value
        ghadelimiter_<uuid>

    Single-line values use the simple ``key=value`` format.
    """
    env_file = os.environ.get("GITHUB_OUTPUT")
    if env_file:
        with open(env_file, "a") as f:
            for key, value in outputs.items():
                str_value = str(value)
                if "\n" in str_value:
                    delimiter = f"ghadelimiter_{uuid.uuid4().hex}"
                    f.write(f"{key}<<{delimiter}\n{str_value}\n{delimiter}\n")
                else:
                    f.write(f"{key}={str_value}\n")


def github_step_summary(markdown: str) -> None:
    """Append markdown content to the GitHub step summary."""
    env_file = os.environ.get("GITHUB_STEP_SUMMARY")
    if env_file:
        with open(env_file, "a") as f:
            f.write(markdown + "\n")
    else:
        # Fallback: print to stdout when not running in GitHub Actions
        print(markdown)


# ---------------------------------------------------------------------------
# Shared CLI option helpers (empty-string-to-None for action.yaml passthrough)
# ---------------------------------------------------------------------------

def empty_string_to_none(value: Optional[str]) -> Optional[str]:
    """Typer callback: treat empty string as None."""
    if value == "" or value is None:
        return None
    return value
