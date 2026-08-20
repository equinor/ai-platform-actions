"""Focused tests for the managed feature store deploy commands."""

from unittest.mock import MagicMock, patch

import pytest
import typer

from aip.inner import deploy
from aip.inner.arm import AssetClient, TokenManager
from aip.inner.util import amlignore_preserved

SUBSCRIPTION = "subscription"
RESOURCE_GROUP = "resource-group"
FEATURE_STORE = "my-feature-store"


def _asset_client(versions: list[str] | None) -> AssetClient:
    """An AssetClient whose transport serves one container and its version list."""

    def transport(method, url, headers, body):
        if versions is None:
            return 404, None
        if "/versions?" in url:
            return 200, {"value": [{"name": v, "properties": {}} for v in versions]}
        return 200, {"name": "transactions", "properties": {}}

    token_manager = MagicMock(spec=TokenManager)
    token_manager.get_token.return_value = "token"
    return AssetClient(
        base_url="https://management.azure.com/base",
        token_manager=token_manager,
        scope_label=f"feature store '{FEATURE_STORE}'",
        transport=transport,
    )


def _spec_folder(tmp_path):
    folder = tmp_path / "spec"
    folder.mkdir()
    (folder / "FeatureSetSpec.yaml").write_text("features: []\n", encoding="utf-8")
    return folder


def _feature_set_config(tmp_path, name: str = "transactions") -> MagicMock:
    config = MagicMock(name="feature_set_config")
    config.name = name
    config.tags = None
    config.entities = ["azureml:account:1"]
    config.stage = "Development"
    config.base_path = str(tmp_path)
    config.specification.path = str(_spec_folder(tmp_path))
    return config


def test_deploy_feature_set_uses_next_integer_version_from_the_feature_store(tmp_path):
    config = _feature_set_config(tmp_path)
    client = MagicMock(name="client")

    with (
        patch("aip.inner.deploy.get_workspace_client", return_value=client),
        patch("aip.inner.deploy.load_feature_set", return_value=config),
        patch.object(AssetClient, "for_workspace", return_value=_asset_client(["3", "7"])),
        patch("aip.inner.deploy.github_output"),
    ):
        deploy.feature_set(SUBSCRIPTION, RESOURCE_GROUP, FEATURE_STORE, "featureset.yaml")

    assert config.version == "8"
    client.feature_sets.begin_create_or_update.assert_called_once_with(config)


def test_deploy_feature_set_does_not_wait_for_provisioning(tmp_path):
    config = _feature_set_config(tmp_path)
    client = MagicMock(name="client")
    poller = client.feature_sets.begin_create_or_update.return_value

    with (
        patch("aip.inner.deploy.get_workspace_client", return_value=client),
        patch("aip.inner.deploy.load_feature_set", return_value=config),
        patch.object(AssetClient, "for_workspace", return_value=_asset_client(None)),
        patch("aip.inner.deploy.github_output"),
    ):
        deploy.feature_set(SUBSCRIPTION, RESOURCE_GROUP, FEATURE_STORE, "featureset.yaml")

    poller.result.assert_not_called()


def test_deploy_feature_set_emits_a_derived_resource_id(tmp_path):
    config = _feature_set_config(tmp_path)

    with (
        patch("aip.inner.deploy.get_workspace_client", return_value=MagicMock()),
        patch("aip.inner.deploy.load_feature_set", return_value=config),
        patch.object(AssetClient, "for_workspace", return_value=_asset_client(None)),
        patch("aip.inner.deploy.github_output") as github_output,
    ):
        deploy.feature_set(SUBSCRIPTION, RESOURCE_GROUP, FEATURE_STORE, "featureset.yaml")

    assert github_output.call_args.args[0] == {
        "reference": "azureml:transactions:1",
        "version": "1",
        "resource-id": (
            f"/subscriptions/{SUBSCRIPTION}/resourceGroups/{RESOURCE_GROUP}"
            f"/providers/Microsoft.MachineLearningServices/workspaces/{FEATURE_STORE}"
            "/featuresets/transactions/versions/1"
        ),
    }


def test_deploy_feature_set_merges_tags(tmp_path):
    config = _feature_set_config(tmp_path)
    config.tags = {"owner": "team"}

    with (
        patch("aip.inner.deploy.get_workspace_client", return_value=MagicMock()),
        patch("aip.inner.deploy.load_feature_set", return_value=config),
        patch.object(AssetClient, "for_workspace", return_value=_asset_client(None)),
        patch("aip.inner.deploy.github_output"),
    ):
        deploy.feature_set(
            SUBSCRIPTION,
            RESOURCE_GROUP,
            FEATURE_STORE,
            "featureset.yaml",
            tags={"data_type": "nonPII"},
        )

    assert config.tags == {"owner": "team", "data_type": "nonPII"}


