"""Shared Azure ML batch endpoint lifecycle operations."""

from typing import Optional

import typer


def _default_deployment_name(endpoint) -> Optional[str]:
    """Read the default deployment name from either a mapping or a REST BatchEndpointDefaults."""
    defaults = getattr(endpoint, "defaults", None)
    if defaults is None:
        return None
    if isinstance(defaults, dict):
        return defaults.get("deployment_name")
    return getattr(defaults, "deployment_name", None)


def _set_default_deployment_name(endpoint, deployment_name: str) -> None:
    defaults = getattr(endpoint, "defaults", None)
    if defaults is None:
        endpoint.defaults = {"deployment_name": deployment_name}
    elif isinstance(defaults, dict):
        defaults["deployment_name"] = deployment_name
    else:
        defaults.deployment_name = deployment_name


def set_default_deployment(
    client,
    *,
    endpoint_name: str,
    target_deployment_name: str,
    expected_current_deployment: Optional[str],
):
    """Set a batch endpoint default idempotently, verifying the result after update.

    A blank `expected_current_deployment` replaces whatever default is there; supplying it
    turns the update into an optimistic concurrency check.
    """
    endpoint = client.batch_endpoints.get(name=endpoint_name)
    current_deployment = _default_deployment_name(endpoint)

    if current_deployment == target_deployment_name:
        return endpoint, current_deployment, False
    if expected_current_deployment and current_deployment != expected_current_deployment:
        raise typer.BadParameter(
            f"Batch endpoint '{endpoint_name}' default changed concurrently: "
            f"expected {expected_current_deployment!r}, found {current_deployment!r}"
        )

    client.batch_deployments.get(
        name=target_deployment_name,
        endpoint_name=endpoint_name,
    )
    _set_default_deployment_name(endpoint, target_deployment_name)
    client.batch_endpoints.begin_create_or_update(endpoint).result()
    verified_endpoint = client.batch_endpoints.get(name=endpoint_name)
    verified_default = _default_deployment_name(verified_endpoint)
    if verified_default != target_deployment_name:
        raise RuntimeError(
            f"Batch endpoint '{endpoint_name}' default update was not retained: "
            f"expected {target_deployment_name!r}, found {verified_default!r}"
        )
    return verified_endpoint, current_deployment, True