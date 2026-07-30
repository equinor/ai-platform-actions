"""Focused tests for waitfor job authentication routing."""

from unittest.mock import MagicMock, patch

from aip.inner import waitfor


def test_waitfor_job_routes_aml_and_arm_tokens_separately():
    entity = MagicMock()
    entity.name = "training-job"
    client = MagicMock()
    client.jobs.get.return_value = entity

    def complete_wait(**kwargs):
        return kwargs["fetch_entity"](), "completed"

    with (
        patch("aip.inner.waitfor.get_workspace_client", return_value=client) as workspace_client,
        patch("aip.inner.waitfor.TokenManager") as token_manager,
        patch("aip.inner.waitfor._wait_for_asset", side_effect=complete_wait),
        patch("aip.inner.waitfor.github_output"),
    ):
        waitfor.job(
            "subscription",
            "resource-group",
            "workspace",
            "training-job",
            token="arm-token",
            expires_on=1234567890,
            aml_token="aml-token",
        )

    workspace_client.assert_called_once_with(
        subscription_id="subscription",
        resource_group="resource-group",
        workspace_name="workspace",
        token="arm-token",
        expires_on=1234567890,
        aml_token="aml-token",
    )
    token_manager.assert_called_once_with(token="arm-token", expires_on=1234567890)
    client.jobs.get.assert_called_once_with(name="training-job")
