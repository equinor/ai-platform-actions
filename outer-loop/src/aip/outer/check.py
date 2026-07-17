"""
Check commands for Outer Loop Action.

Verbs:
  check monitoring — read latest drift / quality signals from MLFlow proxy and emit a report
"""

import json
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
)

app = typer.Typer()

# Signals we look for in monitoring runs, with display labels
KNOWN_SIGNALS = {
    "data_drift": "Data Drift",
    "prediction_drift": "Prediction Drift",
    "performance_drop": "Performance Drop",
    "label_quality_drop": "Label Quality Drop",
    "missing_rate": "Missing Value Rate",
}


@app.command(context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def monitoring(
    ctx: typer.Context,
    mlflow_url: Annotated[str, typer.Option("--mlflow-url")],
    model_name: Annotated[Optional[str], typer.Option("--model-name", callback=empty_string_to_none)] = None,
    experiment_name: Annotated[Optional[str], typer.Option("--experiment-name", callback=empty_string_to_none)] = None,
    model_version: Annotated[Optional[str], typer.Option("--model-version", callback=empty_string_to_none)] = None,
    endpoint_name: Annotated[Optional[str], typer.Option("--endpoint-name", callback=empty_string_to_none)] = None,
    deployment_name: Annotated[Optional[str], typer.Option("--deployment-name", callback=empty_string_to_none)] = None,
    max_evidence_age_minutes: Annotated[int, typer.Option("--max-evidence-age-minutes", min=1)] = 1440,
    min_sample_count: Annotated[int, typer.Option("--min-sample-count", min=1)] = 1,
    token: Annotated[Optional[str], typer.Option("--token", callback=empty_string_to_none)] = None,
    expires_on: Annotated[Optional[str], typer.Option("--expires-on", callback=empty_string_to_none)] = None,
):
    """
    Read latest monitoring signals from the MLFlow proxy and emit a drift/quality report (US8).

    Monitoring signals are stored as metrics in a dedicated monitoring experiment
    named ``monitoring-<model-name>`` (or the experiment name supplied directly).
    The command outputs a structured JSON report and a Markdown step summary.
    """
    if not mlflow_url:
        typer.echo("[check monitoring] ERROR: --mlflow-url is required", err=True)
        raise typer.Exit(1)

    monitoring_experiment = experiment_name or (f"monitoring-{model_name}" if model_name else None)
    if not monitoring_experiment:
        typer.echo("[check monitoring] ERROR: supply --experiment-name or --model-name", err=True)
        raise typer.Exit(1)

    typer.echo(f"[check monitoring] Monitoring experiment: {monitoring_experiment}")

    expires_on_int = int(expires_on) if expires_on else None
    credential = get_credential(token, expires_on_int)
    client = create_mlflow_client(mlflow_url, credential)

    monitoring_run = client.get_monitoring_run(monitoring_experiment)

    if monitoring_run is None:
        typer.echo(f"[check monitoring] No monitoring run found for '{monitoring_experiment}'")
        signals: dict = {}
        run_id_display = "N/A"
    else:
        signals = monitoring_run.get("metrics", {})
        run_id_display = monitoring_run.get("run_id", "?")
        typer.echo(f"[check monitoring] Latest monitoring run: {run_id_display}")
        typer.echo(f"[check monitoring] Signals: {signals}")

    evidence_issues = validate_monitoring_evidence(
        monitoring_run,
        model_name=model_name,
        model_version=model_version,
        endpoint_name=endpoint_name,
        deployment_name=deployment_name,
        max_age=timedelta(minutes=max_evidence_age_minutes),
        min_sample_count=min_sample_count,
    )
    evidence_status = "insufficient-evidence" if evidence_issues else "valid"
    typer.echo(f"[check monitoring] Evidence status: {evidence_status}")

    # Build report
    summary_lines = [
        f"## Monitoring Report",
        f"**Model:** `{model_name or monitoring_experiment}`"
        + (f"  **Version:** `{model_version}`" if model_version else ""),
        f"**Monitoring run:** `{run_id_display}`",
        f"**Evidence status:** `{evidence_status}`",
        "",
        "| Signal | Value |",
        "|--------|-------|",
    ]
    for key, label in KNOWN_SIGNALS.items():
        val = signals.get(key)
        if val is None:
            summary_lines.append(f"| {label} | N/A |")
        else:
            summary_lines.append(f"| {label} | {val:.4f} |")

    # Emit any additional signals not in the known list
    for key, val in signals.items():
        if key not in KNOWN_SIGNALS:
            summary_lines.append(f"| {key} | {val} |")

    summary = "\n".join(summary_lines)
    github_step_summary(summary)

    github_output({
        "result": json.dumps(signals),
        "signals": json.dumps(signals),
        "evidence-status": evidence_status,
        "evidence-issues": json.dumps(evidence_issues),
        "summary": summary,
    })

    if evidence_issues:
        raise typer.Exit(2)
