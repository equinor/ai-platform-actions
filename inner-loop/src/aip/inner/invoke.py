"""Invocation operations for Azure ML deployment validation."""

from typing import Annotated, Optional

import typer
from azure.ai.ml import Input

from .util import empty_string_to_none, get_workspace_client, github_output

app = typer.Typer()


@app.command()
def batch_deployment(
    subscription_id: Annotated[str, typer.Option("--subscription", "-s")],
    resource_group: Annotated[str, typer.Option("--resource-group", "-g")],
    workspace_name: Annotated[str, typer.Option("--workspace-name", "-w")],
    endpoint_name: str,
    deployment_name: Annotated[str, typer.Option("--deployment-name")],
    input_path: Annotated[str, typer.Option("--input-path", envvar="BATCH_INPUT_PATH")],
    input_type: Annotated[str, typer.Option("--input-type", envvar="BATCH_INPUT_TYPE")] = "uri_folder",
    invocation_job_name: Annotated[Optional[str], typer.Option("--invocation-job-name", envvar="BATCH_INVOCATION_JOB_NAME", callback=empty_string_to_none)] = None,
    experiment_name: Annotated[Optional[str], typer.Option("--experiment-name", callback=empty_string_to_none)] = None,
    token: Optional[str] = None,
    expires_on: Annotated[Optional[str], typer.Option("--expires-on", callback=empty_string_to_none)] = None,
    aml_token: Annotated[Optional[str], typer.Option("--aml-token", callback=empty_string_to_none)] = None,
):
    """Invoke one named batch deployment on a pinned validation input."""
    if not input_path:
        raise typer.BadParameter("--input-path is required")
    if input_type not in {"uri_file", "uri_folder"}:
        raise typer.BadParameter("--input-type must be uri_file or uri_folder")

    client = get_workspace_client(
        subscription_id=subscription_id,
        resource_group=resource_group,
        workspace_name=workspace_name,
        token=token,
        expires_on=int(expires_on) if expires_on else None,
        aml_token=aml_token,
    )
    invocation_input = Input(path=input_path, type=input_type)
    invocation = client.batch_endpoints.invoke(
        endpoint_name=endpoint_name,
        deployment_name=deployment_name,
        input=invocation_input,
        job_name=invocation_job_name,
        experiment_name=experiment_name,
    )

    print(
        f"[invoke batch-deployment] Submitted job '{invocation.name}' "
        f"for '{endpoint_name}/{deployment_name}'"
    )
    github_output({
        "reference": f"azureml:{invocation.name}",
        "version": invocation.name,
        "resource-id": getattr(invocation, "id", "") or "",
        "invocation-job-name": invocation.name,
        "status": getattr(invocation, "status", "") or "",
    })