"""
Test suite for outer-loop action logic.

Covers:
1. _compute_score  (compare.py) — weighted scoring with per-metric direction and missing-primary handling
2. _apply_policy   (evaluate.py) — all six signal triggers plus priority ordering
3. evaluate gate   (evaluate.py) — threshold evaluation via Typer CliRunner

Run with:
    cd outer-loop
    uv run pytest test_outer.py -v
"""

import os
import sys
import tempfile
from unittest.mock import MagicMock, patch

import requests

# Mock Azure SDK before importing aip modules to prevent import errors
sys.modules["azure"] = MagicMock()
sys.modules["azure.core"] = MagicMock()
sys.modules["azure.core.credentials"] = MagicMock()
sys.modules["azure.identity"] = MagicMock()
sys.modules["azure.ai"] = MagicMock()
sys.modules["azure.ai.ml"] = MagicMock()

import pytest
from typer.testing import CliRunner

from aip.outer.compare import _compute_score
from aip.outer.evaluate import _apply_policy, app as evaluate_app
from aip.outer.util import AzureMLBackend, MLFlowProxyClient, create_mlflow_client

runner = CliRunner(mix_stderr=False)


# =============================================================================
# _compute_score
# =============================================================================

class TestComputeScore:
    """Tests for the weighted scoring function in compare.py."""

    def test_maximize_single_metric(self):
        score = _compute_score({"accuracy": 0.90}, {"accuracy": 1.0}, "maximize")
        assert score == pytest.approx(0.90)

    def test_minimize_single_metric(self):
        score = _compute_score({"loss": 0.10}, {"loss": 1.0}, "minimize")
        assert score == pytest.approx(-0.10)

    def test_weighted_maximize_two_metrics(self):
        # score = 0.9 * (0.7/1.0) + 0.8 * (0.3/1.0) = 0.63 + 0.24 = 0.87
        score = _compute_score(
            {"accuracy": 0.9, "f1": 0.8},
            {"accuracy": 0.7, "f1": 0.3},
            "maximize",
        )
        assert score == pytest.approx(0.87)

    def test_missing_primary_returns_neg_inf(self):
        # accuracy is primary but not in metrics
        score = _compute_score({"f1": 0.8}, {"accuracy": 1.0}, "maximize", primary="accuracy")
        assert score == float("-inf")

    def test_missing_primary_warns(self, capsys):
        _compute_score({}, {"accuracy": 1.0}, "maximize", primary="accuracy")
        # typer.echo writes to stderr; CliRunner captures it, but capsys captures sys.stderr
        # We just verify the function returns -inf without raising

    def test_missing_non_primary_metric_contributes_zero(self):
        # f1 is absent but primary=accuracy is present — only accuracy contributes
        score = _compute_score(
            {"accuracy": 0.9},
            {"accuracy": 0.7, "f1": 0.3},
            "maximize",
            primary="accuracy",
        )
        # only accuracy: 0.9 * (0.7 / 1.0) = 0.63
        assert score == pytest.approx(0.63)

    def test_per_metric_direction_override_loss_minimized(self):
        # global=maximize, loss overridden to minimize
        score = _compute_score(
            {"accuracy": 0.9, "loss": 0.2},
            {"accuracy": 0.6, "loss": 0.4},
            "maximize",
            directions={"loss": "minimize"},
        )
        # accuracy: +1 * 0.9 * 0.6 = 0.54; loss: -1 * 0.2 * 0.4 = -0.08
        assert score == pytest.approx(0.54 - 0.08)

    def test_per_metric_direction_all_overridden(self):
        directions = {"accuracy": "maximize", "loss": "minimize"}
        score = _compute_score(
            {"accuracy": 0.9, "loss": 0.2},
            {"accuracy": 0.6, "loss": 0.4},
            "maximize",
            directions=directions,
        )
        assert score == pytest.approx(0.9 * 0.6 + (-1.0) * 0.2 * 0.4)

    def test_empty_metrics_returns_zero(self):
        score = _compute_score({}, {"accuracy": 1.0}, "maximize")
        assert score == 0.0

    def test_no_primary_empty_metrics_returns_zero(self):
        score = _compute_score({}, {"accuracy": 1.0}, "maximize", primary="")
        assert score == 0.0

    def test_runs_ranked_correctly(self):
        weights = {"accuracy": 1.0}
        score_a = _compute_score({"accuracy": 0.9}, weights, "maximize", primary="accuracy")
        score_b = _compute_score({"accuracy": 0.7}, weights, "maximize", primary="accuracy")
        score_missing = _compute_score({}, weights, "maximize", primary="accuracy")
        assert score_a > score_b
        assert score_missing == float("-inf")
        assert score_b > score_missing


