"""
Delete operations for Inner Loop Action
"""

import typer
from typing import Annotated, Optional

from .util import (
    get_workspace_client,
    github_output,
    empty_string_to_none,
    get_deployment_ref_properties,
)

app = typer.Typer()


@app.command()
def online_endpoint(
    subscription_id: Annotated[str, typer.Option("--subscription", "-s")],
    resource_group: Annotated[str, typer.Option("--resource-group", "-g")],
    workspace_name: Annotated[str, typer.Option("--workspace-name", "-w")],
    endpoint_name: str,
    token: Optional[str] = None,
    expires_on: Optional[int] = None,
    registry_name: Annotated[Optional[str], typer.Option("--registry-name", callback=empty_string_to_none)] = None,
    promote_stage: Annotated[Optional[str], typer.Option("--promote-stage", callback=empty_string_to_none)] = None,
    image_build_compute: Annotated[Optional[str], typer.Option("--image-build-compute", callback=empty_string_to_none)] = None,
    aml_token: Annotated[Optional[str], typer.Option("--aml-token", callback=empty_string_to_none)] = None,
    traffic_allocation: Annotated[Optional[str], typer.Option("--traffic-allocation", callback=empty_string_to_none)] = None,
):
    """Delete an online endpoint from Azure ML workspace.
    https://learn.microsoft.com/en-us/azure/machine-learning/how-to-deploy-online-endpoints?view=azureml-api-2
    """
    print(f"[delete online-endpoint] Deleting online endpoint")
    print(f"  Workspace: {workspace_name}")
    print(f"  Resource Group: {resource_group}")
    print(f"  Endpoint: {endpoint_name}")

    print("[delete online-endpoint] Creating workspace client")
    client = get_workspace_client(
        subscription_id=subscription_id,
        resource_group=resource_group,
        workspace_name=workspace_name,
        token=token,
        expires_on=expires_on,
    )

    print("[delete online-endpoint] Initiating endpoint deletion")
    poller = client.online_endpoints.begin_delete(name=endpoint_name)
    poller.result()

    print(f"[delete online-endpoint] ✅ Online endpoint '{endpoint_name}' deleted successfully")
    github_output({
        "deleted": "true",
        "endpoint-name": endpoint_name,
    })


@app.command()
def online_deployment(
    subscription_id: Annotated[str, typer.Option("--subscription", "-s")],
    resource_group: Annotated[str, typer.Option("--resource-group", "-g")],
    workspace_name: Annotated[str, typer.Option("--workspace-name", "-w")],
    deployment_resource: str,
    token: Optional[str] = None,
    expires_on: Optional[int] = None,
    registry_name: Annotated[Optional[str], typer.Option("--registry-name", callback=empty_string_to_none)] = None,
    promote_stage: Annotated[Optional[str], typer.Option("--promote-stage", callback=empty_string_to_none)] = None,
    image_build_compute: Annotated[Optional[str], typer.Option("--image-build-compute", callback=empty_string_to_none)] = None,
    aml_token: Annotated[Optional[str], typer.Option("--aml-token", callback=empty_string_to_none)] = None,
    traffic_allocation: Annotated[Optional[str], typer.Option("--traffic-allocation", callback=empty_string_to_none)] = None,
):
    """Delete an online deployment from Azure ML workspace.
    https://learn.microsoft.com/en-us/azure/machine-learning/how-to-deploy-online-endpoints?view=azureml-api-2
    """
    deployment_ref = get_deployment_ref_properties(deployment_resource)
    endpoint_name = deployment_ref.endpoint_name
    deployment_name = deployment_ref.deployment_name

    print(f"[delete online-deployment] Deleting online deployment")
    print(f"  Workspace: {workspace_name}")
    print(f"  Resource Group: {resource_group}")
    print(f"  Endpoint: {endpoint_name}")
    print(f"  Deployment: {deployment_name}")

    print("[delete online-deployment] Creating workspace client")
    client = get_workspace_client(
        subscription_id=subscription_id,
        resource_group=resource_group,
        workspace_name=workspace_name,
        token=token,
        expires_on=expires_on,
    )

    print("[delete online-deployment] Checking endpoint traffic allocation")
    endpoint = client.online_endpoints.get(name=endpoint_name)
    if endpoint.traffic and deployment_name in endpoint.traffic:
        current_traffic = endpoint.traffic[deployment_name]
        if current_traffic > 0:
            print(f"[delete online-deployment] Removing traffic from deployment before deletion")
            endpoint.traffic[deployment_name] = 0
            poller = client.online_endpoints.begin_create_or_update(endpoint)
            poller.result()
            print(f"  Traffic removed from '{deployment_name}'")

    print("[delete online-deployment] Initiating deployment deletion")
    poller = client.online_deployments.begin_delete(
        endpoint_name=endpoint_name,
        name=deployment_name,
    )
    poller.result()

    print(f"[delete online-deployment] ✅ Deployment '{deployment_name}' on endpoint '{endpoint_name}' deleted successfully")
    github_output({
        "deleted": "true",
        "endpoint-name": endpoint_name,
        "deployment-name": deployment_name,
    })


if __name__ == "__main__":
    app()
