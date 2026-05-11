"""
Evaluate commands for Outer Loop Action.

Verbs:
  evaluate gate    — compare run metrics against YAML thresholds, output pass/fail
  evaluate policy  — apply decision policy rules to monitoring signals
"""

from typing import Annotated, Optional

import typer

from .util import (
    MLFlowProxyClient,
    empty_string_to_none,
    get_credential,
    github_output,
    github_step_summary,
    load_yaml_file,
)

app = typer.Typer()


# ---------------------------------------------------------------------------
# evaluate gate (US1)
# ---------------------------------------------------------------------------

@app.command(context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def gate(
    ctx: typer.Context,
    mlflow_proxy_url: Annotated[str, typer.Option("--mlflow-proxy-url")],
    experiment_name: Annotated[str, typer.Option("--experiment-name")],
    thresholds_file: Annotated[str, typer.Option("--thresholds-file")],
    run_id: Annotated[Optional[str], typer.Option("--run-id", callback=empty_string_to_none)] = None,
    token: Annotated[Optional[str], typer.Option("--token", callback=empty_string_to_none)] = None,
    expires_on: Annotated[Optional[str], typer.Option("--expires-on", callback=empty_string_to_none)] = None,
):
    """
    Evaluate whether a training run meets metric thresholds (US1 — Evaluation Gates).

    Reads metric thresholds from a YAML config file, fetches metrics from the
    MLFlow proxy for the specified run (or the latest run in the experiment),
    and outputs pass/fail plus a Markdown summary table.

    Thresholds YAML format:
      accuracy: {min: 0.85}
      f1_score: {min: 0.80}
      loss: {max: 0.15}
    """
    if not mlflow_proxy_url:
        typer.echo("[evaluate gate] ERROR: --mlflow-proxy-url is required", err=True)
        raise typer.Exit(1)
    if not experiment_name:
        typer.echo("[evaluate gate] ERROR: --experiment-name is required", err=True)
        raise typer.Exit(1)
    if not thresholds_file:
        typer.echo("[evaluate gate] ERROR: --thresholds-file is required", err=True)
        raise typer.Exit(1)

    typer.echo(f"[evaluate gate] Experiment: {experiment_name}")
    typer.echo(f"[evaluate gate] Run ID: {run_id or '(latest)'}")
    typer.echo(f"[evaluate gate] Thresholds file: {thresholds_file}")

    thresholds = load_yaml_file(thresholds_file, "thresholds")

    expires_on_int = int(expires_on) if expires_on else None
    credential = get_credential(token, expires_on_int)
    client = MLFlowProxyClient(mlflow_proxy_url, credential)

    # Resolve run ID — use latest run in experiment if not specified
    if run_id:
        actual_run_id = run_id
    else:
        runs = client.get_experiment_runs(experiment_name, max_results=1)
        if not runs:
            typer.echo(f"[evaluate gate] ERROR: no runs found in experiment '{experiment_name}'", err=True)
            raise typer.Exit(1)
        actual_run_id = runs[0]["run_id"]
        typer.echo(f"[evaluate gate] Resolved to latest run: {actual_run_id}")

    metrics = client.get_run_metrics(actual_run_id)
    typer.echo(f"[evaluate gate] Metrics: {metrics}")

    # Evaluate each threshold
    rows: list[dict] = []
    passed = True
    for metric_name, constraint in thresholds.items():
        actual = metrics.get(metric_name)
        if actual is None:
            status = "MISSING"
            passed = False
        else:
            ok = True
            if "min" in constraint and actual < constraint["min"]:
                ok = False
            if "max" in constraint and actual > constraint["max"]:
                ok = False
            status = "PASS" if ok else "FAIL"
            if not ok:
                passed = False
        rows.append({
            "metric": metric_name,
            "actual": actual,
            "constraint": constraint,
            "status": status,
        })

    result = "pass" if passed else "fail"
    typer.echo(f"[evaluate gate] Overall result: {result.upper()}")

    # Build Markdown summary table
    summary_lines = [
        f"## Evaluation Gate — {result.upper()}",
        f"**Experiment:** `{experiment_name}`  **Run:** `{actual_run_id}`",
        "",
        "| Metric | Actual | Threshold | Status |",
        "|--------|--------|-----------|--------|",
    ]
    for row in rows:
        constraint_str = ", ".join(f"{k}: {v}" for k, v in row["constraint"].items())
        actual_str = f"{row['actual']:.4f}" if isinstance(row["actual"], float) else str(row["actual"])
        status_icon = "✅" if row["status"] == "PASS" else ("❌" if row["status"] == "FAIL" else "⚠️")
        summary_lines.append(f"| {row['metric']} | {actual_str} | {constraint_str} | {status_icon} {row['status']} |")

    summary = "\n".join(summary_lines)
    github_step_summary(summary)

    github_output({
        "result": result,
        "summary": summary,
    })

    if not passed:
        typer.echo("[evaluate gate] Gate FAILED — exiting with code 1")
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# evaluate policy (US9)
# ---------------------------------------------------------------------------

@app.command(context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def policy(
    ctx: typer.Context,
    mlflow_proxy_url: Annotated[str, typer.Option("--mlflow-proxy-url")],
    policy_config_file: Annotated[str, typer.Option("--policy-config-file")],
    experiment_name: Annotated[Optional[str], typer.Option("--experiment-name", callback=empty_string_to_none)] = None,
    model_name: Annotated[Optional[str], typer.Option("--model-name", callback=empty_string_to_none)] = None,
    token: Annotated[Optional[str], typer.Option("--token", callback=empty_string_to_none)] = None,
    expires_on: Annotated[Optional[str], typer.Option("--expires-on", callback=empty_string_to_none)] = None,
):
    """
    Apply decision policy rules to monitoring signals (US9 — Decision Policies).

    Reads monitoring metrics from the MLFlow proxy (latest monitoring run),
    applies policy rules defined in a YAML config, and outputs the recommended
    action: retrain | data-refresh | label-improvement | feature-change | code-fix | no-change.

    Policy config YAML format:
      drift_threshold: 0.10
      performance_drop_threshold: 0.05
      label_quality_threshold: 0.05
      data_staleness_threshold: 0.20
      feature_drift_threshold: 0.15
      code_issue_threshold: 0.10
      actions:
        on_drift: retrain
        on_performance_drop: retrain
        on_label_quality: label-improvement
        on_data_staleness: data-refresh
        on_feature_drift: feature-change
        on_code_issue: code-fix
        default: no-change
    """
    if not mlflow_proxy_url:
        typer.echo("[evaluate policy] ERROR: --mlflow-proxy-url is required", err=True)
        raise typer.Exit(1)
    if not policy_config_file:
        typer.echo("[evaluate policy] ERROR: --policy-config-file is required", err=True)
        raise typer.Exit(1)

    typer.echo(f"[evaluate policy] Policy config: {policy_config_file}")
    typer.echo(f"[evaluate policy] Monitoring experiment: {experiment_name or model_name}")

    policy_config = load_yaml_file(policy_config_file, "policy config")

    expires_on_int = int(expires_on) if expires_on else None
    credential = get_credential(token, expires_on_int)
    client = MLFlowProxyClient(mlflow_proxy_url, credential)

    monitoring_experiment = experiment_name or f"monitoring-{model_name}"
    monitoring_run = client.get_monitoring_run(monitoring_experiment)

    if monitoring_run is None:
        typer.echo("[evaluate policy] No monitoring run found — defaulting to no-change")
        recommended_action = "no-change"
        signals: dict = {}
    else:
        signals = monitoring_run.get("metrics", {})
        recommended_action = _apply_policy(signals, policy_config)

    typer.echo(f"[evaluate policy] Signals: {signals}")
    typer.echo(f"[evaluate policy] Recommended action: {recommended_action}")

    summary_lines = [
        "## Decision Policy Evaluation",
        f"**Model:** `{model_name or experiment_name}`",
        "",
        f"**Recommended action:** `{recommended_action}`",
        "",
        "### Monitoring Signals",
        "| Signal | Value |",
        "|--------|-------|",
    ]
    for k, v in signals.items():
        summary_lines.append(f"| {k} | {v} |")

    summary = "\n".join(summary_lines)
    github_step_summary(summary)

    github_output({
        "result": recommended_action,
        "summary": summary,
    })


def _apply_policy(signals: dict, policy_config: dict) -> str:
    """Apply policy rules to monitoring signals and return the recommended action.

    Rules are evaluated in priority order; the first matching threshold wins.
    """
    actions_config = policy_config.get("actions", {})

    drift = signals.get("data_drift", 0.0)
    drift_threshold = policy_config.get("drift_threshold", 0.10)
    if drift > drift_threshold:
        return actions_config.get("on_drift", "retrain")

    perf_drop = signals.get("performance_drop", 0.0)
    perf_threshold = policy_config.get("performance_drop_threshold", 0.05)
    if perf_drop > perf_threshold:
        return actions_config.get("on_performance_drop", "retrain")

    label_quality = signals.get("label_quality_drop", 0.0)
    label_threshold = policy_config.get("label_quality_threshold", 0.05)
    if label_quality > label_threshold:
        return actions_config.get("on_label_quality", "label-improvement")

    data_staleness = signals.get("data_staleness", 0.0)
    data_staleness_threshold = policy_config.get("data_staleness_threshold", 0.20)
    if data_staleness > data_staleness_threshold:
        return actions_config.get("on_data_staleness", "data-refresh")

    feature_drift = signals.get("feature_drift", 0.0)
    feature_drift_threshold = policy_config.get("feature_drift_threshold", 0.15)
    if feature_drift > feature_drift_threshold:
        return actions_config.get("on_feature_drift", "feature-change")

    code_issue = signals.get("code_issue", 0.0)
    code_issue_threshold = policy_config.get("code_issue_threshold", 0.10)
    if code_issue > code_issue_threshold:
        return actions_config.get("on_code_issue", "code-fix")

    return actions_config.get("default", "no-change")
