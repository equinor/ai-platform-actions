"""Invocation operations for Azure ML deployment validation."""

import re
from typing import Annotated, Optional

import typer
from azure.ai.ml import Input

from .util import empty_string_to_none, get_workspace_client, github_output

app = typer.Typer()

JOB_OUTPUT_REFERENCE = re.compile(
    r"^azureml://jobs/(?P<job>[^/]+)/outputs/(?P<output>[^/]+)(?:/paths/(?P<suffix>.*))?/?$",
    re.IGNORECASE,
)
DATASTORE_URI = re.compile(
    r"^azureml://(subscriptions/[^/]+/resource[gG]roups/[^/]+/workspaces/[^/]+/)?datastores/[^/]+/paths/.+",
    re.IGNORECASE,
)
REMOTE_URI_PREFIXES = ("azureml://", "http://", "https://")

SUPPORTED_INPUT_FORMS = (
    "azureml://jobs/<job-name>/outputs/<output-name>",
    "azureml://datastores/<datastore>/paths/<path>",
    "azureml://subscriptions/<sub>/resourcegroups/<rg>/workspaces/<ws>/datastores/<datastore>/paths/<path>",
    "azureml:<data-asset-name>:<version>",
    "azureml:<data-asset-name>@latest",
    "https://<public-uri>",
    "<local-path>",
)


def resolve_job_output_path(client, job_name: str, output_name: str, suffix: Optional[str]) -> str:
    """Translate a job-output reference into the datastore URI that batch invocation accepts."""
    # The SDK rejects azureml://jobs/... paths, so reuse the resolution that jobs.download relies on.
    resolver = getattr(client.jobs, "_get_named_output_uri", None)
    resolved = resolver(job_name, output_name).get(output_name) if resolver else None

    if not resolved:
        job_outputs = getattr(client.jobs.get(job_name), "outputs", None) or {}
        resolved = getattr(job_outputs.get(output_name), "path", None)

    if not resolved:
        raise typer.BadParameter(
            f"Output '{output_name}' of job '{job_name}' has no resolvable storage location. "
            "Confirm the job completed and that the output name matches its definition."
        )

    resolved = resolved.rstrip("/")
    return f"{resolved}/{suffix}" if suffix else resolved


def normalize_input_path(client, input_path: str, input_type: str) -> str:
    """Resolve job-output references and reject URI shapes that batch invocation cannot consume."""
    job_output = JOB_OUTPUT_REFERENCE.match(input_path)
    if job_output:
        input_path = resolve_job_output_path(
            client,
            job_output.group("job"),
            job_output.group("output"),
            job_output.group("suffix"),
        )
    elif input_path.lower().startswith("azureml://") and not DATASTORE_URI.match(input_path):
        supported = "\n  ".join(SUPPORTED_INPUT_FORMS)
        raise typer.BadParameter(
            f"--input-path '{input_path}' is not a URI that a batch endpoint can consume.\n"
            f"Supported forms:\n  {supported}"
        )

    if input_type == "uri_folder" and input_path.lower().startswith(REMOTE_URI_PREFIXES) and not input_path.endswith("/"):
        input_path += "/"
    return input_path


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
    resolved_path = normalize_input_path(client, input_path, input_type)
    if resolved_path != input_path:
        print(f"[invoke batch-deployment] Resolved '{input_path}' to '{resolved_path}'")
    invocation_input = Input(path=resolved_path, type=input_type)
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