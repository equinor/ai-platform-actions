"""
Share operations for Inner Loop Action
"""

import typer
from typing import Optional
from util import get_workspace_client, get_registry_client

app = typer.Typer()


@app.command()
def data(
    subscription_id: str,
    resource_group: str,
    workspace_name: str,
    registry_name: str,
    data_ref: str,
    token: Optional[str] = None,
    expires_on: Optional[int] = None,
    tags: Optional[str] = None
):
    """Share data asset from workspace to registry"""
    print(f"[share data] Sharing data asset")
    print(f"  Workspace: {workspace_name}")
    print(f"  Registry: {registry_name}")
    print(f"  Data Ref: {data_ref}")
    print(f"  Tags: {tags}")
    
    # Skeleton implementation
    print("[share data] [SKELETON] Creating workspace client")
    print("[share data] [SKELETON] Retrieving data asset from workspace")
    print("[share data] [SKELETON] Creating registry client")
    print("[share data] [SKELETON] Sharing data asset to registry")
    print("[share data] [SKELETON] Applying tags if provided")


@app.command()
def environment(
    subscription_id: str,
    resource_group: str,
    workspace_name: str,
    registry_name: str,
    env_ref: str,
    token: Optional[str] = None,
    expires_on: Optional[int] = None,
    tags: Optional[str] = None
):
    """Share environment from workspace to registry"""
    print(f"[share environment] Sharing environment")
    print(f"  Workspace: {workspace_name}")
    print(f"  Registry: {registry_name}")
    print(f"  Environment Ref: {env_ref}")
    print(f"  Tags: {tags}")
    
    # Skeleton implementation
    print("[share environment] [SKELETON] Creating workspace client")
    print("[share environment] [SKELETON] Retrieving environment from workspace")
    print("[share environment] [SKELETON] Creating registry client")
    print("[share environment] [SKELETON] Sharing environment to registry")
    print("[share environment] [SKELETON] Applying tags if provided")


@app.command()
def component(
    subscription_id: str,
    resource_group: str,
    workspace_name: str,
    registry_name: str,
    component_ref: str,
    token: Optional[str] = None,
    expires_on: Optional[int] = None,
    tags: Optional[str] = None
):
    """Share component from workspace to registry"""
    print(f"[share component] Sharing component")
    print(f"  Workspace: {workspace_name}")
    print(f"  Registry: {registry_name}")
    print(f"  Component Ref: {component_ref}")
    print(f"  Tags: {tags}")
    
    # Skeleton implementation
    print("[share component] [SKELETON] Creating workspace client")
    print("[share component] [SKELETON] Parsing component reference")
    print("[share component] [SKELETON] Retrieving component from workspace")
    print("[share component] [SKELETON] Creating registry client")
    print("[share component] [SKELETON] Sharing component to registry")
    print("[share component] [SKELETON] Applying tags if provided")


if __name__ == "__main__":
    app()
