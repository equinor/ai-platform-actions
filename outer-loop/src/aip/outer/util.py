"""
Shared utilities for the Outer Loop Action.

Provides:
- MLFlowProxyClient: authenticated HTTP client for the MLFlow proxy API
- github_output / github_step_summary: GitHub Actions integration helpers
- Auth helpers (token credential, DefaultAzureCredential passthrough)
"""

import os
import time
from pathlib import Path
from typing import Any, Optional

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
        self._base_url = base_url.rstrip("/")
        self._credential = credential
        self._scope = scope
        self._session = self._make_session()
        self._cached_token = None

    @staticmethod
    def _make_session() -> requests.Session:
        session = requests.Session()
        retry = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[502, 503, 504],
            allowed_methods=["GET"],
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

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

    def get_experiment_runs(self, experiment_name: str, max_results: int = 100) -> list[dict]:
        """Return a list of runs for an experiment, most recent first."""
        data = self._get(
            f"/experiments/{experiment_name}/runs",
            params={"max_results": max_results},
        )
        return data.get("runs", [])

    def get_run_metrics(self, run_id: str) -> dict[str, float]:
        """Return the final metric values for a single run."""
        data = self._get(f"/runs/{run_id}/metrics")
        return data.get("metrics", {})

    def compare_runs(self, experiment_name: str, run_ids: Optional[list[str]] = None) -> list[dict]:
        """Return comparison data for multiple runs in an experiment.

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
        return data.get("runs", [])

    def get_run_artifacts(self, run_id: str) -> list[dict]:
        """List artifacts for a run."""
        data = self._get(f"/runs/{run_id}/artifacts")
        return data.get("artifacts", [])

    def get_monitoring_run(self, experiment_name: str) -> Optional[dict]:
        """Return the latest monitoring run for a model/experiment."""
        runs = self.get_experiment_runs(experiment_name, max_results=1)
        return runs[0] if runs else None


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
    """Write key=value pairs to GITHUB_OUTPUT."""
    env_file = os.environ.get("GITHUB_OUTPUT")
    if env_file:
        with open(env_file, "a") as f:
            for key, value in outputs.items():
                f.write(f"{key}={value}\n")


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
