"""
Share operations for Inner Loop Action
"""

import os
import typer
from collections.abc import Callable, Sequence
from typing import Optional, Annotated
from .util import (
    get_new_asset_version,
    get_registry_client,
    get_workspace_client,
    get_yaml_from_folder,
    load_safe_tags,
    empty_string_to_none,
    get_ref_properties,
    github_output
)
from .arm import AssetClient, AssetVersion
from .getasset import (
    getcomponent, 
    getenvironment,
    getmodel,
    getdata,
    next_int_version,
    parse_int_version
)
import tempfile
from azure.ai.ml import load_component
from azure.ai.ml.exceptions import ValidationException
from pathlib import Path
from time import sleep

app = typer.Typer()

_SHARE_VISIBILITY_DEFAULT_TIMEOUT_MINUTES = 5
_SHARE_VISIBILITY_INITIAL_RETRY_DELAYS = (2, 4, 8, 16)
_SHARE_VISIBILITY_MAX_RETRY_DELAY_SECONDS = 30
_MODEL_VERSION_CONFLICT_MESSAGE = "model with this name and version already exists in registry"
_MODEL_VERSION_CONFLICT_RETRIES = 10


def _registry_reference(registry_name: Optional[str], asset_type: str, asset) -> str:
    if not registry_name:
        raise ValueError("registry-name is required for share operations")
    return f"azureml://registries/{registry_name}/{asset_type}/{asset.name}/versions/{asset.version}"


def _share_visibility_retry_delays(
    timeout_minutes: int = _SHARE_VISIBILITY_DEFAULT_TIMEOUT_MINUTES,
) -> tuple[int, ...]:
    if timeout_minutes < 1:
        raise ValueError("timeout-minutes must be at least 1")

    remaining_seconds = timeout_minutes * 60
    retry_delays = []
    for initial_delay in _SHARE_VISIBILITY_INITIAL_RETRY_DELAYS:
        delay = min(initial_delay, remaining_seconds)
        retry_delays.append(delay)
        remaining_seconds -= delay
        if remaining_seconds == 0:
            return tuple(retry_delays)

    while remaining_seconds:
        delay = min(_SHARE_VISIBILITY_MAX_RETRY_DELAY_SECONDS, remaining_seconds)
        retry_delays.append(delay)
        remaining_seconds -= delay

    return tuple(retry_delays)


def _wait_for_shared_asset(
    fetch_versions: Callable[[], list[AssetVersion]],
    asset_type: str,
    asset_name: str,
    asset_version: str | int,
    timeout_minutes: int = _SHARE_VISIBILITY_DEFAULT_TIMEOUT_MINUTES,
    retry_delays: Sequence[int] | None = None,
) -> AssetVersion:
    delays = tuple(retry_delays) if retry_delays is not None else _share_visibility_retry_delays(timeout_minutes)
    for attempt in range(len(delays) + 1):
        versions = fetch_versions()
        if versions:
            return versions[0]
        if attempt < len(delays):
            delay = delays[attempt]
            print(
                f"[share {asset_type}] Registry {asset_type} '{asset_name}' version "
                f"'{asset_version}' is not visible through ARM yet. Retrying in {delay} seconds "
                f"({attempt + 1}/{len(delays)})."
            )
            sleep(delay)

    raise RuntimeError(
        f"Registry {asset_type} '{asset_name}' version '{asset_version}' was not visible through ARM "
        f"after {len(delays) + 1} attempts over {sum(delays)} seconds. "
        "The share may have succeeded; check the Azure ML registry before retrying."
    )


def _share_model_with_version_retry(
    workspace_client,
    workspace_model: AssetVersion,
    registry_name: str,
    initial_version: str,
) -> str:
    target_version = int(initial_version)
    for conflict_attempt in range(_MODEL_VERSION_CONFLICT_RETRIES + 1):
        try:
            workspace_client.models.share(
                name=workspace_model.name,
                version=workspace_model.version,
                registry_name=registry_name,
                share_with_name=workspace_model.name,
                share_with_version=str(target_version),
            )
            return str(target_version)
        except ValidationException as exc:
            is_version_conflict = _MODEL_VERSION_CONFLICT_MESSAGE in str(exc).lower()
            if not is_version_conflict or conflict_attempt == _MODEL_VERSION_CONFLICT_RETRIES:
                raise
            previous_version = target_version
            target_version += 1
            print(
                f"[share model] Registry model '{workspace_model.name}' version '{previous_version}' "
                f"already exists. Retrying with version '{target_version}'."
            )

    raise RuntimeError("Unreachable model share retry state")


