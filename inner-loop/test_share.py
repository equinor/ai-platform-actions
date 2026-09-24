"""Tests for shared asset visibility retries."""

from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import pytest
from azure.ai.ml.exceptions import ValidationException

from aip.inner.arm import AssetContainer, AssetVersion
from aip.inner import share
from aip.inner.share import _wait_for_shared_asset


def test_share_model_increments_existing_registry_version():
    workspace_client = MagicMock()
    workspace_assets = MagicMock()
    registry_assets = MagicMock()
    workspace_model = AssetVersion(name="my-model", version="16")
    existing_registry_model = AssetVersion(name="my-model", version="1")
    shared_registry_model = AssetVersion(name="my-model", version="2", id="registry-id")
    registry_assets.get_container.return_value = AssetContainer(name="my-model")
    registry_assets.list_versions.return_value = [existing_registry_model]

    with (
        patch.object(share, "get_ref_properties", return_value=SimpleNamespace(name="my-model", version="16")),
        patch.object(share, "get_workspace_client", return_value=workspace_client),
        patch.object(share.AssetClient, "for_workspace", return_value=workspace_assets),
        patch.object(share.AssetClient, "for_registry", return_value=registry_assets),
        patch.object(share, "get_registry_client"),
        patch.object(share, "getmodel", return_value=[workspace_model]),
        patch.object(share, "_wait_for_shared_asset", return_value=shared_registry_model),
        patch.object(share, "github_output"),
    ):
        share.model("subscription", "resource-group", "workspace", "registry", "azureml:my-model:16")

    registry_assets.list_versions.assert_called_once_with("model", "my-model", list_view_type="All")
    workspace_client.models.share.assert_called_once_with(
        name="my-model",
        version="16",
        registry_name="registry",
        share_with_name="my-model",
        share_with_version="2",
    )


def test_share_model_retries_a_registry_version_conflict():
    workspace_client = MagicMock()
    workspace_model = AssetVersion(name="my-model", version="16")
    conflict = ValidationException(
        message="A model with this name and version already exists in registry",
        no_personal_data_message="A model with this name and version already exists in registry",
    )
    workspace_client.models.share.side_effect = [conflict, None]

    version = share._share_model_with_version_retry(
        workspace_client=workspace_client,
        workspace_model=workspace_model,
        registry_name="registry",
        initial_version="2",
    )

    assert version == "3"
    assert workspace_client.models.share.call_args_list == [
        call(
            name="my-model",
            version="16",
            registry_name="registry",
            share_with_name="my-model",
            share_with_version="2",
        ),
        call(
            name="my-model",
            version="16",
            registry_name="registry",
            share_with_name="my-model",
            share_with_version="3",
        ),
    ]


def test_wait_for_shared_asset_retries_until_visible():
    asset = AssetVersion(name="my-model", version="7")
    fetch_versions = MagicMock(side_effect=[[], [], [asset]])

    with patch("aip.inner.share.sleep") as sleep_mock:
        result = _wait_for_shared_asset(
            fetch_versions,
            asset_type="model",
            asset_name="my-model",
            asset_version="7",
            retry_delays=(2, 4),
        )

    assert result is asset
    assert fetch_versions.call_count == 3
    assert sleep_mock.call_args_list == [call(2), call(4)]


def test_wait_for_shared_asset_raises_clear_error_after_retries():
    fetch_versions = MagicMock(return_value=[])

    with patch("aip.inner.share.sleep"), pytest.raises(
        RuntimeError,
        match=(
            "Registry model 'my-model' version '7' was not visible through ARM "
            "after 3 attempts over 6 seconds"
        ),
    ):
        _wait_for_shared_asset(
            fetch_versions,
            asset_type="model",
            asset_name="my-model",
            asset_version="7",
            retry_delays=(2, 4),
        )

    assert fetch_versions.call_count == 3