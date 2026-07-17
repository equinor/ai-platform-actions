"""Focused tests for Azure ML batch endpoint lifecycle commands."""

from unittest.mock import MagicMock, patch

import pytest
import typer
from typer.testing import CliRunner

from aip.inner import deploy
from aip.inner.batch import set_default_deployment
from aip.inner import invoke, promote, rollback
from aip.inner.main import app as inner_app

runner = CliRunner()


def test_deploy_batch_endpoint_uses_batch_endpoint_operations():
    endpoint = MagicMock(name="endpoint")
    endpoint.tags = {"existing": "tag"}
    result = MagicMock(name="result")
    result.name = "forecast-batch"
    result.id = "/batchEndpoints/forecast-batch"
    client = MagicMock()
    client.batch_endpoints.begin_create_or_update.return_value.result.return_value = result

    with (
        patch("aip.inner.deploy.load_batch_endpoint", return_value=endpoint),
        patch("aip.inner.deploy.get_workspace_client", return_value=client),
        patch("aip.inner.deploy.github_output") as output,
    ):
        deploy.batch_endpoint(
            "subscription",
            "resource-group",
            "workspace",
            "batch-endpoint.yaml",
            tags={"release": "candidate"},
        )

    client.batch_endpoints.begin_create_or_update.assert_called_once_with(endpoint)
    assert endpoint.tags == {"existing": "tag", "release": "candidate"}
    output.assert_called_once_with({
        "reference": "azureml:forecast-batch",
        "version": "forecast-batch",
        "resource-id": "/batchEndpoints/forecast-batch",
    })


def test_deploy_batch_deployment_uses_versioned_deployment_operations():
    deployment = MagicMock(name="deployment")
    deployment.endpoint_name = "forecast-batch"
    deployment.tags = None
    result = MagicMock(name="result")
    result.name = "candidate-17"
    result.endpoint_name = "forecast-batch"
    result.id = "/batchEndpoints/forecast-batch/deployments/candidate-17"
    client = MagicMock()
    client.batch_deployments.begin_create_or_update.return_value.result.return_value = result

    with (
        patch("aip.inner.deploy.load_batch_deployment", return_value=deployment),
        patch("aip.inner.deploy.get_workspace_client", return_value=client),
        patch("aip.inner.deploy.github_output") as output,
    ):
        deploy.batch_deployment(
            "subscription",
            "resource-group",
            "workspace",
            "batch-deployment.yaml",
            tags={"decision-id": "decision-1"},
        )

    client.batch_deployments.begin_create_or_update.assert_called_once_with(deployment)
    assert deployment.tags == {"decision-id": "decision-1"}
    output.assert_called_once_with({
        "reference": "azureml:forecast-batch/deployments/candidate-17",
        "version": "candidate-17",
        "resource-id": "/batchEndpoints/forecast-batch/deployments/candidate-17",
    })


def test_set_default_deployment_is_idempotent_when_target_is_current():
    endpoint = MagicMock()
    endpoint.defaults = {"deployment_name": "candidate-17"}
    client = MagicMock()
    client.batch_endpoints.get.return_value = endpoint

    result, previous, changed = set_default_deployment(
        client,
        endpoint_name="forecast-batch",
        target_deployment_name="candidate-17",
        expected_current_deployment="production-16",
    )

    assert result is endpoint
    assert previous == "candidate-17"
    assert changed is False
    client.batch_endpoints.begin_create_or_update.assert_not_called()


def test_set_default_deployment_rejects_concurrent_change():
    endpoint = MagicMock()
    endpoint.defaults = {"deployment_name": "unexpected-18"}
    client = MagicMock()
    client.batch_endpoints.get.return_value = endpoint

    with pytest.raises(typer.BadParameter, match="changed concurrently"):
        set_default_deployment(
            client,
            endpoint_name="forecast-batch",
            target_deployment_name="candidate-17",
            expected_current_deployment="production-16",
        )

    client.batch_endpoints.begin_create_or_update.assert_not_called()


def test_set_default_deployment_rejects_unretained_update():
    before = MagicMock()
    before.defaults = {"deployment_name": "production-16"}
    after = MagicMock()
    after.defaults = {"deployment_name": "unexpected-18"}
    client = MagicMock()
    client.batch_endpoints.get.side_effect = [before, after]
    client.batch_endpoints.begin_create_or_update.return_value.result.return_value = after

    with pytest.raises(RuntimeError, match="update was not retained"):
        set_default_deployment(
            client,
            endpoint_name="forecast-batch",
            target_deployment_name="candidate-17",
            expected_current_deployment="production-16",
        )


