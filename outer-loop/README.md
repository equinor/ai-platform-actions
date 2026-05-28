# Outer Loop Action

A unified GitHub Action for ML experiment analytics and evaluation: evaluate gates, compare candidates, report on experiments, check monitoring signals, and apply decision policies.

> **⚠️ Implementation status:** The action is designed and structured but has not been fully tested end-to-end. All commands are implemented and wired up; treat this as a preview.

## Overview

The Outer Loop action provides a single entry point for all post-training and production-monitoring workflows. It uses a `verb` + `subject` pattern (e.g. `evaluate gate`, `compare candidates`) to route requests to the appropriate command module. Authentication is handled via a token from the `azLogin` action or, when running locally, via `DefaultAzureCredential`. All metric data is read through an MLFlow backend — either an **MLFlow proxy** service or directly from an **AzureML workspace tracking URI** — the action does not call Azure ML directly except where noted.

### Commands

| Verb | Subject | Purpose |
|------|---------|---------|
| `evaluate` | `gate` | Compare run metrics against thresholds; exit 1 on failure |
| `evaluate` | `policy` | Apply decision policy rules to monitoring signals |
| `compare` | `candidates` | Rank experiment runs by weighted metrics; output best run |
| `report` | `experiment` | Generate an experiment summary and post it as a step summary |
| `check` | `monitoring` | Read latest drift/quality signals and emit a monitoring report |

---

## Commands

### `evaluate gate` — Evaluation Gates

Fetches metrics from MLFlow for a specific run (or the latest run in the experiment if `run-id` is omitted), compares each metric against the constraints in `thresholds-file`, and outputs a pass/fail result. If any metric fails or is missing the action exits with code 1, blocking downstream steps.

**Required inputs:** `mlflow-url`, `experiment-name`, `thresholds-file`  
**Optional inputs:** `run-id`, `token`, `expires-on`

**Thresholds file format:**

```yaml
accuracy:
  min: 0.85
f1_score:
  min: 0.80
loss:
  max: 0.15
```

