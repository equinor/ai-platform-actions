# Outer Loop — Config File Guide

The outer-loop action reads three YAML config files depending on which command is used. This guide covers the structure, all supported keys, and practical examples for each file.

---

## `thresholds.yaml` — used by `evaluate gate`

Defines pass/fail constraints for run metrics. Each top-level key is a metric name as logged in MLFlow. The value is a constraint object with at minimum one of `min` or `max`; both can be combined.

### Structure

```yaml
<metric_name>:
  min: <float>   # metric must be >= this value
  max: <float>   # metric must be <= this value
```

A metric that is present in `thresholds.yaml` but absent from the run is treated as a failure (`MISSING`).

### Keys

| Key | Type | Description |
|-----|------|-------------|
| `<metric_name>` | mapping | Any metric logged to the MLFlow run. Key name must match exactly. |
| `min` | float | Inclusive lower bound. Metric value must be ≥ `min` to pass. |
| `max` | float | Inclusive upper bound. Metric value must be ≤ `max` to pass. |

### Example

```yaml
accuracy:
  min: 0.85
f1_score:
  min: 0.80
loss:
  max: 0.15
precision:
  min: 0.80
  max: 1.00
```

### Behaviour

- All constraints must pass for the gate to output `result: pass`.
- Any single failure causes the action to exit with code 1 and output `result: fail`.
- The step summary lists every metric with its actual value, constraint, and ✅ / ❌ / ⚠️ status.

---

## `ranking.yaml` — used by `compare candidates`

Defines how candidate runs are scored and ranked. Runs are scored by a weighted sum of their metrics; the run with the highest score is the winner.

### Structure

```yaml
primary: <metric_name>
direction: maximize | minimize
weights:
  <metric_name>: <float>
  ...
```

### Keys

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `primary` | string | Recommended | The single most important metric. Used as a fallback if `weights` is empty. Runs missing the primary metric are ranked last. |
| `direction` | string | Yes | `maximize` — higher values are better. `minimize` — lower values are better (e.g. loss, error rate). Global default applied to all weighted metrics unless overridden by `directions`. |
| `directions` | mapping | No | Per-metric direction overrides. Each key is a metric name; value is `maximize` or `minimize`. Takes precedence over the global `direction` for that metric. |
| `weights` | mapping | Recommended | Relative importance of each metric. Values do not need to sum to 1; they are normalised automatically. If omitted, only `primary` is used with weight 1.0. |

### Scoring formula

$$\text{score} = \text{sign} \times \sum_i \frac{w_i}{\sum_j w_j} \times m_i$$

where sign is `+1` for `maximize` and `-1` for `minimize`, and $m_i$ is the metric value for weight $w_i$. Per-metric direction from `directions` overrides the global sign for that metric. Metrics absent from a run contribute 0 to that run's score. A run missing the `primary` metric is automatically ranked last.

### Example — maximise a classifier

```yaml
primary: accuracy
direction: maximize
weights:
  accuracy: 0.7
  f1_score: 0.3
```

### Example — minimise error with multiple metrics

```yaml
primary: val_loss
direction: minimize
weights:
  val_loss: 0.6
  mae: 0.4
```

### Example — single metric, no weights

```yaml
primary: roc_auc
direction: maximize
```

### Example — mixed direction (loss minimised, accuracy maximised)

```yaml
primary: accuracy
direction: maximize
directions:
  val_loss: minimize
weights:
  accuracy: 0.6
  val_loss: 0.4
```

### Behaviour

- Runs are sorted descending by score; rank 1 is the winner.
- The step summary shows a ranked table with all metric values and computed scores.
- `best-run-id` and `best-run-metrics` outputs contain the winner's run ID and metrics as JSON.

---

## `policy.yaml` — used by `evaluate policy`

Defines thresholds for monitoring signals and the action to recommend when each threshold is breached. The policy is evaluated against the latest monitoring run fetched from the MLFlow proxy.

### Structure

```yaml
drift_threshold: <float>
performance_drop_threshold: <float>
label_quality_threshold: <float>
actions:
  on_drift: <action>
  on_performance_drop: <action>
  on_label_quality: <action>
  default: <action>
```

### Keys

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `drift_threshold` | float | `0.10` | If `data_drift` signal exceeds this value, `on_drift` is recommended. |
| `performance_drop_threshold` | float | `0.05` | If `performance_drop` signal exceeds this value, `on_performance_drop` is recommended. |
| `label_quality_threshold` | float | `0.05` | If `label_quality_drop` signal exceeds this value, `on_label_quality` is recommended. |
| `actions.on_drift` | string | `retrain` | Recommended action when data drift is detected. |
| `actions.on_performance_drop` | string | `retrain` | Recommended action when performance drops below threshold. |
| `actions.on_label_quality` | string | `label-improvement` | Recommended action when label quality drops. |
| `actions.default` | string | `no-change` | Recommended action when no threshold is breached. |

### Supported action values

| Value | Meaning |
|-------|---------|
| `retrain` | Trigger a new training run |
| `data-refresh` | Refresh or re-ingest the training dataset |
| `label-improvement` | Review and correct labels in the training data |
| `feature-change` | Revise or add input features |
| `code-fix` | Address a bug or regression in model/pipeline code |
| `no-change` | No action required |

### Evaluation order

Rules are evaluated in this order; the first match wins:

1. `data_drift` > `drift_threshold` → `on_drift`
2. `performance_drop` > `performance_drop_threshold` → `on_performance_drop`
3. `label_quality_drop` > `label_quality_threshold` → `on_label_quality`
4. No match → `default`

### Example

```yaml
drift_threshold: 0.10
performance_drop_threshold: 0.05
label_quality_threshold: 0.05
actions:
  on_drift: retrain
  on_performance_drop: retrain
  on_label_quality: label-improvement
  default: no-change
```

### Example — stricter thresholds with data-refresh path

```yaml
drift_threshold: 0.05
performance_drop_threshold: 0.03
label_quality_threshold: 0.08
actions:
  on_drift: data-refresh
  on_performance_drop: retrain
  on_label_quality: label-improvement
  default: no-change
```

### Behaviour

- The `result` output is the recommended action string (e.g. `retrain`).
- If no monitoring run exists for the experiment, the action defaults to `no-change` without failing.
- The step summary lists every signal value alongside the recommended action.
- Use `result` in downstream `if:` conditions to conditionally trigger retraining or other workflows.