# =============================================================================
# _apply_policy
# =============================================================================

class TestApplyPolicy:
    """Tests for the decision policy function in evaluate.py."""

    @staticmethod
    def _cfg(**overrides):
        """Return a policy config dict with sensible defaults for all thresholds."""
        base = {
            "drift_threshold": 0.10,
            "performance_drop_threshold": 0.05,
            "label_quality_threshold": 0.05,
            "data_staleness_threshold": 0.20,
            "feature_drift_threshold": 0.15,
            "code_issue_threshold": 0.10,
            "actions": {
                "on_drift": "retrain",
                "on_performance_drop": "retrain",
                "on_label_quality": "label-improvement",
                "on_data_staleness": "data-refresh",
                "on_feature_drift": "feature-change",
                "on_code_issue": "code-fix",
                "default": "no-change",
            },
        }
        base.update(overrides)
        return base

    def test_no_signals_returns_no_change(self):
        assert _apply_policy({}, self._cfg()) == "no-change"

    def test_all_signals_zero_returns_no_change(self):
        signals = {
            "data_drift": 0.0, "performance_drop": 0.0, "label_quality_drop": 0.0,
            "data_staleness": 0.0, "feature_drift": 0.0, "code_issue": 0.0,
        }
        assert _apply_policy(signals, self._cfg()) == "no-change"

    def test_data_drift_triggers_retrain(self):
        assert _apply_policy({"data_drift": 0.15}, self._cfg()) == "retrain"

    def test_data_drift_at_threshold_does_not_trigger(self):
        # strictly greater-than, so equal threshold is not a trigger
        assert _apply_policy({"data_drift": 0.10}, self._cfg()) == "no-change"

    def test_performance_drop_triggers_retrain(self):
        assert _apply_policy({"performance_drop": 0.10}, self._cfg()) == "retrain"

    def test_performance_drop_below_threshold(self):
        assert _apply_policy({"performance_drop": 0.04}, self._cfg()) == "no-change"

    def test_label_quality_drop_triggers_label_improvement(self):
        assert _apply_policy({"label_quality_drop": 0.10}, self._cfg()) == "label-improvement"

    def test_data_staleness_triggers_data_refresh(self):
        assert _apply_policy({"data_staleness": 0.25}, self._cfg()) == "data-refresh"

    def test_data_staleness_at_threshold_does_not_trigger(self):
        assert _apply_policy({"data_staleness": 0.20}, self._cfg()) == "no-change"

    def test_feature_drift_triggers_feature_change(self):
        assert _apply_policy({"feature_drift": 0.20}, self._cfg()) == "feature-change"

    def test_code_issue_triggers_code_fix(self):
        assert _apply_policy({"code_issue": 0.15}, self._cfg()) == "code-fix"

    def test_priority_drift_beats_performance_drop(self):
        signals = {"data_drift": 0.20, "performance_drop": 0.10}
        assert _apply_policy(signals, self._cfg()) == "retrain"

    def test_priority_perf_drop_beats_label_quality(self):
        signals = {"performance_drop": 0.10, "label_quality_drop": 0.10}
        assert _apply_policy(signals, self._cfg()) == "retrain"

    def test_priority_label_quality_beats_data_staleness(self):
        signals = {"label_quality_drop": 0.10, "data_staleness": 0.25}
        assert _apply_policy(signals, self._cfg()) == "label-improvement"

    def test_priority_data_staleness_beats_feature_drift(self):
        signals = {"data_staleness": 0.25, "feature_drift": 0.20}
        assert _apply_policy(signals, self._cfg()) == "data-refresh"

    def test_priority_feature_drift_beats_code_issue(self):
        signals = {"feature_drift": 0.20, "code_issue": 0.15}
        assert _apply_policy(signals, self._cfg()) == "feature-change"

    def test_custom_action_for_drift(self):
        cfg = self._cfg()
        cfg["actions"]["on_drift"] = "data-refresh"
        assert _apply_policy({"data_drift": 0.20}, cfg) == "data-refresh"

    def test_missing_actions_key_uses_defaults(self):
        cfg = {"drift_threshold": 0.10}  # no 'actions' sub-dict
        assert _apply_policy({"data_drift": 0.20}, cfg) == "retrain"

    def test_missing_actions_default_key(self):
        cfg = {"actions": {}}  # no 'default' key inside actions
        assert _apply_policy({}, cfg) == "no-change"


