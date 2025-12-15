"""
Deploy operations for Inner Loop Action
"""
from azure.ai.ml import (
    load_data,
    load_environment,
    load_component,
    load_model
)
from azure.ai.ml.entities import (
    CommandComponent,
    Component,
    Data,
    Environment,
    BuildContext,
    Model
)
from azure.core.polling import LROPoller
import typer
from typing import Annotated, Any, Optional
from .util import (
    get_workspace_client, 
    github_output, 
    load_safe_tags
)
import yaml
from pathlib import Path
from .getasset import (
    getcomponent,
    getdata,
    getenvironment,
    getmodel
)
import re

app = typer.Typer()

@app.command()
def data(
        subscription_id: Annotated[str, typer.Option("--subscription","-s")],
        resource_group: Annotated[str, typer.Option("--resource-group","-g")],
        workspace_name: Annotated[str, typer.Option("--workspace-name","-w")],
        filepath: str,
        token: Optional[str] = None,
        expires_on: Optional[int] = None,
        data_type: Optional[str] = None,
        tags: Annotated[
            Optional[str],
            typer.Option(help="Tags in the config file to use", callback=load_safe_tags),
        ]=None
    ):
    """Deploy data asset to Azure ML workspace"""
    print(f"[deploy data] Deploying data asset")
    print(f"  Workspace: {workspace_name}")
    print(f"  Resource Group: {resource_group}")
    print(f"  Filepath: {filepath}")
    print(f"  Type: {data_type}")

    print("[deploy data] Creating workspace client")
    client = get_workspace_client(
        subscription_id=subscription_id,
        resource_group=resource_group,
        workspace_name=workspace_name,
        token=token,
        expires_on=expires_on
    )

    print("[deploy data] Loading data configuration from file")
    data_asset: Data = load_data(source=filepath)
    if tags:
        if data_asset.tags:
            data_asset.tags.update(tags)
        else:
            data_asset.tags = tags
    
    print("[deploy data] Creating or updating data asset")
    data_result = client.data.create_or_update(data_asset)

    print(f"[deploy data] ✅ Data asset deployed successfully")
    print(f"  Name: {data_result.name}")
    print(f"  Version: {data_result.version}")
    print(f"  Resource ID: {data_result.id}")
    github_output({
        "reference":f"azureml:{data_result.name}:{data_result.version}",
        "version":data_result.version,
        "resource-id":data_result.id
    })

@app.command()
def environment(
        subscription_id: Annotated[str, typer.Option("--subscription","-s")],
        resource_group: Annotated[str, typer.Option("--resource-group","-g")],
        workspace_name: Annotated[str, typer.Option("--workspace-name","-w")],
        filepath: str,
        token: Optional[str] = None,
        expires_on: Optional[int] = None,
        tags: Annotated[
            Optional[str],
            typer.Option(help="Tags in the config file to use", callback=load_safe_tags),
        ]=None
    ):
    """Deploy environment to Azure ML workspace"""
    print(f"[deploy environment] Deploying environment")
    print(f"  Workspace: {workspace_name}")
    print(f"  Resource Group: {resource_group}")
    print(f"  Filepath: {filepath}")
    
    print("[deploy environment] Loading environment configuration from file")
    environment = load_environment(source=filepath)
    if tags:
        if environment.tags:
            environment.tags.update(tags)
        else:
            environment.tags = tags  
    
    print("[deploy environment] Creating workspace client")
    client = get_workspace_client(
        subscription_id=subscription_id,
        resource_group=resource_group,
        workspace_name=workspace_name,
        token=token,
        expires_on=expires_on
    )
   
    print("[deploy environment] Creating or updating environment")
    environment_result = client.environments.create_or_update(environment)
    
    print(f"[deploy environment] ✅ Environment deployed successfully")
    print(f"  Name: {environment_result.name}")
    print(f"  Version: {environment_result.version}")
    print(f"  Resource ID: {environment_result.id}")
    github_output({
        "reference":f"azureml:{environment_result.name}:{environment_result.version}",
        "version":environment_result.version,
        "resource-id":environment_result.id
    })


