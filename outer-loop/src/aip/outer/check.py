"""
Check commands for Outer Loop Action.

Verbs:
  check monitoring — read latest drift / quality signals from MLFlow proxy and emit a report
"""

import json
from typing import Annotated, Optional

import typer

from .util import (
    MLFlowProxyClient,
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
    mlflow_proxy_url: Annotated[str, typer.Option("--mlflow-proxy-url")],
    model_name: Annotated[Optional[str], typer.Option("--model-name", callback=empty_string_to_none)] = None,
    experiment_name: Annotated[Optional[str], typer.Option("--experiment-name", callback=empty_string_to_none)] = None,
    model_version: Annotated[Optional[str], typer.Option("--model-version", callback=empty_string_to_none)] = None,
    token: Annotated[Optional[str], typer.Option("--token", callback=empty_string_to_none)] = None,
    expires_on: Annotated[Optional[str], typer.Option("--expires-on", callback=empty_string_to_none)] = None,
):
    """
    Read latest monitoring signals from the MLFlow proxy and emit a drift/quality report (US8).

    Monitoring signals are stored as metrics in a dedicated monitoring experiment
    named ``monitoring-<model-name>`` (or the experiment name supplied directly).
    The command outputs a structured JSON report and a Markdown step summary.
    """
    if not mlflow_proxy_url:
        typer.echo("[check monitoring] ERROR: --mlflow-proxy-url is required", err=True)
        raise typer.Exit(1)

    monitoring_experiment = experiment_name or (f"monitoring-{model_name}" if model_name else None)
    if not monitoring_experiment:
        typer.echo("[check monitoring] ERROR: supply --experiment-name or --model-name", err=True)
        raise typer.Exit(1)

    typer.echo(f"[check monitoring] Monitoring experiment: {monitoring_experiment}")

    expires_on_int = int(expires_on) if expires_on else None
    credential = get_credential(token, expires_on_int)
    client = MLFlowProxyClient(mlflow_proxy_url, credential)

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

    # Build report
    summary_lines = [
        f"## Monitoring Report",
        f"**Model:** `{model_name or monitoring_experiment}`"
        + (f"  **Version:** `{model_version}`" if model_version else ""),
        f"**Monitoring run:** `{run_id_display}`",
        "",
        "| Signal | Value | Status |",
        "|--------|-------|--------|",
    ]
    for key, label in KNOWN_SIGNALS.items():
        val = signals.get(key)
        if val is None:
            summary_lines.append(f"| {label} | N/A | ⚪ No data |")
        else:
            # Simple traffic-light: >0.10 is amber/red, ≤0.10 is green
            if val > 0.20:
                icon = "🔴"
            elif val > 0.10:
                icon = "🟡"
            else:
                icon = "🟢"
            summary_lines.append(f"| {label} | {val:.4f} | {icon} |")

    # Emit any additional signals not in the known list
    for key, val in signals.items():
        if key not in KNOWN_SIGNALS:
            summary_lines.append(f"| {key} | {val} | ⚪ |")

    summary = "\n".join(summary_lines)
    github_step_summary(summary)

    github_output({
        "result": json.dumps(signals),
        "summary": summary,
    })
