"""
Evaluate commands for Outer Loop Action.

Verbs:
  evaluate gate    — compare run metrics against YAML thresholds, output pass/fail
  evaluate policy  — apply decision policy rules to monitoring signals
"""

import json
import hashlib
from datetime import timedelta
from typing import Annotated, Optional

import typer

from .evidence import validate_monitoring_evidence
from .util import (
    create_mlflow_client,
    empty_string_to_none,
    get_credential,
    github_output,
    github_step_summary,
    load_yaml_file,
    run_display_name,
)

app = typer.Typer()

SUPPORTED_POLICY_ACTIONS = {
    "retrain",
    "data-refresh",
    "label-improvement",
    "feature-change",
    "code-fix",
    "rollback",
    "no-change",
}

POLICY_RULES = (
    ("data_drift", "drift_threshold", 0.10, "on_drift", "retrain"),
    ("performance_drop", "performance_drop_threshold", 0.05, "on_performance_drop", "retrain"),
    ("label_quality_drop", "label_quality_threshold", 0.05, "on_label_quality", "label-improvement"),
    ("data_staleness", "data_staleness_threshold", 0.20, "on_data_staleness", "data-refresh"),
    ("feature_drift", "feature_drift_threshold", 0.15, "on_feature_drift", "feature-change"),
    ("code_issue", "code_issue_threshold", 0.10, "on_code_issue", "code-fix"),
)


# ---------------------------------------------------------------------------
# evaluate gate (US1)
# ---------------------------------------------------------------------------

@app.command()
def gate(
    mlflow_url: Annotated[str, typer.Option("--mlflow-url")],
    experiment_name: Annotated[str, typer.Option("--experiment-name")],
    thresholds_file: Annotated[str, typer.Option("--thresholds-file")],
    run_id: Annotated[Optional[str], typer.Option("--run-id", callback=empty_string_to_none)] = None,
    child_run_name: Annotated[Optional[str], typer.Option("--child-run-name", callback=empty_string_to_none)] = None,
    token: Annotated[Optional[str], typer.Option("--token", callback=empty_string_to_none)] = None,
    expires_on: Annotated[Optional[str], typer.Option("--expires-on", callback=empty_string_to_none)] = None,
):
    """
    Evaluate whether a training run meets metric thresholds (US1 — Evaluation Gates).

    Reads metric thresholds from a YAML config file, fetches metrics from MLFlow
    for the specified run (or the latest run in the experiment), and outputs
    pass/fail plus a Markdown summary table.

    When --child-run-name is supplied, --run-id is treated as the parent (pipeline)
    run and the named child job is evaluated instead.  This matches the inner-loop
    'waitfor job' output, which returns the parent run ID.

    Thresholds YAML format:
      accuracy: {min: 0.85}
      f1_score: {min: 0.80}
      loss: {max: 0.15}
    """
    if not mlflow_url:
        typer.echo("[evaluate gate] ERROR: --mlflow-url is required", err=True)
        raise typer.Exit(1)
    if not experiment_name:
        typer.echo("[evaluate gate] ERROR: --experiment-name is required", err=True)
        raise typer.Exit(1)
    if not thresholds_file:
        typer.echo("[evaluate gate] ERROR: --thresholds-file is required", err=True)
        raise typer.Exit(1)
    if child_run_name and not run_id:
        typer.echo(
            "[evaluate gate] ERROR: --child-run-name requires --run-id (the parent run)",
            err=True,
        )
        raise typer.Exit(1)

    typer.echo(f"[evaluate gate] Experiment: {experiment_name}")
    typer.echo(f"[evaluate gate] Run ID: {run_id or '(latest)'}")
    if child_run_name:
        typer.echo(f"[evaluate gate] Child run name: {child_run_name!r}")
    typer.echo(f"[evaluate gate] Thresholds file: {thresholds_file}")

    thresholds = load_yaml_file(thresholds_file, "thresholds")

    expires_on_int = int(expires_on) if expires_on else None
    credential = get_credential(token, expires_on_int)
    client = create_mlflow_client(mlflow_url, credential)

    # Resolve run ID — use latest run in experiment if not specified
    if run_id and child_run_name:
        actual_run_id = _resolve_child_run_id(client, experiment_name, run_id, child_run_name)
        typer.echo(f"[evaluate gate] Resolved child run: {actual_run_id}")
    elif run_id:
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
    run_line = f"**Experiment:** `{experiment_name}`  **Run:** `{actual_run_id}`"
    if child_run_name:
        run_line = (
            f"**Experiment:** `{experiment_name}`  **Parent run:** `{run_id}`  "
            f"**Child run:** `{child_run_name}` (`{actual_run_id}`)"
        )
    summary_lines = [
        f"## Evaluation Gate — {result.upper()}",
        run_line,
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
        "resolved-run-id": actual_run_id,
        "summary": summary,
    })

    if not passed:
        typer.echo("[evaluate gate] Gate FAILED — exiting with code 1")
        raise typer.Exit(1)