@app.command()
def component(
        subscription_id: Annotated[str, typer.Option("--subscription","-s")],
        resource_group: Annotated[str, typer.Option("--resource-group","-g")],
        workspace_name: Annotated[str, typer.Option("--workspace-name","-w")],
        filepath: str,
        token: Optional[str] = None,
        expires_on: Optional[int] = None,
        tags: Annotated[
            Optional[str],
            typer.Option(help="Tags in the config file to use", callback=load_safe_tags),
        ]=None
    ):
    """Deploy component to Azure ML workspace"""
    print(f"[deploy component] Deploying component")
    print(f"  Workspace: {workspace_name}")
    print(f"  Resource Group: {resource_group}")
    print(f"  Filepath: {filepath}")
    
    print("[deploy component] Loading component configuration from file")
    component = load_component(source=filepath)
    if tags:
        if component.tags:
            component.tags.update(tags)
        else:
            component.tags = tags

    cmd = component.command
    cmd = re.sub(r'\s*[\\]+\s*',' ', cmd)
    cmd = re.sub(r'\s*[\n]\s*', ' ', cmd)
    cmd = re.sub(r'\s+', ' ', cmd)
    cmd = cmd.strip()
    component.command = cmd

    print("[deploy component] Creating workspace client")
    client = get_workspace_client(
        subscription_id=subscription_id,
        resource_group=resource_group,
        workspace_name=workspace_name,
        token=token,
        expires_on=expires_on
    )

    # Due to components being deployed has a "non-standard" version by default,
    # we need to get any existing ones, and update the version ourselves
    list_comp_ws = getcomponent(
        client=client,
        name=component.name
    )

    latest_ws_version=0
    if list_comp_ws:
        for c in list_comp_ws:
            try:
                lrv = int(c.version)
                if lrv>latest_ws_version:
                    latest_ws_version=lrv
            except:
                pass # Ignore non-int versions
    latest_ws_version=str(latest_ws_version+1)

    env_in_component = component.environment
    

    component.version = latest_ws_version
    component_result = client.components.create_or_update(
        component=component,
        version=latest_ws_version
    )
    
    print(f"[deploy component] ✅ Component deployed successfully")
    print(f"  Name: {component_result.name}")
    print(f"  Version: {component_result.version}")
    print(f"  Resource ID: {component_result.id}")
    github_output({
       "reference":f"azureml:{component_result.name}:{component_result.version}",
       "version":component_result.version,
       "resource-id":component_result.id
    })

@app.command()
def job(
        subscription_id: Annotated[str, typer.Option("--subscription","-s")],
        resource_group: Annotated[str, typer.Option("--resource-group","-g")],
        workspace_name: Annotated[str, typer.Option("--workspace-name","-w")],
        filepath: str,
        token: Optional[str] = None,
        expires_on: Optional[int] = None,
        tags: Annotated[
            Optional[str],
            typer.Option(help="Tags in the config file to use", callback=load_safe_tags),
        ]=None
    ):
    """Submit job to Azure ML workspace"""
    print(f"[deploy job] Submitting job")
    print(f"  Workspace: {workspace_name}")
    print(f"  Resource Group: {resource_group}")
    print(f"  Filepath: {filepath}")
    
    print("[deploy job] Creating workspace client")
    client = get_workspace_client(
        subscription_id=subscription_id,
        resource_group=resource_group,
        workspace_name=workspace_name,
        token=token,
        expires_on=expires_on
    )

    print("[deploy job] Loading job configuration from file")
    with open(filepath, "r") as file:
        job_config = yaml.safe_load(file)
    
    print("[deploy job] Submitting job to workspace")
    job_result = client.jobs.create_or_update(job_config)
    
    print(f"[deploy job] ✅ Job submitted successfully")
    print(f"  Name: {job_result.name}")
    print(f"  Status: {job_result.status}")
    print(f"  Resource ID: {job_result.id}")
    github_output({
        "reference":f"azureml:{job_result.name}",
        "version":job_result.name,
        "resource-id":job_result.id
    })

if __name__ == "__main__":
    app()
