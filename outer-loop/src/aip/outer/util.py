"""
Shared utilities for the Outer Loop Action.

Provides:
- MLFlowBackend: Protocol defining the shared interface for all MLFlow backends
- MLflowRestBackend: MLFlow backend using the standard MLflow REST API over HTTP(S)
- create_mlflow_client: factory that maps ``https://``/``http://`` URLs and
  ``azureml://`` tracking URIs onto :class:`MLflowRestBackend`
- BearerToken / resolve_bearer_token: validation of the caller-supplied bearer token
- github_output / github_step_summary: GitHub Actions integration helpers
"""

import os
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Protocol, runtime_checkable

import jwt
import requests
import typer
import yaml
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

TOKEN_EXPIRY_MARGIN_SECONDS = 60


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
        child_run_name: Optional[str] = None,
    ) -> list[dict]:
        """Return comparison data for multiple runs in an experiment.

        ``run_ids`` takes precedence over name-based filtering when supplied.
        """
        ...

    def get_child_runs(
        self,
        experiment_name: str,
        parent_run_id: str,
        child_run_name: Optional[str] = None,
    ) -> list[dict]:
        """Return the child runs of ``parent_run_id``, most recent first.

        If ``child_run_name`` is supplied, only children whose display name
        matches exactly are returned.
        """
        ...

    def get_run_artifacts(self, run_id: str) -> list[dict]:
        """List artifacts for a run.

        NB: listing only. Downloading (``mlflow.artifacts.download_artifacts``)
        would reintroduce a dependency on ``mlflow-skinny`` — deliberately dropped
        because ``mlflow``/``azureml-mlflow`` cap ``cryptography`` below the version
        needed to clear its advisories. Prefer fetching artifact content over REST.
        """
        ...

    def get_monitoring_run(self, experiment_name: str) -> Optional[dict]:
        """Return the latest monitoring run for a model/experiment, or None."""
        ...


# ---------------------------------------------------------------------------
# Bearer token
# ---------------------------------------------------------------------------

class TokenError(ValueError):
    """The supplied bearer token is missing, unusable or expired."""


def _format_epoch(epoch_seconds: int) -> str:
    return datetime.fromtimestamp(epoch_seconds, tz=timezone.utc).isoformat()


@dataclass(frozen=True)
class BearerToken:
    """A caller-supplied bearer token together with its effective expiry (epoch seconds)."""

    value: str
    expires_on: int

    def __repr__(self) -> str:
        return f"BearerToken(expires_on={_format_epoch(self.expires_on)})"

    def is_expired(self, now: Optional[float] = None) -> bool:
        current = time.time() if now is None else now
        return self.expires_on - current < TOKEN_EXPIRY_MARGIN_SECONDS

    def ensure_valid(self) -> None:
        if self.is_expired():
            raise TokenError(
                f"token expired (or expires within {TOKEN_EXPIRY_MARGIN_SECONDS} s) "
                f"at {_format_epoch(self.expires_on)}; obtain a fresh token"
            )


def jwt_expiry(token: str) -> Optional[int]:
    """Return the ``exp`` claim of a JWT, or ``None`` if the token is not a JWT with ``exp``.

    The signature is not verified: the MLflow server is responsible for that.
    The claim is only read to fail early on tokens that are already expired.
    """
    try:
        claims = jwt.decode(token, options={"verify_signature": False})
    except jwt.PyJWTError:
        return None
    exp = claims.get("exp")
    if isinstance(exp, bool) or not isinstance(exp, (int, float)):
        return None
    return int(exp)


