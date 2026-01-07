"""
Wait-for operations for Inner Loop Action.
"""

import time
from typing import Annotated, Callable, Optional, Any

import typer
from azure.core.exceptions import HttpResponseError, ResourceNotFoundError

from .util import (
    get_workspace_client,
    load_safe_tags,
    empty_string_to_none,
    get_ref_properties,
    github_output,
)

POLL_INTERVAL_SECONDS = 10
TIMEOUT_SECONDS = 30 * 60
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

app = typer.Typer()


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
) -> tuple[Any, Optional[str]]:
    start = time.monotonic()
    attempt = 0
    while True:
        attempt += 1
        elapsed = time.monotonic() - start
        remaining = TIMEOUT_SECONDS - elapsed
        if remaining <= 0:
            print(f"[waitfor {subject}] ❌ Timed out after {TIMEOUT_SECONDS // 60} minutes.")
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

    entity, final_state = _wait_for_asset(
        subject="data",
        fetch_entity=lambda: client.data.get(name=data_props.name, version=data_version),
        tags=tags,
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

    entity, final_state = _wait_for_asset(
        subject="environment",
        fetch_entity=lambda: client.environments.get(name=env_props.name, version=env_version),
        tags=tags,
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

    entity, final_state = _wait_for_asset(
        subject="component",
        fetch_entity=lambda: client.components.get(name=comp_props.name, version=comp_version),
        tags=tags,
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

    entity, final_state = _wait_for_asset(
        subject="model",
        fetch_entity=lambda: client.models.get(name=model_props.name, version=model_version),
        tags=tags,
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
):
    print(f"[waitfor job] Waiting for job {job_name}")

    client = get_workspace_client(
        subscription_id=subscription_id,
        resource_group=resource_group,
        workspace_name=workspace_name,
        token=token,
        expires_on=expires_on,
    )

    entity, final_state = _wait_for_asset(
        subject="job",
        fetch_entity=lambda: client.jobs.get(name=job_name),
        tags=tags,
    )

    if final_state not in SUCCESS_STATES:
        print(f"[waitfor job] ❌ Job reached terminal state '{final_state}'.")
        raise typer.Exit(code=1)

    print(f"[waitfor job] ✅ Job '{entity.name}' completed with state '{final_state}'.")
    _emit_github_output(entity)


if __name__ == "__main__":
    app()
