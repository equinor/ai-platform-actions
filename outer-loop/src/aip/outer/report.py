"""
Report commands for Outer Loop Action.

Verbs:
  report experiment — generate and post an experiment summary as a GitHub step summary
"""

from typing import Annotated, Optional

import typer

from .util import (
    create_mlflow_client,
    empty_string_to_none,
    get_credential,
    github_output,
    github_step_summary,
)

app = typer.Typer()


@app.command()
def experiment(
    mlflow_url: Annotated[str, typer.Option("--mlflow-url")],
    experiment_name: Annotated[str, typer.Option("--experiment-name")],
    token: Annotated[Optional[str], typer.Option("--token", callback=empty_string_to_none)] = None,
    expires_on: Annotated[Optional[str], typer.Option("--expires-on", callback=empty_string_to_none)] = None,
):
    """
    Generate an experiment summary and post it as a GitHub step summary (US3 — Experiment Tracking).

    Fetches the most recent runs from the MLFlow proxy, computes a run count and
    metric trend (latest run vs. the run before it), and renders a Markdown report.
    """
    if not mlflow_url:
        typer.echo("[report experiment] ERROR: --mlflow-url is required", err=True)
        raise typer.Exit(1)
    if not experiment_name:
        typer.echo("[report experiment] ERROR: --experiment-name is required", err=True)
        raise typer.Exit(1)

    typer.echo(f"[report experiment] Experiment: {experiment_name}")

    expires_on_int = int(expires_on) if expires_on else None
    credential = get_credential(token, expires_on_int)
    client = create_mlflow_client(mlflow_url, credential)

    runs = client.get_experiment_runs(experiment_name, max_results=20)
    typer.echo(f"[report experiment] Found {len(runs)} recent runs")

    summary_lines = [
        f"## Experiment Report: `{experiment_name}`",
        f"**Total runs (last 20):** {len(runs)}",
        "",
    ]

    if not runs:
        summary_lines.append("_No runs found in this experiment._")
    else:
        # Collect all metric names present across the runs
        all_metric_names: list[str] = sorted(
            {m for run in runs for m in run.get("metrics", {}).keys()}
        )

        # --- Trend: latest vs previous ---
        if len(runs) >= 2 and all_metric_names:
            latest = runs[0].get("metrics", {})
            previous = runs[1].get("metrics", {})
            summary_lines += [
                "### Metric Trend (latest vs previous run)",
                "",
                "| Metric | Previous | Latest | Δ |",
                "|--------|----------|--------|---|",
            ]
            for m in all_metric_names:
                prev_val = previous.get(m)
                curr_val = latest.get(m)
                if prev_val is not None and curr_val is not None:
                    delta = curr_val - prev_val
                    arrow = "↑" if delta > 0 else ("↓" if delta < 0 else "→")
                    summary_lines.append(
                        f"| {m} | {prev_val:.4f} | {curr_val:.4f} | {arrow} {delta:+.4f} |"
                    )
            summary_lines.append("")

        # --- Run table ---
        summary_lines += [
            "### Recent Runs",
            "",
            "| Run ID | Status | " + " | ".join(all_metric_names) + " | Tags |",
            "| ------ | ------ | " + " | ".join(["---"] * len(all_metric_names)) + " | ---- |",
        ]
        for run in runs:
            rid = run.get("run_id", "?")
            status = run.get("status", "?")
            metric_vals = [
                f"{run.get('metrics', {}).get(m, 'N/A'):.4f}"
                if isinstance(run.get("metrics", {}).get(m), float)
                else str(run.get("metrics", {}).get(m, "N/A"))
                for m in all_metric_names
            ]
            tags_raw = run.get("tags", {})
            git_sha = tags_raw.get("mlflow.source.git.commit", "")
            tags_display = f"`{git_sha[:7]}`" if git_sha else ""
            summary_lines.append(
                f"| `{rid}` | {status} | " + " | ".join(metric_vals) + f" | {tags_display} |"
            )

    summary = "\n".join(summary_lines)
    github_step_summary(summary)
    github_output({"summary": summary})