def _resolve_child_run_id(
    client, experiment_name: str, parent_run_id: str, child_run_name: str
) -> str:
    """Return the run ID of the uniquely named child of ``parent_run_id``."""
    children = client.get_child_runs(experiment_name, parent_run_id)
    if not children:
        typer.echo(
            f"[evaluate gate] ERROR: run '{parent_run_id}' has no child runs. "
            "Omit --child-run-name to evaluate this run directly.",
            err=True,
        )
        raise typer.Exit(1)

    matches = [c for c in children if run_display_name(c) == child_run_name]
    if not matches:
        available = ", ".join(sorted({run_display_name(c) for c in children if run_display_name(c)}))
        typer.echo(
            f"[evaluate gate] ERROR: no child run named {child_run_name!r} under run "
            f"'{parent_run_id}'. Available child runs: {available or '(unnamed)'}",
            err=True,
        )
        raise typer.Exit(1)
    if len(matches) > 1:
        matched_ids = ", ".join(c["run_id"] for c in matches)
        typer.echo(
            f"[evaluate gate] ERROR: {len(matches)} child runs named {child_run_name!r} "
            f"under run '{parent_run_id}': {matched_ids}. "
            "Pass the exact child run ID with --run-id instead.",
            err=True,
        )
        raise typer.Exit(1)
    return matches[0]["run_id"]


# ---------------------------------------------------------------------------
# evaluate policy (US9)
# ---------------------------------------------------------------------------