def resolve_bearer_token(token: Optional[str], expires_on: Optional[str] = None) -> BearerToken:
    """Validate the caller-supplied token and determine its effective expiry.

    The effective expiry is the earliest of the JWT ``exp`` claim and ``expires_on``
    (epoch seconds). At least one of them must be available.

    Raises:
        TokenError: when the token is missing, ``expires_on`` is malformed, no expiry
            can be determined, or the token has already expired.
    """
    if not token or not token.strip():
        raise TokenError("--token is required")
    value = token.strip()

    user_expiry: Optional[int] = None
    if expires_on is not None and expires_on.strip():
        try:
            user_expiry = int(expires_on.strip())
        except ValueError:
            raise TokenError("--expires-on must be an integer number of epoch seconds") from None

    expiries = [e for e in (jwt_expiry(value), user_expiry) if e is not None]
    if not expiries:
        raise TokenError(
            "token is not a JWT with an 'exp' claim; supply --expires-on (epoch seconds)"
        )

    bearer = BearerToken(value=value, expires_on=min(expiries))
    bearer.ensure_valid()
    return bearer


def require_bearer_token(token: Optional[str], expires_on: Optional[str], log_prefix: str) -> BearerToken:
    """Resolve the bearer token for a command, exiting with code 1 on any token error."""
    try:
        bearer = resolve_bearer_token(token, expires_on)
    except TokenError as exc:
        typer.echo(f"{log_prefix} ERROR: {exc}", err=True)
        raise typer.Exit(1) from None
    typer.echo(f"{log_prefix} Token valid until: {_format_epoch(bearer.expires_on)}")
    return bearer


# ---------------------------------------------------------------------------
# MLflow REST backend
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


def azureml_uri_to_https(uri: str) -> str:
    """Convert an ``azureml://`` tracking URI to the equivalent ``https://`` REST base URL.

    The two schemes share the same host and path, so the conversion is a simple
    prefix replacement::

        azureml://swedencentral.api.azureml.ms/mlflow/v1.0/...
        → https://swedencentral.api.azureml.ms/mlflow/v1.0/...
    """
    return "https://" + uri[len("azureml://"):]


def run_display_name(run: dict) -> str:
    """Return the MLflow run name from the standard field or compatibility tag."""
    return run.get("run_name") or run.get("tags", {}).get("mlflow.runName", "")


def _parent_run_id(run: dict) -> str:
    """Return the AzureML or MLflow parent run identifier."""
    return (
        run.get("parent_run_id")
        or run.get("tags", {}).get("mlflow.parentRunId", "")
    )


def _select_child_runs(
    runs: list[dict], parent_ids: set[str], child_run_name: Optional[str] = None
) -> list[dict]:
    """Select child runs of the supplied parent run IDs, optionally by display name."""
    return [
        run for run in runs
        if _parent_run_id(run) in parent_ids
        and (child_run_name is None or run_display_name(run) == child_run_name)
    ]