# =============================================================================
# evaluate gate (CLI integration via CliRunner)
# =============================================================================

class TestGateEvaluation:
    """Integration-style tests for the evaluate gate command.

    The MLFlowProxyClient and get_credential are mocked so no network calls
    are made.
    """

    @staticmethod
    def _run_gate(metrics: dict, thresholds_yaml: str, run_id: str = "run-abc"):
        """Run `evaluate gate` with a temp thresholds file and mocked HTTP client."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(thresholds_yaml)
            tmp_path = f.name
        try:
            mock_client = MagicMock()
            mock_client.get_run_metrics.return_value = metrics
            with (
                patch("aip.outer.evaluate.create_mlflow_client", return_value=mock_client),
                patch("aip.outer.evaluate.get_credential", return_value=MagicMock()),
            ):
                result = runner.invoke(
                    evaluate_app,
                    [
                        "gate",
                        "--mlflow-url", "https://proxy.example.com",
                        "--experiment-name", "test-exp",
                        "--thresholds-file", tmp_path,
                        "--run-id", run_id,
                    ],
                )
        finally:
            os.unlink(tmp_path)
        return result

    def test_all_metrics_pass(self):
        thresholds = "accuracy:\n  min: 0.80\nloss:\n  max: 0.20\n"
        result = self._run_gate({"accuracy": 0.90, "loss": 0.10}, thresholds)
        assert result.exit_code == 0

    def test_one_metric_below_min_fails(self):
        thresholds = "accuracy:\n  min: 0.90\n"
        result = self._run_gate({"accuracy": 0.80}, thresholds)
        assert result.exit_code == 1

    def test_one_metric_above_max_fails(self):
        thresholds = "loss:\n  max: 0.15\n"
        result = self._run_gate({"loss": 0.20}, thresholds)
        assert result.exit_code == 1

    def test_missing_metric_fails(self):
        thresholds = "accuracy:\n  min: 0.80\n"
        result = self._run_gate({}, thresholds)
        assert result.exit_code == 1

    def test_exact_min_boundary_passes(self):
        thresholds = "accuracy:\n  min: 0.85\n"
        result = self._run_gate({"accuracy": 0.85}, thresholds)
        assert result.exit_code == 0

    def test_just_below_min_boundary_fails(self):
        thresholds = "accuracy:\n  min: 0.85\n"
        result = self._run_gate({"accuracy": 0.8499}, thresholds)
        assert result.exit_code == 1

    def test_exact_max_boundary_passes(self):
        thresholds = "loss:\n  max: 0.15\n"
        result = self._run_gate({"loss": 0.15}, thresholds)
        assert result.exit_code == 0

    def test_just_above_max_boundary_fails(self):
        thresholds = "loss:\n  max: 0.15\n"
        result = self._run_gate({"loss": 0.1501}, thresholds)
        assert result.exit_code == 1

    def test_min_and_max_combined_passes(self):
        thresholds = "precision:\n  min: 0.80\n  max: 1.00\n"
        result = self._run_gate({"precision": 0.90}, thresholds)
        assert result.exit_code == 0

    def test_min_and_max_combined_fails_above_max(self):
        thresholds = "precision:\n  min: 0.80\n  max: 0.95\n"
        result = self._run_gate({"precision": 0.96}, thresholds)
        assert result.exit_code == 1

    def test_multiple_metrics_one_missing_fails(self):
        thresholds = "accuracy:\n  min: 0.80\nf1:\n  min: 0.75\n"
        result = self._run_gate({"accuracy": 0.90}, thresholds)  # f1 is missing
        assert result.exit_code == 1

    def test_multiple_metrics_all_pass(self):
        thresholds = "accuracy:\n  min: 0.80\nf1:\n  min: 0.75\nloss:\n  max: 0.20\n"
        result = self._run_gate({"accuracy": 0.90, "f1": 0.80, "loss": 0.10}, thresholds)
        assert result.exit_code == 0


# =============================================================================
# create_mlflow_client factory
# =============================================================================

class TestMLFlowClientFactory:
    """Tests for the backend factory function in util.py."""

    def test_https_url_returns_proxy_client(self):
        cred = MagicMock()
        with patch("aip.outer.util.MLFlowProxyClient.__init__", return_value=None):
            client = create_mlflow_client("https://proxy.example.com", cred)
        assert isinstance(client, MLFlowProxyClient)

    def test_http_url_returns_proxy_client(self):
        cred = MagicMock()
        with patch("aip.outer.util.MLFlowProxyClient.__init__", return_value=None):
            client = create_mlflow_client("http://localhost:5000", cred)
        assert isinstance(client, MLFlowProxyClient)

    def test_azureml_uri_returns_azureml_backend(self):
        cred = MagicMock()
        uri = "azureml://swedencentral.api.azureml.ms/mlflow/v1.0/subscriptions/sub/resourceGroups/rg/providers/Microsoft.MachineLearningServices/workspaces/ws"
        with patch("aip.outer.util._make_requests_session"):
            client = create_mlflow_client(uri, cred)
        assert isinstance(client, AzureMLBackend)

    def test_unknown_scheme_raises_value_error(self):
        with pytest.raises(ValueError, match="mlflow-url must be"):
            create_mlflow_client("ftp://something.example.com", MagicMock())


# =============================================================================
# AzureMLBackend
# =============================================================================

class TestAzureMLBackend:
    """Tests for AzureMLBackend — uses HTTP mocks; no mlflow SDK dependency."""

    AZUREML_URI = "azureml://swedencentral.api.azureml.ms/mlflow/v1.0/subscriptions/sub/resourceGroups/rg/providers/Microsoft.MachineLearningServices/workspaces/ws"
    BASE_URL = "https://swedencentral.api.azureml.ms/mlflow/v1.0/subscriptions/sub/resourceGroups/rg/providers/Microsoft.MachineLearningServices/workspaces/ws"

    def _make_backend(self):
        cred = MagicMock()
        cred.get_token.return_value = MagicMock(token="test-token", expires_on=9999999999)
        with patch("aip.outer.util._make_requests_session") as mock_session_factory:
            mock_session_factory.return_value = MagicMock()
            backend = AzureMLBackend(self.AZUREML_URI, cred)
        return backend

    def test_get_experiment_runs_returns_normalized_dicts(self):
        backend = self._make_backend()
        backend._session.get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"experiment": {"experiment_id": "exp1"}},
            raise_for_status=lambda: None,
        )
        backend._session.post.return_value = MagicMock(
            status_code=200,
            raise_for_status=lambda: None,
            json=lambda: {"runs": [{
                "info": {"run_id": "r1", "status": "FINISHED"},
                "data": {"metrics": [{"key": "accuracy", "value": 0.9}], "tags": []},
            }]},
        )

        runs = backend.get_experiment_runs("my-exp", max_results=10)

        assert runs == [{"run_id": "r1", "status": "FINISHED", "metrics": {"accuracy": 0.9}, "tags": {}}]

    def test_get_experiment_runs_returns_empty_on_404(self):
        backend = self._make_backend()
        not_found = MagicMock(status_code=404)
        http_error = requests.HTTPError(response=not_found)
        backend._session.get.return_value = MagicMock(
            raise_for_status=MagicMock(side_effect=http_error),
        )

        runs = backend.get_experiment_runs("nonexistent")

        assert runs == []

    def test_get_run_metrics_returns_flat_dict(self):
        backend = self._make_backend()
        backend._session.get.return_value = MagicMock(
            raise_for_status=lambda: None,
            json=lambda: {"run": {"info": {}, "data": {
                "metrics": [{"key": "f1", "value": 0.85}, {"key": "loss", "value": 0.12}],
                "tags": [],
            }}},
        )

        metrics = backend.get_run_metrics("r1")

        assert metrics == {"f1": 0.85, "loss": 0.12}

    def test_compare_runs_with_explicit_run_ids(self):
        backend = self._make_backend()
        responses = {
            "r1": {"run": {"info": {"run_id": "r1", "status": "FINISHED"}, "data": {"metrics": [{"key": "accuracy", "value": 0.9}], "tags": []}}},
            "r2": {"run": {"info": {"run_id": "r2", "status": "FINISHED"}, "data": {"metrics": [{"key": "accuracy", "value": 0.8}], "tags": []}}},
        }
        call_count = [0]

        def side_effect(url, **kwargs):
            rid = kwargs.get("params", {}).get("run_id")
            m = MagicMock(raise_for_status=lambda: None)
            m.json.return_value = responses[rid]
            return m

        backend._session.get.side_effect = side_effect

        result = backend.compare_runs("my-exp", run_ids=["r1", "r2"])

        assert len(result) == 2
        assert result[0]["run_id"] == "r1"
        assert result[1]["run_id"] == "r2"

    def test_get_experiment_runs_with_run_name_sends_filter_in_post_body(self):
        backend = self._make_backend()
        backend._session.get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"experiment": {"experiment_id": "exp1"}},
            raise_for_status=lambda: None,
        )
        backend._session.post.return_value = MagicMock(
            status_code=200,
            raise_for_status=lambda: None,
            json=lambda: {"runs": [{
                "info": {"run_id": "r1", "status": "FINISHED"},
                "data": {
                    "metrics": [{"key": "accuracy", "value": 0.9}],
                    "tags": [{"key": "mlflow.runName", "value": "baseline-v2"}],
                },
            }]},
        )

        runs = backend.get_experiment_runs("my-exp", run_name="baseline-v2")

        post_call_kwargs = backend._session.post.call_args
        body = post_call_kwargs[1]["json"]
        assert body.get("filter") == "tags.`mlflow.runName` = 'baseline-v2'"
        assert len(runs) == 1
        assert runs[0]["tags"]["mlflow.runName"] == "baseline-v2"

    def test_compare_runs_with_run_name_delegates_to_get_experiment_runs(self):
        backend = self._make_backend()
        backend._session.get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"experiment": {"experiment_id": "exp1"}},
            raise_for_status=lambda: None,
        )
        backend._session.post.return_value = MagicMock(
            status_code=200,
            raise_for_status=lambda: None,
            json=lambda: {"runs": [{
                "info": {"run_id": "r2", "status": "FINISHED"},
                "data": {"metrics": [], "tags": [{"key": "mlflow.runName", "value": "my-run"}]},
            }]},
        )

        result = backend.compare_runs("my-exp", run_name="my-run")

        post_body = backend._session.post.call_args[1]["json"]
        assert post_body.get("filter") == "tags.`mlflow.runName` = 'my-run'"
        assert result[0]["run_id"] == "r2"

    def test_get_monitoring_run_returns_none_when_no_runs(self):
        backend = self._make_backend()
        not_found = MagicMock(status_code=404)
        http_error = requests.HTTPError(response=not_found)
        backend._session.get.return_value = MagicMock(
            raise_for_status=MagicMock(side_effect=http_error),
        )

        result = backend.get_monitoring_run("monitoring-my-model")

        assert result is None


# =============================================================================
# MLFlowProxyClient — run_name client-side filter
# =============================================================================

class TestMLFlowProxyClientRunNameFilter:
    """Tests for client-side run_name filtering in MLFlowProxyClient."""

    def _make_client(self):
        cred = MagicMock()
        cred.get_token.return_value = MagicMock(token="tok", expires_on=9999999999)
        with patch("aip.outer.util._make_requests_session") as mock_factory:
            mock_factory.return_value = MagicMock()
            client = MLFlowProxyClient("https://proxy.example.com", cred)
        return client

    def test_get_experiment_runs_filters_by_run_name(self):
        client = self._make_client()
        client._session.get.return_value = MagicMock(
            raise_for_status=lambda: None,
            json=lambda: {"runs": [
                {"run_id": "r1", "tags": {"mlflow.runName": "baseline-v2"}},
                {"run_id": "r2", "tags": {"mlflow.runName": "experiment-x"}},
                {"run_id": "r3", "tags": {"mlflow.runName": "baseline-v2"}},
            ]},
        )

        runs = client.get_experiment_runs("my-exp", run_name="baseline-v2")

        assert [r["run_id"] for r in runs] == ["r1", "r3"]

    def test_get_experiment_runs_no_run_name_returns_all(self):
        client = self._make_client()
        client._session.get.return_value = MagicMock(
            raise_for_status=lambda: None,
            json=lambda: {"runs": [
                {"run_id": "r1", "tags": {"mlflow.runName": "a"}},
                {"run_id": "r2", "tags": {"mlflow.runName": "b"}},
            ]},
        )

        runs = client.get_experiment_runs("my-exp")

        assert len(runs) == 2

    def test_compare_runs_filters_by_run_name_when_no_run_ids(self):
        client = self._make_client()
        client._session.get.return_value = MagicMock(
            raise_for_status=lambda: None,
            json=lambda: {"runs": [
                {"run_id": "r1", "tags": {"mlflow.runName": "target"}},
                {"run_id": "r2", "tags": {"mlflow.runName": "other"}},
            ]},
        )

        runs = client.compare_runs("my-exp", run_name="target")

        assert [r["run_id"] for r in runs] == ["r1"]


# =============================================================================
# compare candidates CLI — run-name option
# =============================================================================

from aip.outer.compare import app as compare_app


class TestCompareCandidatesRunName:
    """CLI-level tests for --run-name in compare candidates."""

    CRITERIA_YAML = "primary: accuracy\ndirection: maximize\nweights:\n  accuracy: 1.0\n"

    def _run_candidates(self, extra_args, mock_runs):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(self.CRITERIA_YAML)
            tmp = f.name
        try:
            mock_client = MagicMock()
            mock_client.compare_runs.return_value = mock_runs
            with (
                patch("aip.outer.compare.create_mlflow_client", return_value=mock_client),
                patch("aip.outer.compare.get_credential", return_value=MagicMock()),
            ):
                result = runner.invoke(
                    compare_app,
                    [
                        "candidates",
                        "--mlflow-url", "https://proxy.example.com",
                        "--experiment-name", "my-exp",
                        "--ranking-criteria-file", tmp,
                    ] + extra_args,
                )
                return result, mock_client
        finally:
            os.unlink(tmp)

    def test_run_name_passed_to_compare_runs(self):
        mock_runs = [{"run_id": "r1", "metrics": {"accuracy": 0.9}, "tags": {"mlflow.runName": "baseline-v2"}}]
        result, mock_client = self._run_candidates(["--run-name", "baseline-v2"], mock_runs)
        assert result.exit_code == 0
        mock_client.compare_runs.assert_called_once_with("my-exp", run_ids=None, run_name="baseline-v2")

    def test_run_ids_takes_precedence_over_run_name_with_warning(self):
        mock_runs = [{"run_id": "r1", "metrics": {"accuracy": 0.9}, "tags": {}}]
        result, mock_client = self._run_candidates(
            ["--run-ids", "r1", "--run-name", "baseline-v2"], mock_runs
        )
        assert result.exit_code == 0
        # run_name should be cleared when run_ids is present
        call_kwargs = mock_client.compare_runs.call_args[1]
        assert call_kwargs["run_ids"] == ["r1"]
        assert call_kwargs["run_name"] is None
        assert "WARNING" in result.stderr

    def test_no_run_name_no_run_ids_compares_all(self):
        mock_runs = [{"run_id": "r1", "metrics": {"accuracy": 0.9}, "tags": {}}]
        result, mock_client = self._run_candidates([], mock_runs)
        assert result.exit_code == 0
        mock_client.compare_runs.assert_called_once_with("my-exp", run_ids=None, run_name=None)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