def test_promote_batch_deployment_records_previous_default():
    endpoint = MagicMock()
    endpoint.defaults = {"deployment_name": "production-16"}
    updated_endpoint = MagicMock()
    updated_endpoint.id = "/batchEndpoints/forecast-batch"
    client = MagicMock()
    client.batch_endpoints.get.return_value = endpoint
    client.batch_endpoints.begin_create_or_update.return_value.result.return_value = updated_endpoint

    with (
        patch("aip.inner.promote.get_workspace_client", return_value=client),
        patch("aip.inner.promote.github_output") as output,
    ):
        promote.batch_deployment(
            "subscription",
            "resource-group",
            "workspace",
            "forecast-batch",
            "candidate-17",
            "production-16",
        )

    client.batch_deployments.get.assert_called_once_with(
        name="candidate-17",
        endpoint_name="forecast-batch",
    )
    assert endpoint.defaults == {"deployment_name": "candidate-17"}
    assert output.call_args.args[0]["previous-deployment-name"] == "production-16"


def test_rollback_batch_deployment_restores_explicit_prior_default():
    with (
        patch("aip.inner.rollback.get_workspace_client", return_value=MagicMock()),
        patch("aip.inner.rollback.set_default_deployment") as switch,
        patch("aip.inner.rollback.github_output"),
    ):
        result = MagicMock()
        result.id = "/batchEndpoints/forecast-batch"
        switch.return_value = (result, "candidate-17", True)
        rollback.batch_deployment(
            "subscription",
            "resource-group",
            "workspace",
            "forecast-batch",
            "production-16",
            "candidate-17",
        )

    switch.assert_called_once_with(
        switch.call_args.args[0],
        endpoint_name="forecast-batch",
        target_deployment_name="production-16",
        expected_current_deployment="candidate-17",
    )


def test_invoke_named_batch_deployment_uses_pinned_input():
    client = MagicMock()
    invocation = MagicMock()
    invocation.name = "validation-job-17"
    invocation.id = "/jobs/validation-job-17"
    invocation.status = "NotStarted"
    client.batch_endpoints.invoke.return_value = invocation
    input_entity = MagicMock()

    with (
        patch("aip.inner.invoke.get_workspace_client", return_value=client),
        patch("aip.inner.invoke.Input", return_value=input_entity) as input_factory,
        patch("aip.inner.invoke.github_output") as output,
    ):
        invoke.batch_deployment(
            "subscription",
            "resource-group",
            "workspace",
            "forecast-batch",
            "candidate-17",
            "azureml:validation-data:4",
            "uri_folder",
            "validation-job-17",
            "batch-validation",
        )

    input_factory.assert_called_once_with(path="azureml:validation-data:4", type="uri_folder")
    client.batch_endpoints.invoke.assert_called_once_with(
        endpoint_name="forecast-batch",
        deployment_name="candidate-17",
        input=input_entity,
        job_name="validation-job-17",
        experiment_name="batch-validation",
    )
    assert output.call_args.args[0]["invocation-job-name"] == "validation-job-17"


def test_action_style_promote_routes_shared_arguments_and_environment():
    endpoint = MagicMock()
    endpoint.defaults = {"deployment_name": "production-16"}
    endpoint.id = "/batchEndpoints/forecast-batch"
    client = MagicMock()
    client.batch_endpoints.get.return_value = endpoint
    client.batch_endpoints.begin_create_or_update.return_value.result.return_value = endpoint

    with (
        patch("aip.inner.promote.get_workspace_client", return_value=client),
        patch("aip.inner.promote.github_output"),
    ):
        result = runner.invoke(
            inner_app,
            [
                "promote", "batch-deployment", "forecast-batch",
                "--subscription", "subscription",
                "--resource-group", "resource-group",
                "--workspace-name", "workspace",
                "--registry-name", "",
                "--token", "",
                "--expires-on", "",
                "--tags", "",
                "--promote-stage", "",
                "--image-build-compute", "",
                "--aml-token", "",
                "--traffic-allocation", "",
                "--schedule-name", "",
                "--cron-expression", "",
                "--time-zone", "",
                "--experiment-name", "",
                "--deployment-name", "candidate-17",
            ],
            env={"EXPECTED_CURRENT_DEPLOYMENT": "production-16"},
        )

    assert result.exit_code == 0, result.output
    assert endpoint.defaults == {"deployment_name": "candidate-17"}