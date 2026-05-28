"""
Compare commands for Outer Loop Action.

Verbs:
  compare candidates — rank experiment runs by weighted criteria, output best run ID
"""

import json
from typing import Annotated, Optional

import typer

from .util import (
    create_mlflow_client,
    empty_string_to_none,
    get_credential,
    github_output,
    github_step_summary,
    load_yaml_file,
)

app = typer.Typer()


@app.command(context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def candidates(
    ctx: typer.Context,
    mlflow_url: Annotated[str, typer.Option("--mlflow-url")],
    experiment_name: Annotated[str, typer.Option("--experiment-name")],
    ranking_criteria_file: Annotated[str, typer.Option("--ranking-criteria-file")],
    run_ids: Annotated[Optional[str], typer.Option("--run-ids", callback=empty_string_to_none)] = None,
    token: Annotated[Optional[str], typer.Option("--token", callback=empty_string_to_none)] = None,
    expires_on: Annotated[Optional[str], typer.Option("--expires-on", callback=empty_string_to_none)] = None,
):
    """
    Compare and rank training run candidates by weighted metrics (US2 — Candidate Comparison).

    Queries the MLFlow proxy for runs in the experiment (or a specified subset),
    scores each run according to a weighted ranking criteria YAML, and outputs
    the best run ID together with a ranked comparison table as a GitHub step summary.

    Ranking criteria YAML format:
      primary: accuracy
      direction: maximize        # maximize | minimize (global default)
      directions:                # optional per-metric overrides
        loss: minimize
        accuracy: maximize
      weights:
        accuracy: 0.7
        f1_score: 0.3
    """
    if not mlflow_url:
        typer.echo("[compare candidates] ERROR: --mlflow-url is required", err=True)
        raise typer.Exit(1)
    if not experiment_name:
        typer.echo("[compare candidates] ERROR: --experiment-name is required", err=True)
        raise typer.Exit(1)
    if not ranking_criteria_file:
        typer.echo("[compare candidates] ERROR: --ranking-criteria-file is required", err=True)
        raise typer.Exit(1)

    typer.echo(f"[compare candidates] Experiment: {experiment_name}")
    typer.echo(f"[compare candidates] Ranking criteria file: {ranking_criteria_file}")

    criteria = load_yaml_file(ranking_criteria_file, "ranking criteria")

    run_id_list = [r.strip() for r in run_ids.split(",") if r.strip()] if run_ids else None
    typer.echo(f"[compare candidates] Scoped to run IDs: {run_id_list or '(all experiment runs)'}")

    expires_on_int = int(expires_on) if expires_on else None
    credential = get_credential(token, expires_on_int)
    client = create_mlflow_client(mlflow_url, credential)

    runs = client.compare_runs(experiment_name, run_ids=run_id_list)
    if not runs:
        typer.echo(f"[compare candidates] ERROR: no runs found in experiment '{experiment_name}'", err=True)
        raise typer.Exit(1)

    typer.echo(f"[compare candidates] Found {len(runs)} runs")

    weights: dict[str, float] = criteria.get("weights", {})
    direction: str = criteria.get("direction", "maximize")
    primary: str = criteria.get("primary", "")
    directions: dict[str, str] = criteria.get("directions", {})

    # If no weights defined, fall back to single primary metric
    if not weights and primary:
        weights = {primary: 1.0}

    scored_runs = []
    for run in runs:
        rid = run.get("run_id", "?")
        metrics = run.get("metrics", {})
        score = _compute_score(metrics, weights, direction, primary=primary, directions=directions)
        scored_runs.append({"run_id": rid, "metrics": metrics, "score": score})

    scored_runs.sort(key=lambda r: r["score"], reverse=True)
    best = scored_runs[0]

    typer.echo(f"[compare candidates] Best run: {best['run_id']} (score={best['score']:.4f})")

    # --- Build step summary table ---
    all_metric_names: list[str] = sorted(
        {m for run in scored_runs for m in run["metrics"].keys()}
    )
    header_cols = ["Rank", "Run ID"] + all_metric_names + ["Score"]
    sep_cols = ["-" * len(c) for c in header_cols]

    summary_lines = [
        "## Candidate Comparison",
        f"**Experiment:** `{experiment_name}`",
        "",
        "| " + " | ".join(header_cols) + " |",
        "| " + " | ".join(sep_cols) + " |",
    ]
    for rank, run in enumerate(scored_runs, start=1):
        metric_vals = [
            f"{run['metrics'].get(m, 'N/A'):.4f}" if isinstance(run["metrics"].get(m), float) else str(run["metrics"].get(m, "N/A"))
            for m in all_metric_names
        ]
        prefix = "🥇 " if rank == 1 else ""
        row = [str(rank), f"{prefix}`{run['run_id']}`"] + metric_vals + [f"{run['score']:.4f}"]
        summary_lines.append("| " + " | ".join(row) + " |")

    summary = "\n".join(summary_lines)
    github_step_summary(summary)

    github_output({
        "best-run-id": best["run_id"],
        "best-run-metrics": json.dumps(best["metrics"]),
        "summary": summary,
    })


def _compute_score(
    metrics: dict[str, float],
    weights: dict[str, float],
    direction: str,
    primary: str = "",
    directions: Optional[dict[str, str]] = None,
) -> float:
    """
    Compute a weighted score for a run.

    Uses per-metric direction from ``directions`` if specified, otherwise falls
    back to the global ``direction``.  Returns ``float('-inf')`` if the primary
    metric is absent so that run sorts to last place.
    """
    if primary and metrics.get(primary) is None:
        typer.echo(
            f"[compare candidates] WARNING: primary metric '{primary}' missing from run — ranked last",
            err=True,
        )
        return float("-inf")

    global_sign = 1.0 if direction == "maximize" else -1.0
    total_weight = sum(weights.values()) or 1.0
    score = 0.0
    for metric, weight in weights.items():
        value = metrics.get(metric)
        if value is not None:
            if directions and metric in directions:
                sign = 1.0 if directions[metric] == "maximize" else -1.0
            else:
                sign = global_sign
            score += sign * float(value) * (weight / total_weight)
    return score
