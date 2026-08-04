"""Tests for the ARM container/version asset client and the version helpers."""

from unittest.mock import MagicMock

import pytest

from aip.inner.arm import (
    ARM_BASE_URL,
    LIST_VIEW_ALL,
    REST_API_VERSION,
    ArmError,
    AssetClient,
    TokenManager,
    _resolve_registry_resource_group,
)
from aip.inner.getasset import (
    getcomponent,
    getdata,
    next_int_version,
    parse_int_version,
)

WORKSPACE_BASE = (
    f"{ARM_BASE_URL}/subscriptions/sub/resourceGroups/rg"
    "/providers/Microsoft.MachineLearningServices/workspaces/ws"
)


class RecordingTransport:
    """Serves canned responses and records every request the client makes."""

    def __init__(self, responses):
        self._responses = responses
        self.calls = []

    def __call__(self, method, url, headers, body):
        self.calls.append({"method": method, "url": url, "headers": headers, "body": body})
        for matcher, response in self._responses:
            if matcher(method, url):
                return response
        return 404, None

    def urls(self, method=None):
        return [c["url"] for c in self.calls if method is None or c["method"] == method]


def _token_manager():
    manager = MagicMock(spec=TokenManager)
    manager.get_token.return_value = "secret-token"
    return manager


def _client(responses, is_registry=False, base_url=WORKSPACE_BASE):
    transport = RecordingTransport(responses)
    client = AssetClient(
        base_url=base_url,
        token_manager=_token_manager(),
        scope_label="workspace 'ws'",
        is_registry=is_registry,
        transport=transport,
    )
    return client, transport


def _container_body(name="my-asset", latest="4", archived=False, tags=None):
    return {
        "id": f"{WORKSPACE_BASE}/components/{name}",
        "name": name,
        "properties": {
            "latestVersion": latest,
            "isArchived": archived,
            "tags": tags or {},
            "description": "a description",
        },
    }


def _version_body(name="my-asset", version="4", archived=False, tags=None, created_at=None):
    return {
        "id": f"{WORKSPACE_BASE}/components/{name}/versions/{version}",
        "name": version,
        "properties": {"isArchived": archived, "tags": tags or {}},
        "systemData": {"createdAt": created_at} if created_at else {},
    }


def _is_container(method, url):
    return method == "GET" and "/versions" not in url


def _is_version_list(method, url):
    return method == "GET" and "/versions?" in url


def _is_version(method, url):
    return method == "GET" and "/versions/" in url


class TestParseIntVersion:
    @pytest.mark.parametrize(
        "value,expected",
        [
            ("1", 1),
            ("0002", 2),
            (" 3 ", 3),
            ("0", 0),
            (7, 7),
            ("1.0.0", None),
            ("v2", None),
            ("azureml_9d8f_output", None),
            ("2024-01-02-153000", None),
            ("", None),
            ("   ", None),
            (None, None),
            (True, None),
            (-1, None),
            (3.5, None),
        ],
    )
    def test_only_plain_positive_integers_are_accepted(self, value, expected):
        assert parse_int_version(value) == expected