@app.command()
def data(
        subscription_id: Annotated[str, typer.Option("--subscription","-s")],
        resource_group: Annotated[str, typer.Option("--resource-group","-g")],
        workspace_name: Annotated[str, typer.Option("--workspace-name","-w")],
        registry_name: Annotated[Optional[str], typer.Option("--registry-name","-r", callback=empty_string_to_none)],
        data_ref: str,
        token: Optional[str] = None,
        expires_on: Optional[int] = None,
        tags: Annotated[
            Optional[str],
            typer.Option(help="string of key=value pairs separated by ,", callback=load_safe_tags),
        ]=None,
        promote_stage: Annotated[Optional[str], typer.Option(callback=empty_string_to_none)] = None,
        timeout_minutes: Annotated[int, typer.Option(min=1)] = _SHARE_VISIBILITY_DEFAULT_TIMEOUT_MINUTES,
    ):
    """Share data asset from workspace to registry"""
    print(f"[share data] Sharing data asset")
    print(f"  Workspace: {workspace_name}")
    print(f"  Registry: {registry_name}")
    print(f"  Data Ref: {data_ref}")
    print(f"  Tags: {tags}")

    d_ref = get_ref_properties(data_ref)
    data_name = d_ref.name
    data_version = d_ref.version

    print("[share data] Creating workspace client")
    ws_client = get_workspace_client(
        subscription_id=subscription_id,
        resource_group=resource_group,
        workspace_name=workspace_name,
        token=token,
        expires_on=expires_on
    )

    print("[share data] Retrieving data asset from workspace")
    ws_assets = AssetClient.for_workspace(
        subscription_id=subscription_id,
        resource_group=resource_group,
        workspace_name=workspace_name,
        token=token,
        expires_on=expires_on
    )
    list_data_ws = getdata(
        client=ws_assets,
        name=data_name,
        tags=tags
    )
    if len(list_data_ws)<1:
        raise ValueError("There is no such data asset in the workspace")
    if len(list_data_ws)>1:
        raise ValueError("Found more than one matching data asset in the workspace") # should never be raised
    ws_data = list_data_ws[0]

    print("[share data] Creating registry client")
    reg_client = get_registry_client(
        registry_name=registry_name,
        token=token,
        expires_on=expires_on
    )
    reg_assets = AssetClient.for_registry(
        registry_name=registry_name,
        subscription_id=subscription_id,
        token=token,
        expires_on=expires_on
    )
    list_data_reg = getdata(
        client=reg_assets,
        name=data_name,
        #tags=tags,
        req_int_version=True
    )
    # find latest registry version to use
    latest_reg_version=0
    if list_data_reg:
        for d in list_data_reg:
            lrv = parse_int_version(d.version)
            if lrv is not None and lrv>latest_reg_version:
                latest_reg_version=lrv
    latest_reg_version=str(latest_reg_version+1)
    
    print("[share data] Sharing data asset to registry")
    ws_client.data.share(
        name=ws_data.name,
        version=ws_data.version,
        registry_name=registry_name,
        share_with_name=ws_data.name,
        share_with_version=latest_reg_version
    )

    print("[share data] Applying stage promotion if provided")
    if promote_stage:
        reg_data = reg_client.data.get(name=data_name,version=latest_reg_version)
        reg_data_tags=reg_data.tags
        if reg_data_tags:
            reg_data_tags.update({'stage':promote_stage})
        else:
            reg_data_tags={'stage':promote_stage}
        reg_data.tags=reg_data_tags
        reg_client.data.create_or_update(reg_data)
    
    data_result = _wait_for_shared_asset(
        lambda: getdata(
            client=reg_assets,
            name=data_name,
            version=latest_reg_version
        ),
        asset_type="data",
        asset_name=data_name,
        asset_version=latest_reg_version,
        timeout_minutes=timeout_minutes,
    )

    print(f"[share data] ✅ Data shared successfully")
    print(f"  Name: {data_result.name}")
    print(f"  Version: {data_result.version}")
    print(f"  Resource ID: {data_result.id}")
    github_output({
        "reference": _registry_reference(registry_name, "data", data_result),
        "version": data_result.version,
        "resource-id":data_result.id
    })


