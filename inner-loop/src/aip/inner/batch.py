"""Shared Azure ML batch endpoint lifecycle operations."""

from typing import Optional

import typer


def set_default_deployment(
    client,
    *,
    endpoint_name: str,
    target_deployment_name: str,
    expected_current_deployment: Optional[str],
):
    """Set a batch endpoint default with idempotency and optimistic concurrency checks."""
    endpoint = client.batch_endpoints.get(name=endpoint_name)
    current_deployment = (endpoint.defaults or {}).get("deployment_name")

    if current_deployment == target_deployment_name:
        return endpoint, current_deployment, False
    if not expected_current_deployment:
        raise typer.BadParameter(
            "--expected-current-deployment is required when changing a batch endpoint default"
        )
    if current_deployment != expected_current_deployment:
        raise typer.BadParameter(
            f"Batch endpoint '{endpoint_name}' default changed concurrently: "
            f"expected {expected_current_deployment!r}, found {current_deployment!r}"
        )

    client.batch_deployments.get(
        name=target_deployment_name,
        endpoint_name=endpoint_name,
    )
    endpoint.defaults = {"deployment_name": target_deployment_name}
    client.batch_endpoints.begin_create_or_update(endpoint).result()
    verified_endpoint = client.batch_endpoints.get(name=endpoint_name)
    verified_default = (verified_endpoint.defaults or {}).get("deployment_name")
    if verified_default != target_deployment_name:
        raise RuntimeError(
            f"Batch endpoint '{endpoint_name}' default update was not retained: "
            f"expected {target_deployment_name!r}, found {verified_default!r}"
        )
    return verified_endpoint, current_deployment, True