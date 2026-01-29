"""
Share operations for Inner Loop Action
"""

import typer
from typing import Optional, Annotated
from .util import (
    check_and_replace_environment,
    get_new_asset_version,
    get_registry_client,
    get_workspace_client,
    get_yaml_from_folder,
    load_safe_tags,
    empty_string_to_none,
    get_ref_properties,
    github_output
)
from .getasset import (
    getcomponent, 
    getenvironment,
    getmodel,
    getdata
)
import tempfile
from azure.ai.ml import load_component
from pathlib import Path

app = typer.Typer()


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
        image_build_compute: Annotated[Optional[str], typer.Option("--image-build-compute", callback=empty_string_to_none)] = None,
        aml_token: Annotated[Optional[str], typer.Option("--aml-token", callback=empty_string_to_none)] = None,
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
    list_data_ws = getdata(
        client=ws_client,
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
    list_data_reg = getdata(
        client=reg_client,
        name=data_name,
        #tags=tags,
        req_int_version=True
    )
    # find latest registry version to use
    latest_reg_version=0
    if list_data_reg:
        for d in list_data_reg:
            lrv = int(d.version)
            if lrv>latest_reg_version:
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
    
    data_result=getdata(
        client=reg_client,
        name=data_name,
        version=latest_reg_version
    )[0]

    print(f"[share data] ✅ Data shared successfully")
    print(f"  Name: {data_result.name}")
    print(f"  Version: {data_result.version}")
    print(f"  Resource ID: {data_result.id}")
    github_output({
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
        image_build_compute: Annotated[Optional[str], typer.Option("--image-build-compute", callback=empty_string_to_none)] = None,
        aml_token: Annotated[Optional[str], typer.Option("--aml-token", callback=empty_string_to_none)] = None,
    ):
    """Share environment from workspace to registry"""
    print(f"[share environment] Sharing environment")
    print(f"  Workspace: {workspace_name}")
    print(f"  Registry: {registry_name}")
    print(f"  Environment Ref: {env_ref}")
    print(f"  Tags: {tags}")

    env_name = get_ref_properties(env_ref).name

    print("[share environment] Creating workspace client")
    ws_client = get_workspace_client(
        subscription_id=subscription_id,
        resource_group=resource_group,
        workspace_name=workspace_name,
        token=token,
        expires_on=expires_on
    )

    print("[share environment] Retrieving environment from workspace")
    list_env_ws = getenvironment(
        client=ws_client,
        name=env_name,
        #tags=tags, # tags may be unique, so DON'T filter with them
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
    list_env_reg = getenvironment(
        client=reg_client,
        name=env_name,
        #tags=tags, # tags may be unique, so DON'T filter with them
        req_int_version=True
    )
    # find latest registry version to use
    latest_reg_version=ws_env.version # Can cause error if set=0 like the other asset types.
    if list_env_reg:
        for e in list_env_reg:
            lrv = int(e.version)
            if lrv>latest_reg_version:
                latest_reg_version=lrv
        latest_reg_version=str(latest_reg_version+1) # only if name exists
    
    print("[share environment] Sharing environment to registry")
    ws_client.environments.share(
        name=ws_env.name,
        version=ws_env.version,
        registry_name=registry_name,
        share_with_name=ws_env.name,
        share_with_version=latest_reg_version
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

    environment_result = getenvironment(
        client=reg_client,
        name=env_name,
        version=latest_reg_version
    )[0]

    print(f"[share environment] ✅ Environment shared successfully")
    print(f"  Name: {environment_result.name}")
    print(f"  Version: {environment_result.version}")
    print(f"  Resource ID: {environment_result.id}")
    github_output({
        #"reference":f"azureml:{environment_result.name}:{environment_result.version}",
        #"version":environment_result.version,
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
        image_build_compute: Annotated[Optional[str], typer.Option("--image-build-compute", callback=empty_string_to_none)] = None,
        aml_token: Annotated[Optional[str], typer.Option("--aml-token", callback=empty_string_to_none)] = None,
    ):
    """Share model from workspace to registry"""
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
    list_m_ws = getmodel(ws_client,name=model_name,tags=tags)
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
    list_m_reg = getmodel(
        client=reg_client,
        name=model_name,
        #tags=tags,
        req_int_version=True
    )

    # find latest registry version to use
    latest_reg_version=0
    if list_m_reg:
        for m in list_m_reg:
            lrv = int(m.version)
            if lrv>latest_reg_version:
                latest_reg_version=lrv
    latest_reg_version=str(latest_reg_version+1)

    print("[share model] Sharing model to registry")
    ws_client.models.share(
        name=ws_model.name,
        version=ws_model.version,
        registry_name=registry_name,
        share_with_name=ws_model.name,
        share_with_version=latest_reg_version
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

    model_result = getmodel(
        client=reg_client,
        name=model_name,
        version=latest_reg_version
    )[0]

    print(f"[share model] ✅ Model shared successfully")
    print(f"  Name: {model_result.name}")
    print(f"  Version: {model_result.version}")
    print(f"  Resource ID: {model_result.id}")
    github_output({
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
        image_build_compute: Annotated[Optional[str], typer.Option("--image-build-compute", callback=empty_string_to_none)] = None,
        aml_token: Annotated[Optional[str], typer.Option("--aml-token", callback=empty_string_to_none)] = None,
    ):
    """Share component from workspace to registry"""
    print(f"[share component] Sharing component")
    print(f"  Subscription: {subscription_id}")
    print(f"  RG (of WS): {resource_group}")
    print(f"  Workspace: {workspace_name}")
    print(f"  Registry: {registry_name}")
    print(f"  Component-ID (of WS): {component_ref}")
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
    list_comp_ws = getcomponent(client=ws_client,name=component_name)
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
    list_comp_reg = getcomponent(
        client=reg_client,
        name=component_name,
        #tags=tags,
        req_int_version=True
    )

    latest_reg_version=0
    if list_comp_reg:
        for c in list_comp_reg:
            lrv = int(c.version)
            if lrv>latest_reg_version:
                latest_reg_version=lrv
    latest_reg_version=str(latest_reg_version+1)

    with tempfile.TemporaryDirectory() as tmpdirname:
        print('Created temporary directory:', tmpdirname)
        ws_client.components.download(name=ws_comp.name,download_path=tmpdirname,version=ws_comp.version)
        path_to_yaml = get_yaml_from_folder(asset_type="component",folder_path=Path(tmpdirname))
        component = load_component(source=path_to_yaml)
        merged_tags = component.tags or {}
        if tags:
            merged_tags.update(tags)
        if promote_stage:
            merged_tags.update({'stage':promote_stage})
        component.tags = merged_tags

        component.environment = check_and_replace_environment(
            reg_client, component.environment
        )

        reg_comp = reg_client.components.create_or_update(
            component=component,
            version=latest_reg_version
        )
    
    component_result = getcomponent(
        client=reg_client,
        name=component_name,
        version=latest_reg_version
    )[0]

    print(f"[share component] ✅ Component shared successfully")
    print(f"  Name: {component_result.name}")
    print(f"  Version: {component_result.version}")
    print(f"  Resource ID: {component_result.id}")
    github_output({
        "resource-id":component_result.id
    })


if __name__ == "__main__":
    app()