class TestAssetClientUrls:
    def test_container_get_uses_the_container_route_and_pinned_api_version(self):
        client, transport = _client([(_is_container, (200, _container_body()))])

        container = client.get_container("component", "my-asset")

        assert container is not None
        assert container.latest_version == "4"
        assert transport.urls("GET") == [
            f"{WORKSPACE_BASE}/components/my-asset?api-version={REST_API_VERSION}"
        ]

    def test_missing_container_returns_none_rather_than_raising(self):
        client, _ = _client([])
        assert client.get_container("model", "absent") is None

    def test_version_list_requests_all_versions_and_follows_next_link(self):
        page_two = f"{WORKSPACE_BASE}/components/my-asset/versions?$skiptoken=abc"
        responses = [
            (
                lambda m, u: u == page_two,
                (200, {"value": [_version_body(version="2")]}),
            ),
            (
                _is_version_list,
                (200, {"value": [_version_body(version="1")], "nextLink": page_two}),
            ),
        ]
        client, transport = _client(responses)

        versions = client.list_versions("component", "my-asset")

        assert [v.version for v in versions] == ["1", "2"]
        assert f"listViewType={LIST_VIEW_ALL}" in transport.urls("GET")[0]
        assert transport.urls("GET")[1] == page_two

    def test_version_list_sends_no_top_or_orderby(self):
        """The component version API rejects both with HTTP 400."""
        client, transport = _client([(_is_version_list, (200, {"value": []}))])

        client.list_versions("component", "my-asset")

        listed = transport.urls("GET")[0]
        assert "top" not in listed
        assert "orderBy" not in listed
        assert "orderby" not in listed

    def test_registry_scope_uses_the_registries_route(self):
        registry_base = (
            f"{ARM_BASE_URL}/subscriptions/sub/resourceGroups/reg-rg"
            "/providers/Microsoft.MachineLearningServices/registries/my-registry"
        )
        client, transport = _client(
            [(_is_container, (200, _container_body()))],
            is_registry=True,
            base_url=registry_base,
        )

        client.get_container("model", "my-asset")

        assert transport.urls("GET")[0].startswith(f"{registry_base}/models/my-asset?")

    def test_error_responses_raise_without_echoing_the_token(self):
        client, _ = _client([(_is_container, (403, {"error": {"code": "AuthorizationFailed", "message": "no access"}}))])

        with pytest.raises(ArmError) as excinfo:
            client.get_container("data", "my-asset")

        assert "AuthorizationFailed" in str(excinfo.value)
        assert "secret-token" not in str(excinfo.value)

    def test_unknown_asset_kind_is_rejected(self):
        client, _ = _client([])
        with pytest.raises(ValueError):
            client.get_container("endpoint", "my-asset")


class TestRegistryResolution:
    def test_resource_group_is_read_from_the_registry_arm_id(self):
        transport = RecordingTransport([
            (
                lambda m, u: True,
                (
                    200,
                    {
                        "value": [
                            {"name": "other", "id": "/subscriptions/sub/resourceGroups/wrong/providers/x/registries/other"},
                            {"name": "mine", "id": "/subscriptions/sub/resourceGroups/right/providers/x/registries/mine"},
                        ]
                    },
                ),
            )
        ])

        resolved = _resolve_registry_resource_group("mine", "sub", _token_manager(), transport)

        assert resolved == "right"

    def test_a_registry_in_another_subscription_is_reported_clearly(self):
        transport = RecordingTransport([(lambda m, u: True, (200, {"value": []}))])

        with pytest.raises(ArmError) as excinfo:
            _resolve_registry_resource_group("elsewhere", "sub", _token_manager(), transport)

        assert "elsewhere" in str(excinfo.value)
        assert "sub" in str(excinfo.value)


class TestArchivedContainer:
    def test_workspace_container_is_unarchived_and_confirmed(self):
        states = iter([True, False])
        responses = [
            (_is_container, None),
            (lambda m, u: m == "PUT", (200, {})),
        ]
        transport = RecordingTransport([])

        def serve(method, url, headers, body):
            transport.calls.append({"method": method, "url": url, "headers": headers, "body": body})
            if method == "PUT":
                return 200, {}
            return 200, _container_body(archived=next(states))

        client = AssetClient(
            base_url=WORKSPACE_BASE,
            token_manager=_token_manager(),
            scope_label="workspace 'ws'",
            transport=serve,
        )

        assert client.unarchive_container("component", "my-asset") is True
        put_calls = [c for c in transport.calls if c["method"] == "PUT"]
        assert len(put_calls) == 1
        assert put_calls[0]["body"] == {
            "properties": {
                "tags": {},
                "properties": {},
                "isArchived": False,
                "description": "a description",
            }
        }

    def test_next_int_version_repairs_the_container_and_still_counts_versions(self, capsys):
        archived = iter([True, False])

        def serve(method, url, headers, body):
            if method == "PUT":
                return 200, {}
            if "/versions?" in url:
                return 200, {"value": [_version_body(version="1"), _version_body(version="2")]}
            return 200, _container_body(archived=next(archived, False))

        client = AssetClient(
            base_url=WORKSPACE_BASE,
            token_manager=_token_manager(),
            scope_label="workspace 'ws'",
            transport=serve,
        )

        assert next_int_version(client, "component", "my-asset", "deploy component") == "3"
        assert "Restored the component container" in capsys.readouterr().out

    def test_registry_container_is_reported_but_never_modified(self, capsys):
        transport = RecordingTransport([
            (_is_version_list, (200, {"value": [_version_body(version="5")]})),
            (_is_container, (200, _container_body(archived=True))),
        ])
        client = AssetClient(
            base_url=WORKSPACE_BASE,
            token_manager=_token_manager(),
            scope_label="registry 'my-registry'",
            is_registry=True,
            transport=transport,
        )

        assert next_int_version(client, "component", "my-asset", "share component") == "6"
        assert transport.urls("PUT") == []
        assert "is archived" in capsys.readouterr().out


