# Outer Loop Action

A unified GitHub Action for ML experiment analytics and evaluation: evaluate gates, compare candidates, report on experiments, check monitoring signals, and apply decision policies.

> **⚠️ Implementation status:** The action is designed and structured but has not been fully tested end-to-end. All commands are implemented and wired up; treat this as a preview.

## Overview

The Outer Loop action provides a single entry point for all post-training and production-monitoring workflows. It uses a `verb` + `subject` pattern (e.g. `evaluate gate`, `compare candidates`) to route requests to the appropriate command module. Every command requires a caller-supplied bearer `token` (see [Authentication](#authentication-and-tokens)). All metric data is read through the standard [MLflow REST API](https://mlflow.org/docs/latest/rest-api.html) — from any **MLflow tracking server** (`https://`) or from an **AzureML workspace tracking URI** (`azureml://`) — the action does not call Azure ML directly except where noted.

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

**Required inputs:** `mlflow-url`, `token`, `experiment-name`, `thresholds-file`  
**Optional inputs:** `run-id`, `child-run-name`, `expires-on`

Run selection:

| Inputs | Run evaluated |
|--------|---------------|
| `run-id` | That run. |
| `run-id` + `child-run-name` | The child of `run-id` with that MLflow/Studio display name. |
| neither | The latest run in the experiment. |

Use `run-id` + `child-run-name` for pipeline runs: the inner-loop `waitfor job` command returns the **parent** run ID, while the metrics you want to gate on usually belong to one specific child job. `child-run-name` requires `run-id`, and the command fails if the name matches zero or more than one child — the error lists the parent's available child display names.

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

**Outputs:** `result` (`pass` | `fail`), `resolved-run-id` (the run actually evaluated), `summary` (Markdown table)

---

### `evaluate policy` — Decision Policies

Reads the latest monitoring run from MLFlow (experiment `monitoring-<model-name>`, or `experiment-name` if supplied directly), applies the rules in `policy-config-file`, and outputs a recommended action.

Possible recommended actions: `retrain` | `data-refresh` | `label-improvement` | `feature-change` | `code-fix` | `no-change`

**Required inputs:** `mlflow-url`, `token`, `policy-config-file`  
**Optional inputs:** `model-name` or `experiment-name`, `model-version`, `endpoint-name`, `deployment-name`, `max-evidence-age-minutes`, `min-sample-count`, `expires-on`

**Policy config file format:**

```yaml
version: pilot-v1
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

The selected action is the first matching rule, but every matched rule is retained in the decision record. Missing, stale, undersized, or identity-mismatched evidence returns `result: insufficient-evidence` and exits with code 2.

**Outputs:** `result` (recommended action string), `decision-id` (deterministic idempotency key), `decision` (JSON record), `summary` (Markdown table of signals)

---

### `compare candidates` — Candidate Comparison

Queries MLFlow for all runs in the experiment (or a scoped subset), scores each run using a weighted combination of metrics defined in `ranking-criteria-file`, and outputs the best run ID together with a ranked comparison table posted as a GitHub step summary.

**Required inputs:** `mlflow-url`, `token`, `experiment-name`, `ranking-criteria-file`  
**Optional inputs:** `run-ids`, `run-name`, `child-run-name`, `expires-on`

Scoping options (mutually exclusive — `run-ids` wins if both are supplied, with a warning):

| Option | Effect |
|--------|--------|
| *(neither)* | Compares all runs in the experiment (up to 100). |
| `run-ids` | Compares only the specified comma-separated run IDs. |
| `run-name` | Compares only runs whose MLflow display name (`mlflow.runName` tag) exactly matches the given value. Useful when multiple training jobs reuse the same experiment name but have distinct display names and you don't know the individual run IDs. |
| `run-name` + `child-run-name` | Compares only child runs with the given MLflow/Studio display name under matching parent pipeline runs. |

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

**Required inputs:** `mlflow-url`, `token`, `experiment-name`  
**Optional inputs:** `expires-on`

**Outputs:** `summary` (Markdown report with trend table and run list)

---

### `check monitoring` — Monitoring Signals

Reads the latest monitoring run from MLFlow. The monitoring experiment is resolved as `monitoring-<model-name>` unless `experiment-name` is provided directly. Known signals include:

| Signal | Key |
|--------|-----|
| Data Drift | `data_drift` |
| Prediction Drift | `prediction_drift` |
| Performance Drop | `performance_drop` |
| Label Quality Drop | `label_quality_drop` |
| Missing Value Rate | `missing_rate` |

Threshold interpretation belongs to the versioned policy, not the monitoring report.

Autonomous decisions require these MLFlow tags: `aip.monitoring.schema_version=1`, `aip.model.name`, `aip.model.version`, `aip.endpoint.name`, `aip.deployment.name`, and a timezone-aware `aip.observed_at`. Metrics must include `sample_count`.

**Required inputs:** `mlflow-url`, `token`  
**Optional inputs:** `model-name` or `experiment-name`, `model-version`, `endpoint-name`, `deployment-name`, `max-evidence-age-minutes`, `min-sample-count`, `expires-on`

**Outputs:** `result` and `signals` (JSON-encoded signals), `evidence-status`, `evidence-issues`, `summary`. Invalid evidence exits with code 2.

---

## Inputs

### Authentication

| Input | Description | Required |
|-------|-------------|----------|
| `token` | Bearer token sent as `Authorization: Bearer <token>` on every MLflow request. What it must contain depends on `mlflow-url` — see [Authentication](#authentication-and-tokens). | Yes |
| `expires-on` | Token expiry as epoch seconds. Optional for JWTs (the `exp` claim is used; an earlier `expires-on` takes precedence). Required for non-JWT tokens. | No |

### MLFlow backend

| Input | Description | Required |
|-------|-------------|----------|
| `mlflow-url` | MLflow tracking URL or AzureML tracking URI. Accepts an `https://` MLflow tracking server URL, optionally with a path prefix (e.g. `https://mlflow.example.com/my-mlflow`), or an `azureml://` tracking URI from an AzureML workspace. | Yes |

### Experiment / run targeting

| Input | Description | Required |
|-------|-------------|----------|
| `experiment-name` | Azure ML / MLFlow experiment name. | No |
| `run-id` | Single MLFlow run ID. For `evaluate gate`, the run to evaluate, or the parent run when `child-run-name` is also supplied. | No |
| `run-ids` | Comma-separated list of MLFlow run IDs for multi-run operations. | No |
| `run-name` | Filter `compare candidates` to runs with this exact display name (`mlflow.runName` tag). Ignored when `run-ids` is also supplied. | No |
| `child-run-name` | Exact MLflow/Studio display name of a child run. For `compare candidates`, filters children under parents selected by `run-name` (ignored when `run-ids` is supplied). For `evaluate gate`, selects which child of `run-id` to evaluate. | No |

### Config files

| Input | Description | Required |
|-------|-------------|----------|
| `thresholds-file` | Path to YAML file with metric pass/fail thresholds (`evaluate gate`). | No |
| `ranking-criteria-file` | Path to YAML file with ranking criteria (`compare candidates`). | No |
| `policy-config-file` | Path to YAML file with decision policy rules (`evaluate policy`). | No |

### Reserved Azure ML workspace inputs

| Input | Description | Required |
|-------|-------------|----------|
| `subscription-id` | Reserved for future Azure ML SDK operations; currently rejected if supplied. | No |
| `resource-group` | Reserved for future Azure ML SDK operations; currently rejected if supplied. | No |
| `workspace-name` | Reserved for future Azure ML SDK operations; currently rejected if supplied. | No |

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
| `resolved-run-id` | Run ID actually evaluated by `evaluate gate`, after child/latest resolution. |
| `best-run-id` | Run ID of the best candidate (`compare candidates` only). |
| `best-run-metrics` | JSON-encoded metrics of the best candidate run (`compare candidates` only). |
| `summary` | Human-readable Markdown summary, also posted as a GitHub step summary. |

---

## Authentication and tokens

Every command requires `token`. The action does not acquire tokens itself: it sends the supplied token unchanged as `Authorization: Bearer <token>` on every MLflow REST request — the same as `MlflowClient` does with `MLFLOW_TRACKING_TOKEN`. The token value is never logged; only its effective expiry is.

### What the token must contain depends on `mlflow-url`

The server behind `mlflow-url` decides which audience (`aud` claim) and which roles (`roles` claim) it accepts, so the token has to be requested for that server:

| `mlflow-url` | How to request the token | Expected `aud` | Authorization |
|--------------|--------------------------|----------------|---------------|
| `azureml://…` (AzureML workspace tracking URI) | `az account get-access-token --resource https://ml.azure.com` | `https://ml.azure.com` | Azure RBAC on the workspace |
| `https://…` (MLflow server protected by an Entra ID app registration) | `az account get-access-token --scope <resource-id>/.default`, where `<resource-id>` is the app's Application ID URI (e.g. `api://<app-id>`) | `<app-id>` | App role(s) in the `roles` claim, e.g. `<App>.Developer` |

A decoded token for the second case looks like this (abridged):

```json
{
  "aud": "00000000-0000-0000-0000-000000000000",
  "iss": "https://login.microsoftonline.com/<tenant-id>/v2.0",
  "exp": 1791901586,
  "roles": ["<App>.Developer"]
}
```

References: [az account get-access-token](https://learn.microsoft.com/cli/azure/account#az-account-get-access-token), [Access token claims](https://learn.microsoft.com/entra/identity-platform/access-token-claims-reference), [App roles](https://learn.microsoft.com/entra/identity-platform/howto-add-app-roles-in-apps), [MLflow tracking in AzureML](https://learn.microsoft.com/azure/machine-learning/how-to-use-mlflow-configure-tracking), [azure/login](https://github.com/Azure/login).

### Token expiry

- If the token is a JWT (as returned by `az account get-access-token`), its `exp` claim is used. The signature is not verified by the action — that is the server's job.
- `expires-on` (epoch seconds) is optional. If supplied and earlier than `exp`, it takes precedence; the effective expiry is always the earliest of the two. Non-JWT tokens require `expires-on`.
- The command fails early (exit code 1) when the effective expiry has passed or is less than 60 seconds away, and re-checks before every MLflow request.

### Example: AzureML tracking URI with `azure/login@v3`

```yaml
permissions:
  id-token: write
  contents: read

steps:
  - name: Azure Login
    uses: azure/login@v3
    with:
      client-id: ${{ vars.AZURE_CLIENT_ID }}
      tenant-id: ${{ vars.AZURE_TENANT_ID }}
      subscription-id: ${{ vars.SUBSCRIPTION_ID }}

  - name: Get token
    id: get-token
    shell: bash
    run: |
      TOKEN=$(az account get-access-token --resource https://ml.azure.com --query accessToken --output tsv)
      echo "::add-mask::$TOKEN"
      echo "token=$TOKEN" >> "$GITHUB_OUTPUT"

  - name: Report experiment
    uses: equinor/ai-platform-actions/outer-loop@main
    with:
      verb: report
      subject: experiment
      token: ${{ steps.get-token.outputs.token }}
      mlflow-url: azureml://swedencentral.api.azureml.ms/mlflow/v1.0/subscriptions/${{ vars.SUBSCRIPTION_ID }}/resourceGroups/${{ vars.RESOURCE_GROUP }}/providers/Microsoft.MachineLearningServices/workspaces/${{ vars.WORKSPACE_NAME }}
      experiment-name: my-training-experiment
```

### Example: MLflow server protected by an app registration (resource ID)

The identity used by `azure/login` must be assigned the app role the MLflow server requires (e.g. `<App>.Developer`) on the app registration identified by the resource ID.

```yaml
steps:
  - name: Azure Login
    uses: azure/login@v3
    with:
      client-id: ${{ vars.AZURE_CLIENT_ID }}
      tenant-id: ${{ vars.AZURE_TENANT_ID }}
      subscription-id: ${{ vars.SUBSCRIPTION_ID }}

  - name: Get token for the MLflow server
    id: get-token
    shell: bash
    env:
      MLFLOW_RESOURCE_ID: api://00000000-0000-0000-0000-000000000000
    run: |
      TOKEN=$(az account get-access-token --scope "$MLFLOW_RESOURCE_ID/.default" --query accessToken --output tsv)
      echo "::add-mask::$TOKEN"
      echo "token=$TOKEN" >> "$GITHUB_OUTPUT"

  - name: Report experiment
    uses: equinor/ai-platform-actions/outer-loop@main
    with:
      verb: report
      subject: experiment
      token: ${{ steps.get-token.outputs.token }}
      mlflow-url: https://<cluster-host>/<team>-mlflow/
      experiment-name: my-training-experiment
```

The same token can be obtained in Python, e.g. for direct CLI use:

```python
from azure.identity import DefaultAzureCredential

resource_id = "api://00000000-0000-0000-0000-000000000000"
token = DefaultAzureCredential().get_token(f"{resource_id}/.default").token
```

```bash
python -m aip.outer.main report experiment \
  --mlflow-url https://<cluster-host>/<team>-mlflow/ \
  --token "$TOKEN" \
  --experiment-name my-training-experiment
```

---

## Usage Examples

The examples below assume a preceding `get-token` step in the same job, as shown in [Authentication and tokens](#authentication-and-tokens), and a repository variable `MLFLOW_URL` holding the MLflow tracking URL.

### Evaluate a training gate

```yaml
- name: Evaluate gate
  id: gate
  uses: equinor/ai-platform-actions/outer-loop@main
  with:
    verb: evaluate
    subject: gate
    token: ${{ steps.get-token.outputs.token }}
    mlflow-url: ${{ vars.MLFLOW_URL }}
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
    token: ${{ steps.get-token.outputs.token }}
    mlflow-url: azureml://swedencentral.api.azureml.ms/mlflow/v1.0/subscriptions/${{ vars.SUBSCRIPTION_ID }}/resourceGroups/${{ vars.RESOURCE_GROUP }}/providers/Microsoft.MachineLearningServices/workspaces/${{ vars.WORKSPACE_NAME }}
    experiment-name: my-training-experiment
    run-id: ${{ steps.train.outputs.run-id }}
    thresholds-file: .azureml/thresholds.yaml
```

### Evaluate a specific child job of a pipeline run

`waitfor job` returns the parent (pipeline) run ID, so name the child job that holds the metrics.

```yaml
- name: Evaluate gate on the evaluation step
  id: gate
  uses: equinor/ai-platform-actions/outer-loop@main
  with:
    verb: evaluate
    subject: gate
    token: ${{ steps.get-token.outputs.token }}
    mlflow-url: ${{ vars.MLFLOW_URL }}
    experiment-name: my-training-experiment
    run-id: ${{ steps.waitfor.outputs.run-id }}
    child-run-name: evaluate_test
    thresholds-file: .azureml/thresholds.yaml

- name: Show which run was gated
  run: echo "Evaluated run: ${{ steps.gate.outputs.resolved-run-id }}"
```

### Compare candidate runs and promote the best

```yaml
- name: Compare candidates
  id: compare
  uses: equinor/ai-platform-actions/outer-loop@main
  with:
    verb: compare
    subject: candidates
    token: ${{ steps.get-token.outputs.token }}
    mlflow-url: ${{ vars.MLFLOW_URL }}
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
    token: ${{ steps.get-token.outputs.token }}
    mlflow-url: azureml://swedencentral.api.azureml.ms/mlflow/v1.0/subscriptions/${{ vars.SUBSCRIPTION_ID }}/resourceGroups/${{ vars.RESOURCE_GROUP }}/providers/Microsoft.MachineLearningServices/workspaces/${{ vars.WORKSPACE_NAME }}
    experiment-name: my-training-experiment
    run-name: baseline-v2
    ranking-criteria-file: .azureml/ranking.yaml
```

If you know the exact run IDs, `run-ids` takes precedence and `run-name` is ignored (with a warning).

### Compare a named pipeline component across parent jobs

To compare only one component of repeated AzureML pipeline jobs, use the stable parent
pipeline name with the stable component display name. The action resolves the parent runs,
then selects only child runs linked through MLflow's `mlflow.parentRunId` tag.

```yaml
- name: Compare evaluation components
  id: compare
  uses: equinor/ai-platform-actions/outer-loop@main
  with:
    verb: compare
    subject: candidates
    token: ${{ steps.get-token.outputs.token }}
    mlflow-url: azureml://swedencentral.api.azureml.ms/mlflow/v1.0/subscriptions/${{ vars.SUBSCRIPTION_ID }}/resourceGroups/${{ vars.RESOURCE_GROUP }}/providers/Microsoft.MachineLearningServices/workspaces/${{ vars.WORKSPACE_NAME }}
    experiment-name: temporal-equipment-health
    run-name: temporal-equipment-health
    child-run-name: evaluate_test
    ranking-criteria-file: .azureml/ranking.yaml
```

### Report on an experiment

```yaml
- name: Report experiment
  uses: equinor/ai-platform-actions/outer-loop@main
  with:
    verb: report
    subject: experiment
    token: ${{ steps.get-token.outputs.token }}
    mlflow-url: ${{ vars.MLFLOW_URL }}
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
    token: ${{ steps.get-token.outputs.token }}
    mlflow-url: ${{ vars.MLFLOW_URL }}
    model-name: my-registered-model
    model-version: "7"
    endpoint-name: my-batch-endpoint
    deployment-name: production-7
    max-evidence-age-minutes: "60"
    min-sample-count: "100"

- name: Evaluate policy
  id: policy
  uses: equinor/ai-platform-actions/outer-loop@main
  with:
    verb: evaluate
    subject: policy
    token: ${{ steps.get-token.outputs.token }}
    mlflow-url: ${{ vars.MLFLOW_URL }}
    model-name: my-registered-model
    model-version: "7"
    endpoint-name: my-batch-endpoint
    deployment-name: production-7
    max-evidence-age-minutes: "60"
    min-sample-count: "100"
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
| `action_entrypoint.py` | Validates GitHub Action inputs and builds a command-specific CLI invocation |
| `main.py` | Registers sub-typers for each verb and remains the direct CLI entry point |
| `evaluate.py` | `evaluate gate` and `evaluate policy` commands |
| `compare.py` | `compare candidates` command |
| `report.py` | `report experiment` command |
| `check.py` | `check monitoring` command |
| `util.py` | MLFlow backend protocol, MLflow REST backend, factory function, bearer-token validation, GitHub output utilities |

### Command routing

`main.py` registers one `typer` sub-app per verb:

```
aip.outer.main
  ├── evaluate  →  evaluate.py  (gate, policy)
  ├── compare   →  compare.py   (candidates)
  ├── report    →  report.py    (experiment)
  └── check     →  check.py     (monitoring)
```

`action.yaml` exposes its inputs as `INPUT_*` environment variables. The container entrypoint (`python -m aip.outer.action_entrypoint`) validates the selected command, omits blank and inapplicable inputs, and then invokes the Typer application. Direct CLI users can continue to run `python -m aip.outer.main`.

### Container

The action runs as a Docker container:

```
ghcr.io/equinor/ai-platform-actions/outer-loop:latest
```

Built from `Dockerfile` using `astral/uv:python3.12-bookworm-slim` as the base image.

### Authentication

`util.resolve_bearer_token` validates the required `token`, determines its effective expiry (earliest of the JWT `exp` claim and `expires-on`) and fails early on expired or unusable tokens. The resulting `BearerToken` is passed to the backend, which sends it as `Authorization: Bearer <token>` and re-checks expiry before every request. No Azure credential chain is used. See [Authentication and tokens](#authentication-and-tokens).

### MLFlow backends

All URLs are served by a single `MLflowRestBackend`, which calls the standard [MLflow REST API](https://mlflow.org/docs/latest/rest-api.html) at `<base-url>/api/2.0/mlflow/...`; there is no `mlflow`/`azureml-mlflow` SDK dependency.

| Input `mlflow-url` prefix | Base URL used |
|---------------------------|---------------|
| `https://` or `http://` | The URL as given, including any path prefix (e.g. `https://<cluster-host>/<team>-mlflow`) |
| `azureml://` | The URI rewritten to `https://` (same host and path) |
