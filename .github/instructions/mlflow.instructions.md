---
description: "Use when creating or modifying python files in components that interact with the MLFlow server built in to an AzureML workspace. Some methods are not supported, and alternatives should be used."
applyTo: "assets/components/**/*.py"
---

## MLflow Compatibility in AzureML Components

### Problem: Unsupported MLflow Model Registry Endpoints

AzureML's MLflow tracking backend does **not** support newer MLflow model registry APIs. Attempting to use them results in 404 errors on unsupported endpoints.

### Incompatible MLflow Methods (DO NOT USE)

These methods try to access endpoints that AzureML doesn't support and will fail:

- `mlflow.sklearn.log_model()` — Tries to create logged model in registry (`/api/2.0/mlflow/logged-models`)
- `mlflow.sklearn.save_model()` — May trigger registry operations
- `mlflow.sklearn.load_model()` — Unnecessary indirection
- `mlflow.register_model()` — Tries to search logged models (`/api/2.0/mlflow/logged-models/search`)
- `mlflow.models.Model.log()` — High-level wrapper that uses registry
- Any method that references "logged_models" or "model_registry"

**Error pattern if you use these:** `mlflow.exceptions.MlflowException: API request to endpoint /api/2.0/mlflow/logged-models[...] failed with error code 404`

### Safe MLflow Methods (USE THESE)

These methods only use basic artifact and metrics APIs that AzureML supports:

- `mlflow.log_artifact()` — Log files/directories as artifacts ✅
- `mlflow.log_metrics()` — Log numeric metrics ✅
- `mlflow.log_params()` — Log parameters ✅
- `mlflow.set_tags()` — Log tags ✅
- `mlflow.active_run()` — Get current run context ✅
- `mlflow.start_run()` — Start a new run ✅
- `mlflow.get_tracking_uri()` — Get tracking URL ✅

### Correct Pattern for Model Logging

Instead of `mlflow.sklearn.log_model()`, use this pattern:

```python
import joblib
from mlflow.models import Model, infer_signature
import mlflow

# 1. Save model with joblib (not MLflow)
joblib.dump(model, str(model_path / "model.pkl"))

# 2. Create MLmodel metadata manually
mlmodel = Model(
    artifact_path="model",
    flavors={"python_function": {"loader_module": "mlflow.sklearn", "python_version": "3.11"}},
    signature=infer_signature(X_sample, y_sample),
)
mlmodel.save(str(model_path / "MLmodel"))

# 3. Create conda.yaml for reproducibility
conda_yaml = """channels:
  - conda-forge
dependencies:
  - python=3.11
  - pip
  - pip:
      - joblib>=1.3,<2
      - scikit-learn>=1.5,<2
name: mlflow-env
"""
(model_path / "conda.yaml").write_text(conda_yaml, encoding="utf-8")

# 4. Log the directory as an artifact (not a logged model)
mlflow.log_artifact(str(model_path), artifact_path="model")
```

### Loading Models

Instead of `mlflow.sklearn.load_model()`:

```python
import joblib

model = joblib.load(str(model_path / "model.pkl"))
```

### Import Requirements

- Add `joblib>=1.3,<2` to component environment dependencies
- `azureml.mlflow` should be imported at module level (not in functions)

### What NOT to Do

- ❌ Don't call `mlflow.sklearn.log_model()` or `mlflow.sklearn.save_model()`
- ❌ Don't call `mlflow.register_model()` or model registry APIs
- ❌ Don't use `mlflow.models.Model.log()` high-level wrapper
- ❌ Don't try to search or list logged models
- ❌ Don't skip the `conda.yaml` file in model directories

### Validation

Before committing component changes that involve model logging:
1. ✅ No `mlflow.sklearn.log_model()` calls
2. ✅ No `mlflow.register_model()` calls
3. ✅ Model directory has `MLmodel`, `conda.yaml`, and model artifact
4. ✅ Only using safe MLflow APIs for metrics/params/artifacts

---