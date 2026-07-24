"""Focused tests for deploy versioning behavior."""

from unittest.mock import MagicMock, patch

from aip.inner import deploy


def _mock_data_result(name: str, version: str, resource_id: str) -> MagicMock:
    result = MagicMock(name="data_result")
    result.name = name
    result.version = version
    result.id = resource_id
    return result


def test_deploy_data_uses_next_integer_version_from_workspace_assets():
    data_asset = MagicMock(name="data_asset")
    data_asset.name = "training-data"
    data_asset.tags = None

    existing_v3 = MagicMock(name="existing_v3")
    existing_v3.version = "3"
    existing_v7 = MagicMock(name="existing_v7")
    existing_v7.version = "7"

    client = MagicMock(name="client")
    client.data.create_or_update.return_value = _mock_data_result(
        "training-data",
        "8",
        "/data/training-data/versions/8",
    )

    with (
        patch("aip.inner.deploy.get_workspace_client", return_value=client),
        patch("aip.inner.deploy.load_data", return_value=data_asset),
        patch("aip.inner.deploy.getdata", return_value=[existing_v3, existing_v7]),
        patch("aip.inner.deploy.github_output"),
    ):
        deploy.data(
            "subscription",
            "resource-group",
            "workspace",
            "data.yaml",
        )

    assert data_asset.version == "8"
    client.data.create_or_update.assert_called_once_with(
        data=data_asset,
    )
    assert "version" not in client.data.create_or_update.call_args.kwargs


def test_deploy_data_ignores_non_integer_versions_when_bumping():
    data_asset = MagicMock(name="data_asset")
    data_asset.name = "training-data"
    data_asset.tags = None

    existing_non_int = MagicMock(name="existing_non_int")
    existing_non_int.version = "v-next"
    existing_v2 = MagicMock(name="existing_v2")
    existing_v2.version = "2"

    client = MagicMock(name="client")
    client.data.create_or_update.return_value = _mock_data_result(
        "training-data",
        "3",
        "/data/training-data/versions/3",
    )

    with (
        patch("aip.inner.deploy.get_workspace_client", return_value=client),
        patch("aip.inner.deploy.load_data", return_value=data_asset),
        patch("aip.inner.deploy.getdata", return_value=[existing_non_int, existing_v2]),
        patch("aip.inner.deploy.github_output"),
    ):
        deploy.data(
            "subscription",
            "resource-group",
            "workspace",
            "data.yaml",
        )

    assert data_asset.version == "3"
    client.data.create_or_update.assert_called_once_with(
        data=data_asset,
    )
    assert "version" not in client.data.create_or_update.call_args.kwargs


def test_deploy_data_starts_at_one_when_no_prior_assets_exist():
    data_asset = MagicMock(name="data_asset")
    data_asset.name = "training-data" 
    data_asset.tags = None

    client = MagicMock(name="client")
    client.data.create_or_update.return_value = _mock_data_result(
        "training-data",
        "1",
        "/data/training-data/versions/1",
    )

    with (
        patch("aip.inner.deploy.get_workspace_client", return_value=client),
        patch("aip.inner.deploy.load_data", return_value=data_asset),
        patch("aip.inner.deploy.getdata", return_value=None),
        patch("aip.inner.deploy.github_output"),
    ):
        deploy.data(
            "subscription",
            "resource-group",
            "workspace",
            "data.yaml",
        )

    assert data_asset.version == "1"
    client.data.create_or_update.assert_called_once_with(
        data=data_asset,
    )
    assert "version" not in client.data.create_or_update.call_args.kwargs
