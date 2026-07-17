"""Promotion operations for Azure ML deployments."""

from typing import Annotated, Optional

import typer

from .batch import set_default_deployment
from .util import empty_string_to_none, get_workspace_client, github_output

app = typer.Typer()


@app.command(context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def batch_deployment(
    subscription_id: Annotated[str, typer.Option("--subscription", "-s")],
    resource_group: Annotated[str, typer.Option("--resource-group", "-g")],
    workspace_name: Annotated[str, typer.Option("--workspace-name", "-w")],
    endpoint_name: str,
    deployment_name: Annotated[str, typer.Option("--deployment-name")],
    expected_current_deployment: Annotated[Optional[str], typer.Option("--expected-current-deployment", envvar="EXPECTED_CURRENT_DEPLOYMENT", callback=empty_string_to_none)] = None,
    token: Optional[str] = None,
    expires_on: Annotated[Optional[str], typer.Option("--expires-on", callback=empty_string_to_none)] = None,
    aml_token: Annotated[Optional[str], typer.Option("--aml-token", callback=empty_string_to_none)] = None,
):
    """Promote a batch deployment with guarded and verified default switching."""
    client = get_workspace_client(
        subscription_id=subscription_id,
        resource_group=resource_group,
        workspace_name=workspace_name,
        token=token,
        expires_on=int(expires_on) if expires_on else None,
        aml_token=aml_token,
    )
    result, previous_deployment, changed = set_default_deployment(
        client,
        endpoint_name=endpoint_name,
        target_deployment_name=deployment_name,
        expected_current_deployment=expected_current_deployment,
    )

    print(
        f"[promote batch-deployment] Default for '{endpoint_name}': "
        f"'{previous_deployment}' -> '{deployment_name}' (changed={changed})"
    )
    github_output({
        "reference": f"azureml:{endpoint_name}/deployments/{deployment_name}",
        "version": deployment_name,
        "resource-id": getattr(result, "id", "") or "",
        "previous-deployment-name": previous_deployment or "",
        "default-deployment-name": deployment_name,
        "changed": str(changed).lower(),
    })