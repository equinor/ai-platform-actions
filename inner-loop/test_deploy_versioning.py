"""Focused tests for deploy versioning behavior."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from azure.ai.ml.entities import Model

from aip.inner import deploy
from aip.inner.arm import AssetClient, TokenManager


@pytest.mark.parametrize("artifact_kind", ["file", "folder", "mlflow"])
def test_deploy_model_downloads_registry_artifact_before_registration(artifact_kind):
    source = "azureml://registries/shared/models/source-model/versions/8"
    model = Model(
        name="destination-model", version="3", path=source,
        type="mlflow_model" if artifact_kind == "mlflow" else "custom_model",
        tags={"existing": "tag"}, description="Destination description",
    )
    workspace_client = MagicMock()
    registry_client = MagicMock()
    download_paths = []

    def download(*, name, version, download_path):
        assert (name, version) == ("source-model", "8")
        download_paths.append(Path(download_path))
        wrapper = Path(download_path, name)
        wrapper.mkdir()
        if artifact_kind == "file":
            (wrapper / "model.pkl").write_bytes(b"model")
        else:
            root = wrapper / "original-folder"
            root.mkdir()
            (root / "model.pkl").write_bytes(b"model")
            if artifact_kind == "mlflow":
                (root / "MLmodel").write_text("flavors: {}", encoding="utf-8")

    def register(asset):
        root = Path(asset.path)
        assert root.is_absolute()
        assert root.name == ("model.pkl" if artifact_kind == "file" else "original-folder")
        assert (root if artifact_kind == "file" else root / "model.pkl").read_bytes() == b"model"
        if artifact_kind == "mlflow":
            assert (root / "MLmodel").is_file()
        assert asset.name == "destination-model"
        assert asset.version == "3"
        assert asset.type == ("mlflow_model" if artifact_kind == "mlflow" else "custom_model")
        assert asset.description == "Destination description"
        assert asset.tags == {"existing": "tag", "stage": "dev"}
        return Model(name=asset.name, version=asset.version, id="/workspace/model/3")

    registry_client.models.download.side_effect = download
    workspace_client.models.create_or_update.side_effect = register
    with (
        patch("aip.inner.deploy.load_model", return_value=model),
        patch("aip.inner.deploy.get_workspace_client", return_value=workspace_client) as workspace_factory,
        patch("aip.inner.deploy.get_registry_client", return_value=registry_client) as registry_factory,
        patch("aip.inner.deploy.github_output") as output,
    ):
        deploy.model(
            "subscription", "resource-group", "workspace", "model.yaml",
            token="arm-token", expires_on=123, aml_token="aml-token",
            storage_token="storage-token", tags={"stage": "dev"},
        )
    registry_factory.assert_called_once_with(
        registry_name="shared", token="arm-token", expires_on=123,
        aml_token="aml-token", storage_token="storage-token",
    )
    workspace_factory.assert_called_once_with(
        subscription_id="subscription", resource_group="resource-group", workspace_name="workspace",
        token="arm-token", expires_on=123, aml_token="aml-token", storage_token="storage-token",
    )
    assert model.path == source
    assert len(download_paths) == 1
    assert not download_paths[0].exists()
    output.assert_called_once_with({
        "reference": "azureml:destination-model:3", "version": "3", "resource-id": "/workspace/model/3",
    })


@pytest.mark.parametrize("failure", ["download", "upload", "missing", "empty", "ambiguous"])
def test_deploy_model_cleans_registry_download_on_failure(failure):
    source = "azureml://registries/shared/models/source-model/versions/8"
    model = Model(name="destination-model", version="3", path=source)
    registry_client = MagicMock()
    workspace_client = MagicMock()
    download_paths = []

    def download(*, name, version, download_path):
        download_paths.append(Path(download_path))
        wrapper = Path(download_path, name)
        if failure == "missing":
            return
        wrapper.mkdir()
        if failure == "empty":
            (wrapper / "empty-folder").mkdir()
            return
        (wrapper / "model.pkl").write_bytes(b"model")
        if failure == "ambiguous":
            (wrapper / "other.pkl").write_bytes(b"other")
        if failure == "download":
            raise RuntimeError("download failed")

    registry_client.models.download.side_effect = download
    workspace_client.models.create_or_update.side_effect = RuntimeError("upload failed")
    expected = {
        "download": "download failed", "upload": "upload failed",
        "missing": "exactly one artifact", "empty": "contains no files",
        "ambiguous": "exactly one artifact",
    }
    with (
        patch("aip.inner.deploy.load_model", return_value=model),
        patch("aip.inner.deploy.get_workspace_client", return_value=workspace_client),
        patch("aip.inner.deploy.get_registry_client", return_value=registry_client),
        patch("aip.inner.deploy.github_output") as output,
        pytest.raises(RuntimeError, match=expected[failure]),
    ):
        deploy.model("subscription", "resource-group", "workspace", "model.yaml")

    assert len(download_paths) == 1
    assert not download_paths[0].exists()
    assert model.path == source
    if failure == "upload":
        workspace_client.models.create_or_update.assert_called_once_with(model)
    else:
        workspace_client.models.create_or_update.assert_not_called()
    output.assert_not_called()


@pytest.mark.parametrize("source", [
    "./local-model", "azureml://jobs/train/outputs/model",
    "azureml://datastores/workspaceblobstore/paths/model", "https://example.blob.core.windows.net/models/model",
])
def test_deploy_model_leaves_non_registry_paths_unchanged(source):
    model = Model(name="destination-model", version="3", path=source)
    loaded_path = model.path
    workspace_client = MagicMock()
    workspace_client.models.create_or_update.return_value = model
    with (
        patch("aip.inner.deploy.load_model", return_value=model),
        patch("aip.inner.deploy.get_workspace_client", return_value=workspace_client),
        patch("aip.inner.deploy.get_registry_client") as registry_factory,
        patch("aip.inner.deploy.github_output"),
    ):
        deploy.model("subscription", "resource-group", "workspace", "model.yaml")
    workspace_client.models.create_or_update.assert_called_once_with(model)
    registry_factory.assert_not_called()
    assert model.path == loaded_path


@pytest.mark.parametrize("source", [
    "azureml://registries/shared/models/model/labels/latest",
    "azureml://registries/shared/models/model",
    "azureml://registries/shared/environments/model/versions/8",
    "azureml://registries/shared/models/../versions/8",
    "azureml://registries/shared/models/model/versions/8?extra=value",
])
def test_deploy_model_rejects_invalid_registry_paths_before_transfer(source):
    model = Model(name="destination-model", path=source)
    workspace_client = MagicMock()
    with (
        patch("aip.inner.deploy.load_model", return_value=model),
        patch("aip.inner.deploy.get_workspace_client", return_value=workspace_client),
        patch("aip.inner.deploy.get_registry_client") as registry_factory,
        patch("aip.inner.deploy.github_output") as output,
        pytest.raises(deploy.typer.BadParameter, match="Registry model path must use"),
    ):
        deploy.model("subscription", "resource-group", "workspace", "model.yaml")
    registry_factory.assert_not_called()
    workspace_client.models.create_or_update.assert_not_called()
    output.assert_not_called()


def _asset_client(versions: list[str] | None) -> AssetClient:
    """An AssetClient whose transport serves one container and its version list."""

    def transport(method, url, headers, body):
        if versions is None:
            return 404, None
        if "/versions?" in url:
            return 200, {"value": [{"name": v, "properties": {}} for v in versions]}
        return 200, {"name": "training-data", "properties": {}}

    token_manager = MagicMock(spec=TokenManager)
    token_manager.get_token.return_value = "token"
    return AssetClient(
        base_url="https://management.azure.com/base",
        token_manager=token_manager,
        scope_label="workspace 'workspace'",
        transport=transport,
    )


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

    client = MagicMock(name="client")
    client.data.create_or_update.return_value = _mock_data_result(
        "training-data",
        "8",
        "/data/training-data/versions/8",
    )

    with (
        patch("aip.inner.deploy.get_workspace_client", return_value=client),
        patch("aip.inner.deploy.load_data", return_value=data_asset),
        patch.object(AssetClient, "for_workspace", return_value=_asset_client(["3", "7"])),
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

    client = MagicMock(name="client")
    client.data.create_or_update.return_value = _mock_data_result(
        "training-data",
        "3",
        "/data/training-data/versions/3",
    )

    with (
        patch("aip.inner.deploy.get_workspace_client", return_value=client),
        patch("aip.inner.deploy.load_data", return_value=data_asset),
        patch.object(AssetClient, "for_workspace", return_value=_asset_client(["v-next", "2"])),
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
        patch.object(AssetClient, "for_workspace", return_value=_asset_client(None)),
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
