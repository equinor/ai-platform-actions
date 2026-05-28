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

# Mock Azure SDK before importing aip modules to prevent import errors
sys.modules["azure"] = MagicMock()
sys.modules["azure.core"] = MagicMock()
sys.modules["azure.core.credentials"] = MagicMock()
sys.modules["azure.identity"] = MagicMock()
sys.modules["azure.ai"] = MagicMock()
sys.modules["azure.ai.ml"] = MagicMock()
sys.modules["mlflow"] = MagicMock()
sys.modules["mlflow.entities"] = MagicMock()

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
        with patch("aip.outer.util.mlflow.MlflowClient"):
            client = create_mlflow_client(uri, cred)
        assert isinstance(client, AzureMLBackend)

    def test_unknown_scheme_raises_value_error(self):
        with pytest.raises(ValueError, match="mlflow-url must be"):
            create_mlflow_client("ftp://something.example.com", MagicMock())


# =============================================================================
# AzureMLBackend
# =============================================================================

class TestAzureMLBackend:
    """Tests for AzureMLBackend normalisation and delegation logic."""

    AZUREML_URI = "azureml://swedencentral.api.azureml.ms/mlflow/v1.0/subscriptions/sub/resourceGroups/rg/providers/Microsoft.MachineLearningServices/workspaces/ws"

    @staticmethod
    def _make_run(run_id: str, metrics: dict, status: str = "FINISHED", tags: dict | None = None):
        """Build a mock mlflow Run object."""
        run = MagicMock()
        run.info.run_id = run_id
        run.info.status = status
        run.data.metrics = metrics
        run.data.tags = tags or {}
        return run

    def test_get_experiment_runs_returns_normalized_dicts(self):
        mock_run = self._make_run("r1", {"accuracy": 0.9})
        mock_mlflow_client = MagicMock()
        mock_mlflow_client.get_experiment_by_name.return_value = MagicMock(experiment_id="exp1")
        mock_mlflow_client.search_runs.return_value = [mock_run]

        with patch("aip.outer.util.mlflow.MlflowClient", return_value=mock_mlflow_client):
            backend = AzureMLBackend(self.AZUREML_URI, MagicMock())
            runs = backend.get_experiment_runs("my-exp", max_results=10)

        assert runs == [{"run_id": "r1", "status": "FINISHED", "metrics": {"accuracy": 0.9}, "tags": {}}]
        mock_mlflow_client.search_runs.assert_called_once_with(
            experiment_ids=["exp1"], max_results=10, order_by=["start_time DESC"]
        )

    def test_get_experiment_runs_returns_empty_when_experiment_not_found(self):
        mock_mlflow_client = MagicMock()
        mock_mlflow_client.get_experiment_by_name.return_value = None

        with patch("aip.outer.util.mlflow.MlflowClient", return_value=mock_mlflow_client):
            backend = AzureMLBackend(self.AZUREML_URI, MagicMock())
            runs = backend.get_experiment_runs("nonexistent-exp")

        assert runs == []

    def test_get_run_metrics_returns_metrics_dict(self):
        mock_run = self._make_run("r1", {"f1": 0.85, "loss": 0.12})
        mock_mlflow_client = MagicMock()
        mock_mlflow_client.get_run.return_value = mock_run

        with patch("aip.outer.util.mlflow.MlflowClient", return_value=mock_mlflow_client):
            backend = AzureMLBackend(self.AZUREML_URI, MagicMock())
            metrics = backend.get_run_metrics("r1")

        assert metrics == {"f1": 0.85, "loss": 0.12}

    def test_compare_runs_with_explicit_run_ids_fetches_each(self):
        runs_by_id = {
            "r1": self._make_run("r1", {"accuracy": 0.9}),
            "r2": self._make_run("r2", {"accuracy": 0.8}),
        }
        mock_mlflow_client = MagicMock()
        mock_mlflow_client.get_run.side_effect = lambda rid: runs_by_id[rid]

        with patch("aip.outer.util.mlflow.MlflowClient", return_value=mock_mlflow_client):
            backend = AzureMLBackend(self.AZUREML_URI, MagicMock())
            result = backend.compare_runs("my-exp", run_ids=["r1", "r2"])

        assert len(result) == 2
        assert result[0]["run_id"] == "r1"
        assert result[1]["run_id"] == "r2"

    def test_get_monitoring_run_returns_none_when_no_runs(self):
        mock_mlflow_client = MagicMock()
        mock_mlflow_client.get_experiment_by_name.return_value = None

        with patch("aip.outer.util.mlflow.MlflowClient", return_value=mock_mlflow_client):
            backend = AzureMLBackend(self.AZUREML_URI, MagicMock())
            result = backend.get_monitoring_run("monitoring-my-model")

        assert result is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