@app.command()
def environment(
        subscription_id: Annotated[str, typer.Option("--subscription","-s")],
        resource_group: Annotated[str, typer.Option("--resource-group","-g")],
        workspace_name: Annotated[str, typer.Option("--workspace-name","-w")],
        registry_name: Annotated[Optional[str], typer.Option("--registry-name","-r", callback=empty_string_to_none)],
        env_ref: str, # Consider renaming this, asset_id, resource_id, asset_uri , etc. 
        token: Optional[str] = None,
        expires_on: Optional[int] = None,
        tags: Annotated[
            Optional[str],
            typer.Option(help="string of key=value pairs separated by ,", callback=load_safe_tags),
        ]=None,
        promote_stage: Annotated[Optional[str], typer.Option(callback=empty_string_to_none)] = None,
        timeout_minutes: Annotated[int, typer.Option(min=1)] = _SHARE_VISIBILITY_DEFAULT_TIMEOUT_MINUTES,
    ):
    """Share environment from workspace to registry"""
    print(f"[share environment] Sharing environment")
    print(f"  Workspace: {workspace_name}")
    print(f"  Registry: {registry_name}")
    print(f"  Environment Ref: {env_ref}")
    print(f"  Tags: {tags}")

    env_name = get_ref_properties(env_ref).name
    env_version = get_ref_properties(env_ref).version

    print("[share environment] Creating workspace client")
    ws_client = get_workspace_client(
        subscription_id=subscription_id,
        resource_group=resource_group,
        workspace_name=workspace_name,
        token=token,
        expires_on=expires_on
    )

    print("[share environment] Retrieving environment from workspace")
    ws_assets = AssetClient.for_workspace(
        subscription_id=subscription_id,
        resource_group=resource_group,
        workspace_name=workspace_name,
        token=token,
        expires_on=expires_on
    )
    list_env_ws = getenvironment(
        client=ws_assets,
        name=env_name,
        version=env_version,
        tags=tags
    )
    if len(list_env_ws)<1:
        raise ValueError("There is no such environment in the workspace")
    if len(list_env_ws)>1:
        raise ValueError("Found more than one matching environment in the workspace") # should never be raised
    ws_env = list_env_ws[0]

    print("[share environment] Creating registry client")
    reg_client = get_registry_client(
        registry_name=registry_name,
        token=token,
        expires_on=expires_on
    )
    reg_assets = AssetClient.for_registry(
        registry_name=registry_name,
        subscription_id=subscription_id,
        token=token,
        expires_on=expires_on
    )
    list_env_reg = getenvironment(
        client=reg_assets,
        name=env_name,
        #tags=tags, # tags may be unique, so DON'T filter with them
        req_int_version=True
    )
    # find latest registry version to use
    latest_reg_version = parse_int_version(ws_env.version)
    if latest_reg_version is None:
        latest_reg_version = 0
    if list_env_reg:
        for e in list_env_reg:
            lrv = parse_int_version(e.version)
            if lrv is not None and lrv>latest_reg_version:
                latest_reg_version=lrv
        latest_reg_version=latest_reg_version+1 # only if name exists
    print("[share environment] Sharing environment to registry")
    ws_client.environments.share(
        name=ws_env.name,
        version=str(ws_env.version),
        registry_name=registry_name,
        share_with_name=ws_env.name,
        share_with_version=f"{latest_reg_version}"
    )

    print("[share environment] Applying stage promotion if provided")
    if promote_stage:
        reg_env = reg_client.environments.get(name=env_name,version=latest_reg_version)
        reg_env_tags=reg_env.tags
        if reg_env_tags:
            reg_env_tags.update({'stage':promote_stage})
        else:
            reg_env_tags={'stage':promote_stage}
        reg_env.tags=reg_env_tags
        reg_client.environments.create_or_update(reg_env)

    environment_result = _wait_for_shared_asset(
        lambda: getenvironment(
            client=reg_assets,
            name=env_name,
            version=latest_reg_version
        ),
        asset_type="environment",
        asset_name=env_name,
        asset_version=latest_reg_version,
        timeout_minutes=timeout_minutes,
    )


    print(f"[share environment] ✅ Environment shared successfully")
    print(f"  Name: {environment_result.name}")
    print(f"  Version: {environment_result.version}")
    print(f"  Resource ID: {environment_result.id}")
    github_output({
        "reference": _registry_reference(registry_name, "environments", environment_result),
        "version": environment_result.version,
        "resource-id":environment_result.id
    })

