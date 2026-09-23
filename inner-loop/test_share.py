"""Tests for shared asset visibility retries."""

from unittest.mock import MagicMock, call, patch

import pytest

from aip.inner.arm import AssetVersion
from aip.inner.share import _wait_for_shared_asset


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