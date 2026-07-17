"""
Rollback operations for Inner Loop Action.

Verbs:
  rollback online-deployment — swap traffic to the previous known-good deployment (US10)
"""

import sys
from typing import Annotated, Optional

import typer

from .util import (
    empty_string_to_none,
    get_workspace_client,
    github_output,
    load_safe_tags,
)
from .batch import set_default_deployment

app = typer.Typer()


@app.command(context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def batch_deployment(
        subscription_id: Annotated[str, typer.Option("--subscription", "-s")],
        resource_group: Annotated[str, typer.Option("--resource-group", "-g")],
        workspace_name: Annotated[str, typer.Option("--workspace-name", "-w")],
        endpoint_name: str,
        previous_deployment_name: Annotated[Optional[str], typer.Option("--deployment-name", callback=empty_string_to_none)] = None,
        expected_current_deployment: Annotated[Optional[str], typer.Option("--expected-current-deployment", envvar="EXPECTED_CURRENT_DEPLOYMENT", callback=empty_string_to_none)] = None,
        token: Optional[str] = None,
        expires_on: Annotated[Optional[str], typer.Option("--expires-on", callback=empty_string_to_none)] = None,
        aml_token: Annotated[Optional[str], typer.Option("--aml-token", callback=empty_string_to_none)] = None,
    ):
    """Restore the exact prior default deployment recorded before batch promotion."""
    if not previous_deployment_name:
        raise typer.BadParameter("--deployment-name must identify the recorded prior deployment")

    client = get_workspace_client(
        subscription_id=subscription_id,
        resource_group=resource_group,
        workspace_name=workspace_name,
        token=token,
        expires_on=int(expires_on) if expires_on else None,
        aml_token=aml_token,
    )
    result, replaced_deployment, changed = set_default_deployment(
        client,
        endpoint_name=endpoint_name,
        target_deployment_name=previous_deployment_name,
        expected_current_deployment=expected_current_deployment,
    )

    print(
        f"[rollback batch-deployment] Default for '{endpoint_name}': "
        f"'{replaced_deployment}' -> '{previous_deployment_name}' (changed={changed})"
    )
    github_output({
        "reference": f"azureml:{endpoint_name}/deployments/{previous_deployment_name}",
        "version": previous_deployment_name,
        "resource-id": getattr(result, "id", "") or "",
        "replaced-deployment-name": replaced_deployment or "",
        "default-deployment-name": previous_deployment_name,
        "changed": str(changed).lower(),
    })


@app.command()
def online_deployment(
        subscription_id: Annotated[str, typer.Option("--subscription", "-s")],
        resource_group: Annotated[str, typer.Option("--resource-group", "-g")],
        workspace_name: Annotated[str, typer.Option("--workspace-name", "-w")],
        endpoint_name: str,
        token: Optional[str] = None,
        expires_on: Optional[int] = None,
        aml_token: Annotated[Optional[str], typer.Option("--aml-token", callback=empty_string_to_none)] = None,
        previous_deployment_name: Annotated[Optional[str], typer.Option("--deployment-name", callback=empty_string_to_none)] = None,
        tags: Annotated[
            Optional[str],
            typer.Option(help="Tags in the config file to use", callback=load_safe_tags),
        ] = None,
        # passthrough args for GitHub Actions interface
        registry_name: Annotated[Optional[str], typer.Option("--registry-name", callback=empty_string_to_none)] = None,
        promote_stage: Annotated[Optional[str], typer.Option("--promote-stage", callback=empty_string_to_none)] = None,
        image_build_compute: Annotated[Optional[str], typer.Option("--image-build-compute", callback=empty_string_to_none)] = None,
        traffic_allocation: Annotated[Optional[str], typer.Option("--traffic-allocation", callback=empty_string_to_none)] = None,
        schedule_name: Annotated[Optional[str], typer.Option("--schedule-name")] = None,
        cron_expression: Annotated[Optional[str], typer.Option("--cron-expression")] = None,
        time_zone: Annotated[Optional[str], typer.Option("--time-zone")] = None,
    ):
    """Roll back an online endpoint to its previous deployment (US10 — Rollback and Retirement).

    Shifts 100% of traffic to the target deployment. If --deployment-name is not
    supplied, the deployment with the second-highest creation time (i.e. the one
    before the current primary) is selected automatically.

    The rollback is logged as GitHub step output for audit purposes.
    """
    print(f"[rollback online-deployment] Rolling back endpoint: {endpoint_name}")
    print(f"  Workspace: {workspace_name}")
    print(f"  Resource Group: {resource_group}")

    client = get_workspace_client(
        subscription_id=subscription_id,
        resource_group=resource_group,
        workspace_name=workspace_name,
        token=token,
        expires_on=expires_on,
        aml_token=aml_token
    )

    endpoint = client.online_endpoints.get(name=endpoint_name)
    current_traffic: dict[str, int] = endpoint.traffic or {}

    # Identify the current primary deployment (highest traffic share)
    if current_traffic:
        current_primary = max(current_traffic, key=lambda d: current_traffic[d])
    else:
        current_primary = None
    print(f"  Current primary deployment: {current_primary or '(none)'}")

    if previous_deployment_name:
        target = previous_deployment_name
        print(f"  Target deployment (explicit): {target}")
    else:
        # Auto-detect: list deployments ordered by creation time, pick the most recent
        # one that is NOT the current primary
        deployments = sorted(
            client.online_deployments.list(endpoint_name=endpoint_name),
            key=lambda d: getattr(d, "creation_context", None) and
                          getattr(d.creation_context, "created_at", None) or "",
            reverse=True,
        )
        candidates = [d.name for d in deployments if d.name != current_primary]
        if not candidates:
            print(
                f"[rollback online-deployment] ERROR: No previous deployment found on endpoint '{endpoint_name}'",
                file=sys.stderr,
            )
            raise typer.Exit(1)
        target = candidates[0]
        print(f"  Target deployment (auto-detected): {target}")

    # Shift 100% traffic to target
    new_traffic = {target: 100}
    # Zero out all others
    for d in current_traffic:
        if d != target:
            new_traffic[d] = 0

    print(f"[rollback online-deployment] Updating traffic: {new_traffic}")
    endpoint.traffic = new_traffic
    poller = client.online_endpoints.begin_create_or_update(endpoint)
    poller.result()

    print(f"[rollback online-deployment] ✅ Rollback complete — 100% traffic → '{target}'")
    github_output({
        "reference": f"azureml:{endpoint_name}/deployments/{target}",
        "version": target,
        "resource-id": endpoint.id or "",
    })