class MLflowRestBackend:
    """MLFlow backend that talks to any MLflow tracking server via the MLflow REST API.

    ``base_url`` is the tracking server root (it may include a path prefix, e.g.
    ``https://host/my-mlflow``); requests go to ``<base_url>/api/2.0/mlflow/...``.
    Every request carries ``Authorization: Bearer <token>`` with the caller-supplied
    token, exactly as ``MlflowClient`` does with ``MLFLOW_TRACKING_TOKEN``.

    MLflow REST API reference:
    https://mlflow.org/docs/latest/rest-api.html
    """

    def __init__(self, base_url: str, token: BearerToken):
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._session = _make_requests_session()

    @property
    def base_url(self) -> str:
        return self._base_url

    def _headers(self) -> dict[str, str]:
        self._token.ensure_valid()
        return {
            "Authorization": f"Bearer {self._token.value}",
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
        # NaN metrics are returned without "value", since JSON has no NaN.
        metrics = {m["key"]: m["value"] for m in data.get("metrics", []) if "value" in m}
        tags = {t["key"]: t["value"] for t in data.get("tags", [])}
        return {
            "run_id": info.get("run_id", ""),
            "status": info.get("status", ""),
            "run_name": info.get("run_name", tags.get("mlflow.runName", "")),
            "parent_run_id": info.get("parent_run_id", info.get("parentRunId", "")),
            "metrics": metrics,
            "tags": tags,
        }

    def get_experiment_runs(
        self, experiment_name: str, max_results: Optional[int] = 100, run_name: Optional[str] = None
    ) -> list[dict]:
        """Return a list of runs for an experiment, most recent first.

        If ``run_name`` is supplied, the returned list is filtered client-side.
        AzureML's MLflow service does not reliably apply a ``mlflow.runName``
        server-side filter to pipeline runs.
        Pass ``None`` for ``max_results`` to retrieve every result page.
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
        runs = []
        page_token = None
        while True:
            body: dict[str, Any] = {
                "experiment_ids": [experiment_id],
                "max_results": 1000,
                "order_by": ["start_time DESC"],
            }
            if page_token:
                body["page_token"] = page_token
            runs_data = self._post("/api/2.0/mlflow/runs/search", body)
            page_runs = runs_data.get("runs", [])
            normalized_runs = (self._normalize_run(run) for run in page_runs)
            if run_name:
                runs.extend(run for run in normalized_runs if run_display_name(run) == run_name)
            else:
                runs.extend(normalized_runs)
            if max_results is not None and len(runs) >= max_results:
                return runs[:max_results]
            page_token = runs_data.get("next_page_token")
            if not page_runs or not page_token:
                break
        return runs[:max_results] if max_results is not None else runs

    def get_run_metrics(self, run_id: str) -> dict[str, float]:
        """Return the final metric values for a single run."""
        data = self._get("/api/2.0/mlflow/runs/get", params={"run_id": run_id})
        run_data = data.get("run", {}).get("data", {})
        # NaN metrics are returned without "value", since JSON has no NaN.
        return {m["key"]: m["value"] for m in run_data.get("metrics", []) if "value" in m}

    def compare_runs(
        self,
        experiment_name: str,
        run_ids: Optional[list[str]] = None,
        run_name: Optional[str] = None,
        child_run_name: Optional[str] = None,
    ) -> list[dict]:
        """Return comparison data for multiple runs in an experiment.

        ``run_ids`` takes precedence over name-based filtering when supplied.
        """
        if run_ids:
            runs = []
            for rid in run_ids:
                data = self._get("/api/2.0/mlflow/runs/get", params={"run_id": rid})
                runs.append(self._normalize_run(data.get("run", {})))
            return runs
        if child_run_name:
            parent_runs = self.get_experiment_runs(experiment_name, max_results=None, run_name=run_name)
            all_runs = self.get_experiment_runs(experiment_name, max_results=None)
            parent_ids = {run["run_id"] for run in parent_runs}
            return _select_child_runs(all_runs, parent_ids, child_run_name)
        return self.get_experiment_runs(experiment_name, max_results=100, run_name=run_name)

    def get_child_runs(
        self,
        experiment_name: str,
        parent_run_id: str,
        child_run_name: Optional[str] = None,
    ) -> list[dict]:
        """Return the child runs of ``parent_run_id``, optionally filtered by display name."""
        runs = self.get_experiment_runs(experiment_name, max_results=None)
        return _select_child_runs(runs, {parent_run_id}, child_run_name)

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

def create_mlflow_client(url: str, token: BearerToken) -> MLFlowBackend:
    """Return an :class:`MLflowRestBackend` for an MLflow tracking URL or URI.

    - ``https://`` or ``http://`` → used as the tracking server root as-is
    - ``azureml://``              → rewritten to ``https://`` (AzureML workspace tracking URI)

    Raises :class:`ValueError` for any other scheme.
    """
    if url.startswith(("http://", "https://")):
        return MLflowRestBackend(url, token)
    if url.startswith("azureml://"):
        return MLflowRestBackend(azureml_uri_to_https(url), token)
    raise ValueError(
        f"mlflow-url must be an https:// MLflow tracking URL or an azureml:// tracking URI, got: {url!r}. "
        "Examples:\n"
        "  https://mlflow.example.com/my-mlflow\n"
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
        with open(env_file, "a", encoding="utf-8") as f:
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
        with open(env_file, "a", encoding="utf-8") as f:
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