def test_deploy_feature_set_rejects_a_missing_spec_folder(tmp_path):
    config = _feature_set_config(tmp_path)
    config.specification.path = str(tmp_path / "absent")

    with (
        patch("aip.inner.deploy.get_workspace_client", return_value=MagicMock()),
        patch("aip.inner.deploy.load_feature_set", return_value=config),
        pytest.raises(typer.BadParameter, match="does not exist"),
    ):
        deploy.feature_set(SUBSCRIPTION, RESOURCE_GROUP, FEATURE_STORE, "featureset.yaml")


def test_deploy_feature_set_rejects_a_spec_folder_without_a_spec_file(tmp_path):
    config = _feature_set_config(tmp_path)
    (tmp_path / "spec" / "FeatureSetSpec.yaml").unlink()

    with (
        patch("aip.inner.deploy.get_workspace_client", return_value=MagicMock()),
        patch("aip.inner.deploy.load_feature_set", return_value=config),
        pytest.raises(typer.BadParameter, match="FeatureSetSpec.yaml"),
    ):
        deploy.feature_set(SUBSCRIPTION, RESOURCE_GROUP, FEATURE_STORE, "featureset.yaml")


def test_deploy_feature_set_accepts_a_cloud_hosted_spec(tmp_path):
    config = _feature_set_config(tmp_path)
    config.specification.path = "azureml://datastores/workspaceblobstore/paths/specs/transactions"
    client = MagicMock(name="client")

    with (
        patch("aip.inner.deploy.get_workspace_client", return_value=client),
        patch("aip.inner.deploy.load_feature_set", return_value=config),
        patch.object(AssetClient, "for_workspace", return_value=_asset_client(None)),
        patch("aip.inner.deploy.github_output"),
    ):
        deploy.feature_set(SUBSCRIPTION, RESOURCE_GROUP, FEATURE_STORE, "featureset.yaml")

    client.feature_sets.begin_create_or_update.assert_called_once_with(config)


def _entity(version: str = "3") -> MagicMock:
    entity = MagicMock(name="entity")
    entity.name = "account"
    entity.version = version
    entity.tags = None
    entity.index_columns = []
    return entity


def test_deploy_feature_store_entity_keeps_the_version_from_the_yaml():
    entity = _entity("3")
    client = MagicMock(name="client")
    result = client.feature_store_entities.begin_create_or_update.return_value.result.return_value
    result.name = "account"
    result.version = "3"
    result.id = "/featurestoreEntities/account/versions/3"

    with (
        patch("aip.inner.deploy.get_workspace_client", return_value=client),
        patch("aip.inner.deploy.load_feature_store_entity", return_value=entity),
        patch("aip.inner.deploy.github_output") as github_output,
    ):
        deploy.feature_store_entity(SUBSCRIPTION, RESOURCE_GROUP, FEATURE_STORE, "entity.yaml")

    assert entity.version == "3"
    client.feature_store_entities.begin_create_or_update.assert_called_once_with(entity)
    assert github_output.call_args.args[0]["reference"] == "azureml:account:3"


def test_deploy_feature_store_entity_waits_for_provisioning():
    entity = _entity()
    client = MagicMock(name="client")
    poller = client.feature_store_entities.begin_create_or_update.return_value

    with (
        patch("aip.inner.deploy.get_workspace_client", return_value=client),
        patch("aip.inner.deploy.load_feature_store_entity", return_value=entity),
        patch("aip.inner.deploy.github_output"),
    ):
        deploy.feature_store_entity(SUBSCRIPTION, RESOURCE_GROUP, FEATURE_STORE, "entity.yaml")

    poller.result.assert_called_once_with()


def test_amlignore_created_by_the_sdk_is_removed_afterwards(tmp_path):
    target = tmp_path / ".amlignore"

    with amlignore_preserved(tmp_path, subject="deploy feature-set"):
        target.write_text(".*\n", encoding="utf-8")

    assert not target.exists()


def test_existing_amlignore_is_restored_and_warns(tmp_path, capsys):
    target = tmp_path / ".amlignore"
    target.write_text("scratch/\n", encoding="utf-8")

    with amlignore_preserved(tmp_path, subject="deploy feature-set"):
        target.write_text(".*\n", encoding="utf-8")

    assert target.read_text(encoding="utf-8") == "scratch/\n"
    assert "Warning" in capsys.readouterr().out


def test_amlignore_is_restored_when_the_upload_fails(tmp_path):
    target = tmp_path / ".amlignore"
    target.write_text("scratch/\n", encoding="utf-8")

    with pytest.raises(RuntimeError):
        with amlignore_preserved(tmp_path, subject="deploy feature-set"):
            target.write_text(".*\n", encoding="utf-8")
            raise RuntimeError("upload failed")

    assert target.read_text(encoding="utf-8") == "scratch/\n"


def test_amlignore_is_not_announced_when_absent(tmp_path, capsys):
    with amlignore_preserved(tmp_path, subject="deploy feature-set"):
        pass

    assert "Warning" not in capsys.readouterr().out


def test_amlignore_guard_is_inert_for_a_cloud_hosted_spec():
    with amlignore_preserved(None, subject="deploy feature-set"):
        pass