@app.command()
def model(
        subscription_id: Annotated[str, typer.Option("--subscription","-s")],
        resource_group: Annotated[str, typer.Option("--resource-group","-g")],
        workspace_name: Annotated[str, typer.Option("--workspace-name","-w")],
        registry_name: Annotated[Optional[str], typer.Option("--registry-name","-r", callback=empty_string_to_none)],
        model_ref: str, # Consider renaming this, asset_id, resource_id, asset_uri , etc. 
        token: Optional[str] = None,
        expires_on: Optional[int] = None,
        tags: Annotated[
            Optional[str],
            typer.Option(help="string of key=value pairs separated by ,", callback=load_safe_tags),
        ]=None,
        promote_stage: Annotated[Optional[str], typer.Option(callback=empty_string_to_none)] = None,
        timeout_minutes: Annotated[int, typer.Option(min=1)] = _SHARE_VISIBILITY_DEFAULT_TIMEOUT_MINUTES,
    ):
    """Share model from workspace to registry"""
    if not registry_name:
        raise ValueError("registry-name is required for share operations")

    print(f"[share model] Sharing model")
    print(f"  Subscription: {subscription_id}")
    print(f"  RG (of WS): {resource_group}")
    print(f"  Workspace: {workspace_name}")
    print(f"  Registry: {registry_name}")
    print(f"  Model-ID (of WS): {model_ref}")
    print(f"  Tags: {tags}")

    m_ref = get_ref_properties(model_ref)
    model_name = m_ref.name
    model_version = m_ref.version

    ws_client = get_workspace_client(
        subscription_id=subscription_id,
        resource_group=resource_group,
        workspace_name=workspace_name,
        token=token,
        expires_on=expires_on
    )
    ws_assets = AssetClient.for_workspace(
        subscription_id=subscription_id,
        resource_group=resource_group,
        workspace_name=workspace_name,
        token=token,
        expires_on=expires_on
    )
    list_m_ws = getmodel(ws_assets,name=model_name,tags=tags)
    if len(list_m_ws)<1:
        raise ValueError("There is no such model in the workspace")
    if len(list_m_ws)>1:
        raise ValueError("Found more than one matching model in the workspace") # should never be raised
    ws_model = list_m_ws[0]

    print("[share model] Creating registry client")
    reg_client = get_registry_client(
        registry_name=registry_name,
        token=token,
        expires_on=expires_on
    )
    reg_assets = AssetClient.for_registry(
        registry_name=registry_name,
        subscription_id=subscription_id,
        token=token,
        expires_on=expires_on
    )
    latest_reg_version = next_int_version(
        client=reg_assets,
        kind="model",
        name=model_name,
        subject="share model",
    )

    print("[share model] Sharing model to registry")
    latest_reg_version = _share_model_with_version_retry(
        workspace_client=ws_client,
        workspace_model=ws_model,
        registry_name=registry_name,
        initial_version=latest_reg_version,
    )

    print("[share model] Applying stage promotion if provided")
    if promote_stage:
        reg_model = reg_client.models.get(name=model_name,version=latest_reg_version)
        reg_model_tags=reg_model.tags
        if reg_model_tags:
            reg_model_tags.update({'stage':promote_stage})
        else:
            reg_model_tags={'stage':promote_stage}
        reg_model.tags=reg_model_tags
        reg_client.models.create_or_update(reg_model)

    model_result = _wait_for_shared_asset(
        lambda: getmodel(
            client=reg_assets,
            name=model_name,
            version=latest_reg_version
        ),
        asset_type="model",
        asset_name=model_name,
        asset_version=latest_reg_version,
        timeout_minutes=timeout_minutes,
    )

    print(f"[share model] ✅ Model shared successfully")
    print(f"  Name: {model_result.name}")
    print(f"  Version: {model_result.version}")
    print(f"  Resource ID: {model_result.id}")
    github_output({
        "reference": _registry_reference(registry_name, "models", model_result),
        "version": model_result.version,
        "resource-id":model_result.id
    })