See [outer-loop-config.md](outer-loop-config.md#thresholdsyaml----used-by-evaluate-gate) for the full format reference.

**Outputs:** `result` (`pass` | `fail`), `summary` (Markdown table)

---

### `evaluate policy` — Decision Policies

Reads the latest monitoring run from MLFlow (experiment `monitoring-<model-name>`, or `experiment-name` if supplied directly), applies the rules in `policy-config-file`, and outputs a recommended action.

Possible recommended actions: `retrain` | `data-refresh` | `label-improvement` | `feature-change` | `code-fix` | `no-change`

**Required inputs:** `mlflow-url`, `policy-config-file`  
**Optional inputs:** `model-name` or `experiment-name`, `token`, `expires-on`

**Policy config file format:**

```yaml
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
```

See [outer-loop-config.md](outer-loop-config.md#policyyaml----used-by-evaluate-policy) for the full format reference.

**Outputs:** `result` (recommended action string), `summary` (Markdown table of signals)

---

### `compare candidates` — Candidate Comparison

Queries MLFlow for all runs in the experiment (or a scoped subset), scores each run using a weighted combination of metrics defined in `ranking-criteria-file`, and outputs the best run ID together with a ranked comparison table posted as a GitHub step summary.

**Required inputs:** `mlflow-url`, `experiment-name`, `ranking-criteria-file`  
**Optional inputs:** `run-ids`, `run-name`, `token`, `expires-on`

Scoping options (mutually exclusive — `run-ids` wins if both are supplied, with a warning):

| Option | Effect |
|--------|--------|
| *(neither)* | Compares all runs in the experiment (up to 100). |
| `run-ids` | Compares only the specified comma-separated run IDs. |
| `run-name` | Compares only runs whose MLflow display name (`mlflow.runName` tag) exactly matches the given value. Useful when multiple training jobs reuse the same experiment name but have distinct display names and you don't know the individual run IDs. |

**Ranking criteria file format:**

```yaml
primary: accuracy
direction: maximize      # maximize | minimize
weights:
  accuracy: 0.7
  f1_score: 0.3
```

See [outer-loop-config.md](outer-loop-config.md#rankingyaml----used-by-compare-candidates) for the full format reference.

**Outputs:** `best-run-id`, `best-run-metrics` (JSON), `summary` (Markdown ranked table)

---

### `report experiment` — Experiment Tracking

Fetches the 20 most recent runs from MLFlow for the named experiment, computes a metric trend (latest run vs. the run before it), and renders a Markdown report that is posted as a GitHub step summary.

**Required inputs:** `mlflow-url`, `experiment-name`  
**Optional inputs:** `token`, `expires-on`

**Outputs:** `summary` (Markdown report with trend table and run list)

---

### `check monitoring` — Monitoring Signals

Reads the latest monitoring run from MLFlow. The monitoring experiment is resolved as `monitoring-<model-name>` unless `experiment-name` is provided directly. Known signals are mapped to a traffic-light status:

| Signal | Key |
|--------|-----|
| Data Drift | `data_drift` |
| Prediction Drift | `prediction_drift` |
| Performance Drop | `performance_drop` |
| Label Quality Drop | `label_quality_drop` |
| Missing Value Rate | `missing_rate` |

Status thresholds: 🔴 > 0.20 &nbsp;|&nbsp; 🟡 > 0.10 &nbsp;|&nbsp; 🟢 ≤ 0.10

**Required inputs:** `mlflow-url`  
**Optional inputs:** `model-name` or `experiment-name`, `model-version`, `token`, `expires-on`

**Outputs:** `result` (JSON-encoded signals dict), `summary` (Markdown report)

---

## Inputs

### Authentication

| Input | Description | Required |
|-------|-------------|----------|
| `token` | Access token from the `azLogin` action. Not needed when running locally. | No |
| `expires-on` | Token expiry as epoch seconds, from the `azLogin` action. | No |

### MLFlow backend

| Input | Description | Required |
|-------|-------------|----------|
| `mlflow-url` | MLFlow backend URL or AzureML tracking URI. Accepts `https://` proxy URLs (e.g. `https://mlflow-proxy.cluster.aurora.equinor.com`) or `azureml://` tracking URIs from an AzureML workspace. | No |

### Experiment / run targeting

| Input | Description | Required |
|-------|-------------|----------|
| `experiment-name` | Azure ML / MLFlow experiment name. | No |
| `run-id` | Single MLFlow run ID. | No |
| `run-ids` | Comma-separated list of MLFlow run IDs for multi-run operations. | No |
| `run-name` | Filter `compare candidates` to runs with this exact display name (`mlflow.runName` tag). Ignored when `run-ids` is also supplied. | No |

### Config files

| Input | Description | Required |
|-------|-------------|----------|
| `thresholds-file` | Path to YAML file with metric pass/fail thresholds (`evaluate gate`). | No |
| `ranking-criteria-file` | Path to YAML file with ranking criteria (`compare candidates`). | No |
| `policy-config-file` | Path to YAML file with decision policy rules (`evaluate policy`). | No |

### Azure ML workspace

| Input | Description | Required |
|-------|-------------|----------|
| `subscription-id` | Azure subscription ID. | No |
| `resource-group` | Azure resource group name. | No |
| `workspace-name` | Azure Machine Learning workspace name. | No |

### Model

| Input | Description | Required |
|-------|-------------|----------|
| `model-name` | Azure ML registered model name. | No |
| `model-version` | Azure ML registered model version. | No |

---

## Outputs

| Output | Description |
|--------|-------------|
| `result` | `pass`/`fail` for `evaluate gate`; recommended action string for `evaluate policy`; JSON signals for `check monitoring`. |
| `best-run-id` | Run ID of the best candidate (`compare candidates` only). |
| `best-run-metrics` | JSON-encoded metrics of the best candidate run (`compare candidates` only). |
| `summary` | Human-readable Markdown summary, also posted as a GitHub step summary. |

---

## Usage Examples

### Evaluate a training gate

```yaml
- name: Evaluate gate
  id: gate
  uses: equinor/ai-platform-actions/outer-loop@main
  with:
    verb: evaluate
    subject: gate
    token: ${{ steps.azLogin.outputs.token }}
    expires-on: ${{ steps.azLogin.outputs.expires-on }}
    mlflow-url: https://mlflow-proxy.cluster.aurora.equinor.com
    experiment-name: my-training-experiment
    run-id: ${{ steps.train.outputs.run-id }}
    thresholds-file: .azureml/thresholds.yaml

- name: Use gate result
  run: echo "Gate result: ${{ steps.gate.outputs.result }}"
```

### Evaluate a training gate using an AzureML tracking URI

```yaml
- name: Evaluate gate (AzureML direct)
  id: gate
  uses: equinor/ai-platform-actions/outer-loop@main
  with:
    verb: evaluate
    subject: gate
    mlflow-url: azureml://swedencentral.api.azureml.ms/mlflow/v1.0/subscriptions/${{ vars.SUBSCRIPTION_ID }}/resourceGroups/${{ vars.RESOURCE_GROUP }}/providers/Microsoft.MachineLearningServices/workspaces/${{ vars.WORKSPACE_NAME }}
    experiment-name: my-training-experiment
    run-id: ${{ steps.train.outputs.run-id }}
    thresholds-file: .azureml/thresholds.yaml
```

### Compare candidate runs and promote the best

```yaml
- name: Compare candidates
  id: compare
  uses: equinor/ai-platform-actions/outer-loop@main
  with:
    verb: compare
    subject: candidates
    token: ${{ steps.azLogin.outputs.token }}
    expires-on: ${{ steps.azLogin.outputs.expires-on }}
    mlflow-url: https://mlflow-proxy.cluster.aurora.equinor.com
    experiment-name: my-training-experiment
    ranking-criteria-file: .azureml/ranking.yaml

- name: Share best model
  uses: equinor/ai-platform-actions/inner-loop@main
  with:
    verb: share
    subject: model
    run-id: ${{ steps.compare.outputs.best-run-id }}
    # ... other share inputs
```

### Compare candidates filtered by run display name

When an experiment accumulates runs from different training jobs that share the same
experiment name but have distinct display names (set via `mlflow.set_tag("mlflow.runName", "baseline-v2")`
or `mlflow.start_run(run_name="baseline-v2")`), use `run-name` to scope the comparison:

```yaml
- name: Compare baseline-v2 candidates
  id: compare
  uses: equinor/ai-platform-actions/outer-loop@main
  with:
    verb: compare
    subject: candidates
    mlflow-url: azureml://swedencentral.api.azureml.ms/mlflow/v1.0/subscriptions/${{ vars.SUBSCRIPTION_ID }}/resourceGroups/${{ vars.RESOURCE_GROUP }}/providers/Microsoft.MachineLearningServices/workspaces/${{ vars.WORKSPACE_NAME }}
    experiment-name: my-training-experiment
    run-name: baseline-v2
    ranking-criteria-file: .azureml/ranking.yaml
```

If you know the exact run IDs, `run-ids` takes precedence and `run-name` is ignored (with a warning).

### Report on an experiment

```yaml
- name: Report experiment
  uses: equinor/ai-platform-actions/outer-loop@main
  with:
    verb: report
    subject: experiment
    token: ${{ steps.azLogin.outputs.token }}
    expires-on: ${{ steps.azLogin.outputs.expires-on }}
    mlflow-url: https://mlflow-proxy.cluster.aurora.equinor.com
    experiment-name: my-training-experiment
```

### Check monitoring signals and apply a decision policy

```yaml
- name: Check monitoring
  id: monitoring
  uses: equinor/ai-platform-actions/outer-loop@main
  with:
    verb: check
    subject: monitoring
    token: ${{ steps.azLogin.outputs.token }}
    expires-on: ${{ steps.azLogin.outputs.expires-on }}
    mlflow-url: https://mlflow-proxy.cluster.aurora.equinor.com
    model-name: my-registered-model

- name: Evaluate policy
  id: policy
  uses: equinor/ai-platform-actions/outer-loop@main
  with:
    verb: evaluate
    subject: policy
    token: ${{ steps.azLogin.outputs.token }}
    expires-on: ${{ steps.azLogin.outputs.expires-on }}
    mlflow-url: https://mlflow-proxy.cluster.aurora.equinor.com
    model-name: my-registered-model
    policy-config-file: .azureml/policy.yaml

- name: Trigger retrain if recommended
  if: steps.policy.outputs.result == 'retrain'
  run: echo "Policy recommends retraining — triggering pipeline"
```

---

## Architecture

### Structure

The action is organized into modular Python files under `src/aip/outer/`:

| File | Purpose |
|------|---------|
| `main.py` | Entry point; registers sub-typers for each verb |
| `evaluate.py` | `evaluate gate` and `evaluate policy` commands |
| `compare.py` | `compare candidates` command |
| `report.py` | `report experiment` command |
| `check.py` | `check monitoring` command |
| `util.py` | MLFlow backend protocol, proxy client, AzureML backend, factory function, authentication helpers, GitHub output utilities |

### Command routing

`main.py` registers one `typer` sub-app per verb:

```
aip.outer.main
  ├── evaluate  →  evaluate.py  (gate, policy)
  ├── compare   →  compare.py   (candidates)
  ├── report    →  report.py    (experiment)
  └── check     →  check.py     (monitoring)
```

The `verb` and `subject` inputs from `action.yaml` are passed directly as positional CLI arguments to the container entrypoint (`python -m aip.outer.main`).

### Container

The action runs as a Docker container:

```
ghcr.io/equinor/ai-platform-actions/outer-loop:latest
```

Built from `Dockerfile` using `astral/uv:python3.12-bookworm-slim` as the base image.

### Authentication

Two modes are supported:

1. **Token-based** (recommended in GitHub Actions): pass `token` and `expires-on` from an upstream `azLogin` step. The token is wrapped in a `StaticTokenCredential` and used for all Azure SDK calls. This mode works with the `MLFlowProxyClient` backend.
2. **DefaultAzureCredential** (local development and AzureML backend): when `token` is omitted, or when using an `azureml://` tracking URI, the standard Azure credential chain is used. The `AzureMLBackend` always uses this path — `azureml-mlflow` manages its own credential resolution via the environment variables set by `azLogin`.

### MLFlow backends

| Input `mlflow-url` prefix | Backend | Auth |
|---------------------------|---------|------|
| `https://` or `http://` | `MLFlowProxyClient` — authenticated HTTP calls to the proxy REST API | Bearer token from `token`/`expires-on` or DefaultAzureCredential |
| `azureml://` | `AzureMLBackend` — converts URI to `https://` and calls the MLflow REST API directly; no `azureml-mlflow` SDK dependency | Bearer token via `AML_SCOPE` — same mechanism as proxy client, fully compatible with `token`/`expires-on` from `azLogin` |