class TestNextIntVersion:
    def test_absent_container_starts_at_one(self):
        client, _ = _client([])
        assert next_int_version(client, "data", "absent", "deploy data") == "1"

    def test_archived_versions_are_counted_because_they_occupy_their_number(self):
        responses = [
            (_is_version_list, (200, {"value": [
                _version_body(version="1"),
                _version_body(version="9", archived=True),
            ]})),
            (_is_container, (200, _container_body(latest="1"))),
        ]
        client, _ = _client(responses)

        assert next_int_version(client, "data", "my-asset", "deploy data") == "10"

    def test_non_integer_versions_are_ignored(self):
        responses = [
            (_is_version_list, (200, {"value": [
                _version_body(version="azureml_abc"),
                _version_body(version="1.0.0"),
                _version_body(version="4"),
            ]})),
            (_is_container, (200, _container_body(latest="4"))),
        ]
        client, _ = _client(responses)

        assert next_int_version(client, "component", "my-asset", "deploy component") == "5"

    def test_only_non_integer_versions_still_yields_one(self):
        responses = [
            (_is_version_list, (200, {"value": [_version_body(version="v-next")]})),
            (_is_container, (200, _container_body(latest=None))),
        ]
        client, _ = _client(responses)

        assert next_int_version(client, "component", "my-asset", "deploy component") == "1"


class TestGetAsset:
    def test_missing_container_returns_an_empty_list(self):
        client, _ = _client([])
        assert getdata(client=client, name="absent") == []

    def test_explicit_version_hits_the_version_route_directly(self):
        client, transport = _client([
            (_is_version, (200, _version_body(version="3"))),
            (_is_container, (200, _container_body())),
        ])

        found = getcomponent(client=client, name="my-asset", version=3)

        assert [f.version for f in found] == ["3"]
        assert transport.urls("GET")[-1].startswith(
            f"{WORKSPACE_BASE}/components/my-asset/versions/3?"
        )

    def test_latest_version_comes_from_the_container(self):
        client, _ = _client([
            (_is_version_list, (200, {"value": [
                _version_body(version="1"),
                _version_body(version="4"),
            ]})),
            (_is_container, (200, _container_body(latest="4"))),
        ])

        found = getcomponent(client=client, name="my-asset")

        assert [f.version for f in found] == ["4"]

    def test_latest_falls_back_to_the_newest_timestamp_when_the_container_has_none(self):
        client, _ = _client([
            (_is_version_list, (200, {"value": [
                _version_body(version="1", created_at="2024-01-01T00:00:00.1234567+00:00"),
                _version_body(version="2", created_at="2024-06-01T00:00:00Z"),
            ]})),
            (_is_container, (200, _container_body(latest=None))),
        ])

        found = getcomponent(client=client, name="my-asset")

        assert [f.version for f in found] == ["2"]

    def test_tag_filtering_matches_keys_and_optional_values(self):
        client, _ = _client([
            (_is_version, (200, _version_body(version="2", tags={"stage": "dev", "team": "aip"}))),
            (_is_container, (200, _container_body(latest="2"))),
        ])

        assert getcomponent(client=client, name="my-asset", version="2", tags={"stage": "dev"})
        assert getcomponent(client=client, name="my-asset", version="2", tags={"stage": None})
        assert getcomponent(client=client, name="my-asset", version="2", tags="team")
        assert not getcomponent(client=client, name="my-asset", version="2", tags={"stage": "prod"})
        assert not getcomponent(client=client, name="my-asset", version="2", tags={"absent": None})

    def test_req_int_version_drops_non_integer_versions(self):
        client, _ = _client([
            (_is_version, (200, _version_body(version="azureml_abc"))),
            (_is_container, (200, _container_body(latest="azureml_abc"))),
        ])

        assert getcomponent(client=client, name="my-asset", version="azureml_abc") == []
        assert len(getcomponent(client=client, name="my-asset", version="azureml_abc", req_int_version=False)) == 1

    def test_archived_versions_are_excluded_from_lookups(self):
        client, _ = _client([
            (_is_version, (200, _version_body(version="2", archived=True))),
            (_is_container, (200, _container_body(latest="2"))),
        ])

        assert getcomponent(client=client, name="my-asset", version="2") == []
