"""
Deploy operations for Inner Loop Action
"""
from azure.ai.ml.entities import Environment,BuildContext
from azure.core.polling import LROPoller
import typer
from typing import Annotated, Any, Optional
from util import get_workspace_client, github_output
import yaml
from pathlib import Path
from getasset import getenvironment
import re

app = typer.Typer()

def load_safe_tags(tag: None|str) -> dict[str, str]:
    """
        This method splits a string into key=value pairs.
        Each pair is comma separated.
        This means that the "," should not be used in any key or value,
        and that the "=" should not be used in any key.
        Trailing whitespace in keys, and leading whitespace in values are removed.
    """
    if tag:
        res :dict[str,str] = dict()
        tl = re.split(r",\s+",tag)
        for t in tl:
            kv = re.split(r"\s*=\s*",t,1)
            res.update({kv[0]: kv[1]})
        return res
    else:
        return {}

@app.command()
def data(
    subscription_id: str,
    resource_group: str,
    workspace_name: str,
    filepath: str,
    token: Optional[str] = None,
    expires_on: Optional[int] = None,
    data_type: Optional[str] = None
):
    """Deploy data asset to Azure ML workspace"""
    print(f"[deploy data] Deploying data asset")
    print(f"  Workspace: {workspace_name}")
    print(f"  Resource Group: {resource_group}")
    print(f"  Filepath: {filepath}")
    print(f"  Type: {data_type}")
    
    # Skeleton implementation
    print("[deploy data] [SKELETON] Creating workspace client")
    print("[deploy data] [SKELETON] Loading data configuration from file")
    print("[deploy data] [SKELETON] Creating or updating data asset")
    print("[deploy data] [SKELETON] Returning resource ID")


@app.command()
def environment(
    subscription_id: str,
    resource_group: str,
    workspace_name: str,
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
    
    if True:
        # Load environment configuration from YAML file
        print("[deploy environment] Loading environment configuration from file")
        
        # Get the directory containing the YAML file
        yaml_path = Path(filepath).resolve()
        yaml_dir = yaml_path.parent
        
        with open(yaml_path, "r") as file:
            environment_config = yaml.safe_load(file)
        for key,value in environment_config.items():
            print (f"{key} = {value}")
        if "build" in environment_config:
            # Resolve paths relative to the YAML file's directory
            dockerfile_path = environment_config["build"].get("dockerfile_path", None)
            build_path = environment_config["build"].get("path", None)
            
            if dockerfile_path:
                dockerfile_path = str(yaml_dir / dockerfile_path)
            if build_path:
                build_path = str(yaml_dir / build_path)
            
            build = BuildContext(
                dockerfile_path=dockerfile_path,
                path=build_path
            )
            yaml_tags=environment_config.get("tags")
            tags_to_apply = dict()
            if yaml_tags:
                tags_to_apply.update(yaml_tags)
            if tags:
                tags_to_apply.update(tags)
            environment = Environment(
                name=environment_config["name"],
                build = build,
                tags=tags_to_apply,
                conda_file=environment_config.get("conda_file", None),
                properties=environment_config.get("properties", {}),
                datastore=environment_config.get("datastore",None),
            )
        else:
            environment = Environment(
                name=environment_config["name"],
                description=environment_config.get("description", ""),
                tags=tags_to_apply,
                conda_file=environment_config.get("conda_file", None),
                image=environment_config.get("image", None),
                properties=environment_config.get("properties", {}),
                datastore=environment_config.get("datastore",None),
                #os_type=environment_config.get("os_type", None),
                #python=environment_config.get("python", None),
                #packages=environment_config.get("packages", None),
                #pip_requirements=environment_config.get("pip_requirements", None),
                #environment_variables=environment_config.get("environment_variables", None),
            )

        print(environment)
    
    print("[deploy environment] Creating workspace client")
    client = get_workspace_client(
        subscription_id=subscription_id,
        resource_group=resource_group,
        workspace_name=workspace_name,
        token=token,
        expires_on=expires_on
    )
   
    # Create or update (sync operation)
    environment_result = client.create_or_update(environment)
    
    print(f"[deploy environment] ✓ Environment deployed successfully")
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
    subscription_id: str,
    resource_group: str,
    workspace_name: str,
    filepath: str,
    token: Optional[str] = None,
    expires_on: Optional[int] = None
):
    """Deploy component to Azure ML workspace"""
    print(f"[deploy component] Deploying component")
    print(f"  Workspace: {workspace_name}")
    print(f"  Resource Group: {resource_group}")
    print(f"  Filepath: {filepath}")
    
    yaml_path = Path(filepath).resolve()
    yaml_dir = yaml_path.parent
    with open(yaml_path, "r") as file:
        component_config = yaml.safe_load(file)

    # Note: Handle this in a better way
    component_config['command'] = component_config['command'].replace(" \\\n","").replace("  "," ")
    
    for key,value in component_config.items():
        print (f"{key} = {value}")

    # Skeleton implementation
    print("[deploy component] [SKELETON] Creating workspace client")
    print("[deploy component] [SKELETON] Loading component configuration from file")
    print("[deploy component] [SKELETON] Creating or updating component")
    print("[deploy component] [SKELETON] Returning resource ID")


@app.command()
def job(
    subscription_id: str,
    resource_group: str,
    workspace_name: str,
    filepath: str,
    token: Optional[str] = None,
    expires_on: Optional[int] = None
):
    """Submit job to Azure ML workspace"""
    print(f"[deploy job] Submitting job")
    print(f"  Workspace: {workspace_name}")
    print(f"  Resource Group: {resource_group}")
    print(f"  Filepath: {filepath}")
    
    # Skeleton implementation
    print("[deploy job] [SKELETON] Creating workspace client")
    print("[deploy job] [SKELETON] Loading job configuration from file")
    print("[deploy job] [SKELETON] Submitting job")
    print("[deploy job] [SKELETON] Returning job details")

if __name__ == "__main__":
    app()