@app.command()
def policy(
    mlflow_url: Annotated[str, typer.Option("--mlflow-url")],
    policy_config_file: Annotated[str, typer.Option("--policy-config-file")],
    experiment_name: Annotated[Optional[str], typer.Option("--experiment-name", callback=empty_string_to_none)] = None,
    model_name: Annotated[Optional[str], typer.Option("--model-name", callback=empty_string_to_none)] = None,
    model_version: Annotated[Optional[str], typer.Option("--model-version", callback=empty_string_to_none)] = None,
    endpoint_name: Annotated[Optional[str], typer.Option("--endpoint-name", callback=empty_string_to_none)] = None,
    deployment_name: Annotated[Optional[str], typer.Option("--deployment-name", callback=empty_string_to_none)] = None,
    max_evidence_age_minutes: Annotated[int, typer.Option("--max-evidence-age-minutes", min=1)] = 1440,
    min_sample_count: Annotated[int, typer.Option("--min-sample-count", min=1)] = 1,
    token: Annotated[Optional[str], typer.Option("--token", callback=empty_string_to_none)] = None,
    expires_on: Annotated[Optional[str], typer.Option("--expires-on", callback=empty_string_to_none)] = None,
):
    """
    Apply decision policy rules to monitoring signals (US9 — Decision Policies).

    Reads monitoring metrics from MLFlow (latest monitoring run), applies policy
    rules defined in a YAML config, and outputs the recommended action:
    retrain | data-refresh | label-improvement | feature-change | code-fix | no-change.

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
    if not mlflow_url:
        typer.echo("[evaluate policy] ERROR: --mlflow-url is required", err=True)
        raise typer.Exit(1)
    if not policy_config_file:
        typer.echo("[evaluate policy] ERROR: --policy-config-file is required", err=True)
        raise typer.Exit(1)
    if not experiment_name and not model_name:
        typer.echo("[evaluate policy] ERROR: supply --experiment-name or --model-name", err=True)
        raise typer.Exit(1)

    typer.echo(f"[evaluate policy] Policy config: {policy_config_file}")
    typer.echo(f"[evaluate policy] Monitoring experiment: {experiment_name or model_name}")

    policy_config = load_yaml_file(policy_config_file, "policy config")
    policy_version = _validate_policy_config(policy_config)

    expires_on_int = int(expires_on) if expires_on else None
    credential = get_credential(token, expires_on_int)
    client = create_mlflow_client(mlflow_url, credential)

    monitoring_experiment = experiment_name or f"monitoring-{model_name}"
    monitoring_run = client.get_monitoring_run(monitoring_experiment)

    evidence_issues = validate_monitoring_evidence(
        monitoring_run,
        model_name=model_name,
        model_version=model_version,
        endpoint_name=endpoint_name,
        deployment_name=deployment_name,
        max_age=timedelta(minutes=max_evidence_age_minutes),
        min_sample_count=min_sample_count,
    )
    signals = monitoring_run.get("metrics", {}) if monitoring_run else {}
    matched_rules: list[dict] = []
    if evidence_issues:
        recommended_action = "insufficient-evidence"
        typer.echo(f"[evaluate policy] Evidence rejected: {'; '.join(evidence_issues)}")
    else:
        matched_rules = _matching_policy_rules(signals, policy_config)
        recommended_action = (
            matched_rules[0]["action"]
            if matched_rules
            else policy_config.get("actions", {}).get("default", "no-change")
        )

    typer.echo(f"[evaluate policy] Signals: {signals}")
    typer.echo(f"[evaluate policy] Recommended action: {recommended_action}")

    summary_lines = [
        "## Decision Policy Evaluation",
        f"**Model:** `{model_name or experiment_name}`",
        "",
        f"**Recommended action:** `{recommended_action}`",
        "",
    ]
    if evidence_issues:
        summary_lines += [
            "### Evidence Issues",
            *[f"- {issue}" for issue in evidence_issues],
            "",
        ]
    summary_lines += [
        "### Monitoring Signals",
        "| Signal | Value |",
        "|--------|-------|",
    ]
    for k, v in signals.items():
        summary_lines.append(f"| {k} | {v} |")

    summary = "\n".join(summary_lines)
    github_step_summary(summary)

    evidence_run_id = monitoring_run.get("run_id") if monitoring_run else None
    decision_material = "|".join([
        monitoring_experiment,
        evidence_run_id or "no-evidence",
        policy_version,
    ])
    decision_id = hashlib.sha256(decision_material.encode("utf-8")).hexdigest()
    decision = {
        "schema_version": "1",
        "decision_id": decision_id,
        "policy_version": policy_version,
        "status": "insufficient-evidence" if evidence_issues else "decided",
        "recommended_action": recommended_action,
        "model_name": model_name,
        "model_version": model_version,
        "endpoint_name": endpoint_name,
        "deployment_name": deployment_name,
        "evidence_experiment": monitoring_experiment,
        "evidence_run_id": evidence_run_id,
        "evidence_issues": evidence_issues,
        "matched_rules": matched_rules,
    }

    github_output({
        "result": recommended_action,
        "decision-id": decision_id,
        "decision": json.dumps(decision, sort_keys=True),
        "summary": summary,
    })

    if evidence_issues:
        raise typer.Exit(2)


def _apply_policy(signals: dict, policy_config: dict) -> str:
    """Apply policy rules to monitoring signals and return the recommended action.

    Rules are evaluated in priority order; the first matching threshold wins.
    """
    matched_rules = _matching_policy_rules(signals, policy_config)
    if matched_rules:
        return matched_rules[0]["action"]
    return policy_config.get("actions", {}).get("default", "no-change")


def _matching_policy_rules(signals: dict, policy_config: dict) -> list[dict]:
    """Return all breached rules in their configured priority order."""
    actions_config = policy_config.get("actions", {})
    matches: list[dict] = []
    for signal_name, threshold_name, default_threshold, action_name, default_action in POLICY_RULES:
        value = signals.get(signal_name, 0.0)
        threshold = policy_config.get(threshold_name, default_threshold)
        if value > threshold:
            matches.append({
                "signal": signal_name,
                "value": value,
                "threshold": threshold,
                "action": actions_config.get(action_name, default_action),
            })
    return matches


def _validate_policy_config(policy_config: dict) -> str:
    """Validate an autonomous decision policy and return its version."""
    policy_version = str(policy_config.get("version", "")).strip()
    if not policy_version:
        raise typer.BadParameter("policy config must define a non-empty 'version'")

    for _, threshold_name, _, _, _ in POLICY_RULES:
        if threshold_name not in policy_config:
            continue
        threshold = policy_config[threshold_name]
        if not isinstance(threshold, (int, float)) or threshold < 0:
            raise typer.BadParameter(f"{threshold_name} must be a non-negative number")

    actions_config = policy_config.get("actions", {})
    if not isinstance(actions_config, dict):
        raise typer.BadParameter("actions must be a mapping")
    unsupported_actions = sorted(
        {action for action in actions_config.values() if action not in SUPPORTED_POLICY_ACTIONS}
    )
    if unsupported_actions:
        raise typer.BadParameter(
            f"unsupported policy action(s): {', '.join(unsupported_actions)}"
        )
    return policy_version