@app.command()
def component(
        subscription_id: Annotated[str, typer.Option("--subscription","-s")],
        resource_group: Annotated[str, typer.Option("--resource-group","-g")],
        workspace_name: Annotated[str, typer.Option("--workspace-name","-w")],
        registry_name: Annotated[Optional[str], typer.Option("--registry-name","-r", callback=empty_string_to_none)],
        component_ref: str, # Consider renaming this, asset_id, resource_id, asset_uri , etc. 
        token: Optional[str] = None,
        expires_on: Optional[int] = None,
        tags: Annotated[
            Optional[str],
            typer.Option(help="string of key=value pairs separated by ,", callback=load_safe_tags),
        ]=None,
        promote_stage: Annotated[Optional[str], typer.Option(callback=empty_string_to_none)] = None,
        timeout_minutes: Annotated[int, typer.Option(min=1)] = _SHARE_VISIBILITY_DEFAULT_TIMEOUT_MINUTES,
    ):
    registry_env_ref = os.environ.get("REGISTRY_ENV_REF")
    if not registry_env_ref or registry_env_ref.strip() == "":
        raise ValueError("registry-env-ref is required for share component operations. ")

    """Share component from workspace to registry"""
    print(f"[share component] Sharing component")
    print(f"  Subscription: {subscription_id}")
    print(f"  RG (of WS): {resource_group}")
    print(f"  Workspace: {workspace_name}")
    print(f"  Registry: {registry_name}")
    print(f"  Component-ID (of WS): {component_ref}")
    print(f"  Components target Environment-ID (in Registry): {registry_env_ref}")
    print(f"  Tags: {tags}")
    print(f"  Promote Stage: {promote_stage}")

    c_ref = get_ref_properties(component_ref)
    component_name = c_ref.name
    component_version = c_ref.version

    ws_client = get_workspace_client(
        subscription_id=subscription_id,
        resource_group=resource_group,
        workspace_name=workspace_name,
        token=token,
        expires_on=expires_on
    )

    ws_assets = AssetClient.for_workspace(
        subscription_id=subscription_id,
        resource_group=resource_group,
        workspace_name=workspace_name,
        token=token,
        expires_on=expires_on
    )
    list_comp_ws = getcomponent(
        client=ws_assets,
        name=component_name,
        version=component_version,
        tags=tags
    )
    if len(list_comp_ws)<1:
        raise ValueError("There is no such component in the workspace")
    if len(list_comp_ws)>1:
        raise ValueError("Found more than one matching component in the workspace") # should never happen
    ws_comp = list_comp_ws[0]

    print("[share component] Creating registry client")
    reg_client = get_registry_client(
        registry_name=registry_name,
        token=token,
        expires_on=expires_on
    )
    reg_assets = AssetClient.for_registry(
        registry_name=registry_name,
        subscription_id=subscription_id,
        token=token,
        expires_on=expires_on
    )

    with tempfile.TemporaryDirectory() as tmpdirname:
        print('Created temporary directory:', tmpdirname)
        ws_client.components.download(name=ws_comp.name, download_path=tmpdirname, version=ws_comp.version)
        path_to_yaml = get_yaml_from_folder(asset_type="component", folder_path=Path(tmpdirname))
        component = load_component(source=path_to_yaml)
        
        merged_tags = component.tags or {}
        if tags:
            merged_tags.update(tags)
        if promote_stage:
            merged_tags.update({'stage':promote_stage})
        component.tags = merged_tags

        component.environment = registry_env_ref

        list_comp_reg = getcomponent(
            client=reg_assets,
            name=component_name,
            req_int_version=True
        )

        # Determine target version number in registry right before sharing
        # to minimize chance of it becoming outdated
        latest_reg_version = 0
        for c in list_comp_reg:
            lrv = parse_int_version(c.version)
            if lrv is not None and lrv>latest_reg_version:
                latest_reg_version=lrv
        latest_reg_version=str(latest_reg_version+1)

        reg_comp = reg_client.components.create_or_update(
            component=component,
            version=latest_reg_version
        )
    
    component_result = _wait_for_shared_asset(
        lambda: getcomponent(
            client=reg_assets,
            name=component_name,
            version=latest_reg_version
        ),
        asset_type="component",
        asset_name=component_name,
        asset_version=latest_reg_version,
        timeout_minutes=timeout_minutes,
    )

    print(f"[share component] ✅ Component shared successfully")
    print(f"  Name: {component_result.name}")
    print(f"  Version: {component_result.version}")
    print(f"  Resource ID: {component_result.id}")
    github_output({
        "reference": _registry_reference(registry_name, "components", component_result),
        "version": component_result.version,
        "resource-id":component_result.id
    })


if __name__ == "__main__":
    app()
