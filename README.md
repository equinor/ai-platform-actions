# AI-Platform-Actions

Reusable GitHub Actions for Azure Machine Learning workflows.

---

## Table of Contents

- [Motivation: Why, When, and How](#motivation-why-when-and-how)
  - [Who is this for?](#who-is-this-for)
  - [The Problem](#the-problem)
  - [When Do You Need This?](#when-do-you-need-this)
  - [Why Use It?](#why-use-it)
  - [The Key Idea: Splitting Your Project into Assets](#the-key-idea-splitting-your-project-into-assets)
  - [What Do These YAML Files Look Like?](#what-do-these-yaml-files-look-like)
  - [How Does the Automation Work?](#how-does-the-automation-work)
  - [A Toy Example: End to End](#a-toy-example-end-to-end)
  - [Using AI Assistance to Generate Workflows](#using-ai-assistance-to-generate-workflows)
- [Actions Reference](#actions-reference)
- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Advanced Patterns](#advanced-patterns)
- [Branching Strategy](#branching-strategy)
- [Contributing](#contributing)

---

## Motivation: Why, When, and How

### Who is this for?

You are a data scientist. You understand model training, data preparation, and evaluation — but you may never have written a GitHub Actions workflow before. This section explains, from scratch, why this repository exists, when you need it, and how to get started.

---

### The Problem

You have built a machine learning project. It works on your laptop. Now you want to:

- Run training in the cloud (Azure ML)
- Keep your models, data, and environments versioned
- Collaborate with your team through a shared workspace
- Automate deployments so pushing code actually *does something*

The gap between "it works locally" and "it runs in the cloud automatically" is large. That gap is what **ai-platform-actions** bridges.

---

### When Do You Need This?

You need ai-platform-actions **when you start saving your machine learning artifacts in a GitHub repository** and want that repository to interact with an [Azure ML workspace](https://learn.microsoft.com/en-us/azure/machine-learning/concept-workspace).

Typical trigger points:

| Moment | What happens |
|--------|-------------|
| You push a new training component | The component is deployed to the workspace automatically |
| You update a conda environment file | The environment is rebuilt in Azure ML |
| You register new training data | The data asset appears in the workspace |
| You submit a job definition | A training run starts in the cloud |
| A model is ready for production | The model is shared to a registry for wider use |

If none of this is happening automatically today, you are probably doing it by hand with `az ml` CLI commands or the Azure ML Studio UI. This repository replaces that manual work with automation.

---

### Why Use It?

**Consistency.** Every team member pushes to the same repository; every push triggers the same workflow. No more "it works on my machine."

**Traceability.** Every asset deployed to the workspace is linked to a Git commit. You can always answer "which version of the code produced this model?"

**Speed.** Once set up, deploying an updated component takes a `git push`, not a series of CLI commands.

**Safety.** Pull requests can deploy to a development workspace first. Only merged code reaches production.

---

### The Key Idea: Splitting Your Project into Assets

Before any automation can work, your project must be organized into the logical pieces that Azure ML understands. These pieces are called **assets**. If you have used Azure ML Studio, you have seen them in the left-hand menu.

#### What are assets?

| Asset type | What it is | Typical file |
|------------|-----------|--------------|
| **Environment** | The Python version and all packages your code needs (think: `requirements.txt` or `conda.yml`, packaged as a Docker image) | `environment.yaml` |
| **Data** | A reference to your training/test data (CSV, Parquet, etc.) | `data.yaml` |
| **Component** | A reusable piece of code with defined inputs and outputs (e.g., "train model", "split data") | `component.yaml` |
| **Model** | A trained model artifact, optionally with metadata | `model.yaml` |
| **Job** | A description of how to wire components together: which data goes in, which compute to use, what to run | `job.yaml` |

Each asset lives in its own folder and is described by a YAML file. This is how Azure ML knows what to do with it.

> **Ref:** [Azure ML assets overview](https://learn.microsoft.com/en-us/azure/machine-learning/concept-assets-v2)

#### Example repository layout

```
my-ml-project/
  assets/
    environments/
      my-env/
        environment.yaml          # Defines Python version + packages
        conda_dependencies.yaml   # Conda specification
    data/
      my-training-data/
        data.yaml                 # Points to your data source
    components/
      train-model/
        component.yaml            # Defines inputs, outputs, command
        src/
          train.py                # Your actual training code
      evaluate-model/
        component.yaml
        src/
          evaluate.py
    jobs/
      training-pipeline/
        job.yaml                  # Wires components + data together
```

---

### What Do These YAML Files Look Like?

If you have never seen an Azure ML YAML file, here is what the key fields mean.

#### Environment YAML

```yaml
$schema: https://azuremlschemas.azureedge.net/latest/environment.schema.json
name: my-env                  # Name as it will appear in the workspace
version: 1                    # Version number (auto-managed by the action)
image: mcr.microsoft.com/azureml/openmpi4.1.0-ubuntu22.04  # Base Docker image
conda_file: conda_dependencies.yaml   # Path to your conda/pip spec
description: "Environment for training my model"
```

| Field | Purpose |
|-------|---------|
| `$schema` | Tells Azure ML which kind of asset this is |
| `name` | The identifier you will use to reference this environment |
| `version` | Lets you track changes over time |
| `image` | The base Docker image that your packages are installed on top of |
| `conda_file` | Points to the file listing your Python dependencies |

> **Ref:** [Azure ML environment YAML schema](https://learn.microsoft.com/en-us/azure/machine-learning/reference-yaml-environment)

#### Component YAML

```yaml
$schema: https://azuremlschemas.azureedge.net/latest/commandComponent.schema.json
name: train-model
version: 1
display_name: Train Model
type: command
inputs:
  training_data:
    type: uri_folder            # The component expects a folder of data
  learning_rate:
    type: number
    default: 0.01
outputs:
  model_output:
    type: uri_folder
code: ./src                     # Where your Python source code lives
environment:
  azureml:my-env:1              # Which environment to run in
command: >-
  python train.py
  --data ${{inputs.training_data}}
  --lr ${{inputs.learning_rate}}
  --output ${{outputs.model_output}}
```

| Field | Purpose |
|-------|---------|
| `name` | Unique name of the component in the workspace |
| `inputs` / `outputs` | Defines what data flows in and out |
| `code` | Folder containing your source files |
| `environment` | Which Azure ML environment to use (by name and version) |
| `command` | The shell command to execute; `${{inputs.X}}` are replaced at runtime |

> **Ref:** [Azure ML component YAML schema](https://learn.microsoft.com/en-us/azure/machine-learning/reference-yaml-component-command)

#### Job YAML

```yaml
$schema: https://azuremlschemas.azureedge.net/latest/pipelineJob.schema.json
type: pipeline
display_name: my-training-pipeline
compute: azureml:cpu-cluster
inputs:
  raw_data:
    type: uri_folder
    path: azureml:my-training-data:1
jobs:
  train_step:
    component: azureml:train-model:1
    inputs:
      training_data: ${{parent.inputs.raw_data}}
      learning_rate: 0.001
    outputs:
      model_output:
        mode: rw_mount
```

| Field | Purpose |
|-------|---------|
| `type: pipeline` | This job orchestrates multiple components |
| `compute` | Which Azure ML compute cluster to run on |
| `inputs` | Pipeline-level inputs (data references) |
| `jobs` | The steps in the pipeline, each referencing a component |

> **Ref:** [Azure ML job YAML schema](https://learn.microsoft.com/en-us/azure/machine-learning/reference-yaml-job-pipeline)

---

### How Does the Automation Work?

Once your repository has assets in folders with YAML definitions, you add a **GitHub Actions workflow** file. This file tells GitHub: "when code changes, run these steps."

#### The workflow in plain language

```
1. Someone pushes code or opens a pull request
2. GitHub detects which asset folders changed
3. For each changed asset, deploy it to the Azure ML workspace
4. Optionally: wait for builds to finish, run a job, share to a registry
```

#### A minimal workflow file

Create this file at `.github/workflows/ml-inner-loop.yml` in your repository:

```yaml
name: ML Inner Loop

on:
  push:
    branches: [main, develop]

jobs:
  deploy-assets:
    runs-on: ubuntu-latest
    steps:
      # Step 1: Check out the repository
      - uses: actions/checkout@v4

      # Step 2: Log in to Azure
      #   The id: field lets later steps reference the login outputs
      - name: Azure Login
        id: azure-login
        uses: azure/login@v2
        with:
          client-id: ${{ secrets.AZURE_CLIENT_ID }}
          tenant-id: ${{ secrets.AZURE_TENANT_ID }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
          enable-AzPSSession: true
          auth-type: SERVICE_PRINCIPAL

      # Step 3: Deploy the environment definition to the workspace
      - name: Deploy environment
        id: deploy-env
        uses: equinor/ai-platform-actions/inner-loop@main
        with:
          verb: deploy
          subject: environment
          token: ${{ steps.azure-login.outputs.access-token }}
          expires-on: ${{ steps.azure-login.outputs.expires-on }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
          resource-group: ${{ secrets.AZURE_RESOURCE_GROUP }}
          workspace-name: ${{ secrets.AZURE_ML_WORKSPACE_NAME }}
          filepath: assets/environments/my-env/environment.yaml

      # Step 4: Wait for the environment image to finish building
      #   The environment is a Docker image — Azure ML needs time to build it.
      #   Downstream steps that depend on the environment must not start
      #   until the build succeeds.
      - name: Wait for environment
        uses: equinor/ai-platform-actions/inner-loop@main
        with:
          verb: waitfor
          subject: environment
          token: ${{ steps.azure-login.outputs.access-token }}
          expires-on: ${{ steps.azure-login.outputs.expires-on }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
          resource-group: ${{ secrets.AZURE_RESOURCE_GROUP }}
          workspace-name: ${{ secrets.AZURE_ML_WORKSPACE_NAME }}
          env-ref: ${{ steps.deploy-env.outputs.reference }}

      # Step 5: Pin the component to the exact environment version just built
      #   The component YAML may reference "azureml:my-env:1", but after a
      #   new deploy the version has incremented. override-inputs rewrites the
      #   environment reference in the YAML so the component uses the freshly
      #   built environment.
      - name: Override environment in component
        uses: equinor/ai-platform-actions/override-inputs@main
        with:
          file: assets/components/train-model/component.yaml
          path: environment
          set-value: ${{ steps.deploy-env.outputs.reference }}

      # Step 6: Deploy the component
      - name: Deploy component
        uses: equinor/ai-platform-actions/inner-loop@main
        with:
          verb: deploy
          subject: component
          token: ${{ steps.azure-login.outputs.access-token }}
          expires-on: ${{ steps.azure-login.outputs.expires-on }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
          resource-group: ${{ secrets.AZURE_RESOURCE_GROUP }}
          workspace-name: ${{ secrets.AZURE_ML_WORKSPACE_NAME }}
          filepath: assets/components/train-model/component.yaml

      # Step 7: Submit a training job
      #   Job operations require an additional aml-token (Azure ML scope)
      - name: Run training job
        uses: equinor/ai-platform-actions/inner-loop@main
        with:
          verb: deploy
          subject: job
          token: ${{ steps.azure-login.outputs.access-token }}
          expires-on: ${{ steps.azure-login.outputs.expires-on }}
          aml-token: ${{ steps.azure-login.outputs.aml-token }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
          resource-group: ${{ secrets.AZURE_RESOURCE_GROUP }}
          workspace-name: ${{ secrets.AZURE_ML_WORKSPACE_NAME }}
          filepath: assets/jobs/training-pipeline/job.yaml
```

#### What each workflow field means

| Field | Meaning |
|-------|---------|
| `on: push: branches:` | Trigger the workflow when code is pushed to these branches |
| `runs-on: ubuntu-latest` | The workflow runs on a Linux virtual machine hosted by GitHub |
| `uses: actions/checkout@v4` | Copies your repository code into the runner |
| `uses: azure/login@v2` | Authenticates the runner to your Azure subscription |
| `id: azure-login` | Gives the login step a name so later steps can read its outputs |
| `uses: equinor/ai-platform-actions/inner-loop@main` | Calls one of the actions from this repository |
| `verb` | The operation: `deploy`, `share`, `waitfor`, or `delete` |
| `subject` | The asset type: `environment`, `component`, `data`, `model`, `job`, `online-endpoint`, `online-deployment` |
| `token` / `expires-on` | Access token and expiry from the Azure login step — passed to every inner-loop call |
| `aml-token` | An additional token scoped to Azure ML (`https://ml.azure.com/.default`), required specifically for **job** operations |
| `filepath` | Path to the YAML file that describes the asset |
| `env-ref` | Reference to an environment (name + version), used by `waitfor environment` to poll the right build |
| `subscription-id`, `resource-group`, `workspace-name` | Identify which Azure ML workspace to target |
| `secrets.XYZ` | Values stored securely in your GitHub repository settings — never hardcoded |
| **override-inputs** | |
| `file` | The YAML file to modify (changes are ephemeral — only within this workflow run) |
| `path` | Dot-notation path to the property to overwrite (e.g., `environment`) |
| `set-value` | The new value — here, the freshly deployed environment reference |
| `value-type` | How to interpret `set-value`: `string` (quoted, current default), `auto` (YAML type inference) or `raw` (a yq expression). Leaving it unset is deprecated and logs a warning |

> **Ref:** [GitHub Actions quickstart](https://docs.github.com/en/actions/quickstart) &middot; [Setting up secrets](https://docs.github.com/en/actions/security-for-github-actions/security-guides/using-secrets-in-github-actions)

---

### A Toy Example: End to End

Imagine you are building an iris flower classifier. Here is the full journey from local code to automated cloud deployment.

#### 1. Organize your project

```
iris-project/
  assets/
    environments/
      iris-env/
        environment.yaml
        conda.yaml
    data/
      iris-data/
        data.yaml
    components/
      train-iris/
        component.yaml
        src/
          train.py
    jobs/
      iris-pipeline/
        job.yaml
  .github/
    workflows/
      ml-inner-loop.yml           # ← The workflow file from above
```

#### 2. Write your training code

`assets/components/train-iris/src/train.py` — your normal Python script:

```python
import argparse
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
import joblib, os

parser = argparse.ArgumentParser()
parser.add_argument("--data", type=str)
parser.add_argument("--output", type=str)
args = parser.parse_args()

df = pd.read_csv(os.path.join(args.data, "iris.csv"))
X, y = df.drop("species", axis=1), df["species"]
model = RandomForestClassifier().fit(X, y)

os.makedirs(args.output, exist_ok=True)
joblib.dump(model, os.path.join(args.output, "model.pkl"))
```

#### 3. Define the YAML assets

Each YAML file is small and declarative — it describes *what* you want, not *how* to build it.

#### 4. Push to GitHub

```bash
git add .
git commit -m "Add iris training pipeline"
git push origin develop
```

#### 5. Watch the workflow run

Go to the **Actions** tab in your GitHub repository. You will see the workflow deploying your environment, component, and job — all automatically.

---

### Using AI Assistance to Generate Workflows

If you use VS Code with GitHub Copilot, you can ask it to generate the workflow for you. Because this repository provides templates and conventions, a prompt like:

> *"Create a new inner-loop workflow. Deploy the data `iris-data`, train a model using `train-iris` component. Set up the environment `iris-env` based on `conda.yaml`. Chain the dependencies together. Finally, create an online endpoint `iris-endpoint` from the trained model."*

…will produce a nearly complete inner-loop workflow file, with the correct action references, dependency ordering, and YAML structure.

---

## Actions Reference

### inner-loop

The main action. Consolidates all Azure ML operations into a single, flexible action with a `verb`/`subject` interface.

| Verb | Subjects | Description |
|------|----------|-------------|
| `deploy` | `data`, `environment`, `component`, `model`, `job`, `online-endpoint`, `online-deployment` | Deploy assets to an Azure ML workspace |
| `share` | `data`, `environment`, `component`, `model` | Share assets from a workspace to a registry |
| `waitfor` | `data`, `environment`, `component`, `model`, `job`, `online-endpoint`, `online-deployment` | Poll until an asset reaches a terminal state |
| `delete` | `online-endpoint`, `online-deployment` | Remove endpoints or deployments |

Full reference: [inner-loop/README.md](inner-loop/README.md) &middot; Examples: [inner-loop/EXAMPLES.md](inner-loop/EXAMPLES.md)

### changed-files

Detects changes to Azure ML assets by monitoring YAML definition files and their related source files (Python, Dockerfiles, etc.). Outputs a JSON array compatible with matrix strategies and inner-loop inputs.

Full reference: [changed-files/README.md](changed-files/README.md)

### override-inputs

Overwrites a value in a YAML file using `yq`. Changes are ephemeral — they only persist within the current workflow run. Used to chain outputs from one step into the inputs of another (e.g., pinning a component to the environment version that was just deployed).

The optional `value-type` input controls how `set-value` is written: `string` writes a quoted string (`"45"`), `auto` infers the YAML type (`45` as an integer, `true` as a boolean), and `raw` treats `set-value` as a yq expression. The default is `string`, but leaving `value-type` unset is deprecated and logs a warning — a future major release will default to `auto`.

Full reference: [override-inputs/README.md](override-inputs/README.md)

---

## Prerequisites

### Azure Authentication

**Important:** All actions in this repository require Azure authentication. You must include the Azure login step **with an `id`** so that later steps can reference the login outputs (tokens).

```yaml
- name: Azure Login
  id: azure-login
  uses: azure/login@v2
  with:
    client-id: ${{ secrets.AZURE_CLIENT_ID }}
    tenant-id: ${{ secrets.AZURE_TENANT_ID }}
    subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
    enable-AzPSSession: true
    auth-type: SERVICE_PRINCIPAL
```

The login step produces three outputs used by inner-loop:

| Output | Used by | Purpose |
|--------|---------|---------|
| `steps.azure-login.outputs.access-token` | All inner-loop calls (`token`) | Authenticates against Azure Resource Manager |
| `steps.azure-login.outputs.expires-on` | All inner-loop calls (`expires-on`) | Token expiry — lets the action refresh if needed |
| `steps.azure-login.outputs.aml-token` | Job operations only (`aml-token`) | Token scoped to `https://ml.azure.com/.default` |

This authentication step only needs to be called once per workflow job.

### Repository Secrets

Configure these in your GitHub repository (Settings → Secrets and variables → Actions):

| Secret | Description |
|--------|-------------|
| `AZURE_CLIENT_ID` | Service principal or federated credential client ID |
| `AZURE_TENANT_ID` | Azure Active Directory tenant ID |
| `AZURE_SUBSCRIPTION_ID` | Azure subscription containing your workspace |
| `AZURE_RESOURCE_GROUP` | Resource group containing your workspace |
| `AZURE_ML_WORKSPACE_NAME` | Name of your Azure ML workspace |

---

## Quick Start

The most common pattern is to use the `changed-files` action to detect which assets changed, then deploy them using the `inner-loop` action.

```yaml
name: Deploy Changed Assets

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  detect-changes:
    runs-on: ubuntu-latest
    outputs:
      changed-files-json: ${{ steps.changed-files.outputs.changed-files-json }}
      has-changes: ${{ steps.changed-files.outputs.has-changes }}
    steps:
      - uses: actions/checkout@v4

      - uses: equinor/ai-platform-actions/changed-files@main
        id: changed-files
        with:
          filter-pattern: "assets/**/*.yaml"

  deploy-assets:
    if: ${{ needs.detect-changes.outputs.has-changes == 'true' }}
    needs: detect-changes
    runs-on: ubuntu-latest
    strategy:
      matrix:
        asset: ${{ fromJson(needs.detect-changes.outputs.changed-files-json) }}
      max-parallel: 3
      fail-fast: false
    steps:
      - uses: actions/checkout@v4

      - name: Azure Login
        id: azure-login
        uses: azure/login@v2
        with:
          client-id: ${{ secrets.AZURE_CLIENT_ID }}
          tenant-id: ${{ secrets.AZURE_TENANT_ID }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
          enable-AzPSSession: true
          auth-type: SERVICE_PRINCIPAL

      - name: Deploy asset
        uses: equinor/ai-platform-actions/inner-loop@main
        with:
          verb: deploy
          subject: ${{ matrix.asset.subject }}
          token: ${{ steps.azure-login.outputs.access-token }}
          expires-on: ${{ steps.azure-login.outputs.expires-on }}
          aml-token: ${{ steps.azure-login.outputs.aml-token }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
          resource-group: ${{ secrets.AZURE_RESOURCE_GROUP }}
          workspace-name: ${{ secrets.AZURE_ML_WORKSPACE_NAME }}
          filepath: ${{ matrix.asset.filepath }}
```

### Output Format from changed-files

The `changed-files` action outputs a JSON array where each object contains:
- `subject`: The asset type (`environment`, `component`, `data`, `job`)
- `filepath`: Path to the YAML definition file

```json
[
  { "subject": "environment", "filepath": "assets/environments/my-env/environment.yaml" },
  { "subject": "component",   "filepath": "assets/components/train/component.yaml" }
]
```

This format is designed to map directly to the inner-loop `subject` and `filepath` inputs.

---

## Advanced Patterns

### Chained Deployment with Waitfor and Override

When assets depend on each other (e.g., a component depends on an environment), use `waitfor` and `override-inputs` to enforce ordering:

```yaml
jobs:
  deploy-pipeline:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Azure Login
        id: azure-login
        uses: azure/login@v2
        with:
          client-id: ${{ secrets.AZURE_CLIENT_ID }}
          tenant-id: ${{ secrets.AZURE_TENANT_ID }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
          enable-AzPSSession: true
          auth-type: SERVICE_PRINCIPAL

      # 1. Deploy environment
      - name: Deploy environment
        id: deploy-env
        uses: equinor/ai-platform-actions/inner-loop@main
        with:
          verb: deploy
          subject: environment
          token: ${{ steps.azure-login.outputs.access-token }}
          expires-on: ${{ steps.azure-login.outputs.expires-on }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
          resource-group: ${{ secrets.AZURE_RESOURCE_GROUP }}
          workspace-name: ${{ secrets.AZURE_ML_WORKSPACE_NAME }}
          filepath: assets/environments/training-env/environment.yaml

      # 2. Wait for environment image build to complete
      - name: Wait for environment
        uses: equinor/ai-platform-actions/inner-loop@main
        with:
          verb: waitfor
          subject: environment
          token: ${{ steps.azure-login.outputs.access-token }}
          expires-on: ${{ steps.azure-login.outputs.expires-on }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
          resource-group: ${{ secrets.AZURE_RESOURCE_GROUP }}
          workspace-name: ${{ secrets.AZURE_ML_WORKSPACE_NAME }}
          env-ref: ${{ steps.deploy-env.outputs.reference }}

      # 3. Pin the component to the freshly built environment version
      - name: Override environment in component
        uses: equinor/ai-platform-actions/override-inputs@main
        with:
          file: assets/components/train/component.yaml
          path: environment
          set-value: ${{ steps.deploy-env.outputs.reference }}

      # 4. Deploy component (now locked to the correct environment)
      - name: Deploy component
        id: deploy-comp
        uses: equinor/ai-platform-actions/inner-loop@main
        with:
          verb: deploy
          subject: component
          token: ${{ steps.azure-login.outputs.access-token }}
          expires-on: ${{ steps.azure-login.outputs.expires-on }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
          resource-group: ${{ secrets.AZURE_RESOURCE_GROUP }}
          workspace-name: ${{ secrets.AZURE_ML_WORKSPACE_NAME }}
          filepath: assets/components/train/component.yaml

      # 5. Override the component version in the job YAML
      - name: Override component in job
        uses: equinor/ai-platform-actions/override-inputs@main
        with:
          file: assets/jobs/pipeline/job.yaml
          path: jobs.train_step.component
          set-value: ${{ steps.deploy-comp.outputs.reference }}

      # 6. Submit the job (requires aml-token)
      - name: Run training job
        uses: equinor/ai-platform-actions/inner-loop@main
        with:
          verb: deploy
          subject: job
          token: ${{ steps.azure-login.outputs.access-token }}
          expires-on: ${{ steps.azure-login.outputs.expires-on }}
          aml-token: ${{ steps.azure-login.outputs.aml-token }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
          resource-group: ${{ secrets.AZURE_RESOURCE_GROUP }}
          workspace-name: ${{ secrets.AZURE_ML_WORKSPACE_NAME }}
          filepath: assets/jobs/pipeline/job.yaml
```

### Conditional Deployment by Asset Type

Filter matrix results to deploy only certain asset types:

```yaml
  deploy-environments-only:
    if: ${{ needs.detect-changes.outputs.has-changes == 'true' }}
    needs: detect-changes
    runs-on: ubuntu-latest
    strategy:
      matrix:
        asset: ${{ fromJson(needs.detect-changes.outputs.changed-files-json) }}
    steps:
      - uses: actions/checkout@v4

      - name: Azure Login
        id: azure-login
        uses: azure/login@v2
        with:
          client-id: ${{ secrets.AZURE_CLIENT_ID }}
          tenant-id: ${{ secrets.AZURE_TENANT_ID }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
          enable-AzPSSession: true
          auth-type: SERVICE_PRINCIPAL

      - name: Deploy Environment
        if: ${{ matrix.asset.subject == 'environment' }}
        uses: equinor/ai-platform-actions/inner-loop@main
        with:
          verb: deploy
          subject: environment
          token: ${{ steps.azure-login.outputs.access-token }}
          expires-on: ${{ steps.azure-login.outputs.expires-on }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
          resource-group: ${{ secrets.AZURE_RESOURCE_GROUP }}
          workspace-name: ${{ secrets.AZURE_ML_WORKSPACE_NAME }}
          filepath: ${{ matrix.asset.filepath }}
```

---

## Further Reading

| Topic | Link |
|-------|------|
| Inner-loop action reference | [inner-loop/README.md](inner-loop/README.md) |
| Usage examples (CLI and GitHub Action) | [inner-loop/EXAMPLES.md](inner-loop/EXAMPLES.md) |
| How to set up a basic workflow | [how-to-use.md](how-to-use.md) |
| Azure ML assets documentation | [Azure ML concepts: assets](https://learn.microsoft.com/en-us/azure/machine-learning/concept-assets-v2) |
| GitHub Actions documentation | [GitHub Actions quickstart](https://docs.github.com/en/actions/quickstart) |
| Azure ML YAML schemas | [CLI v2 YAML reference](https://learn.microsoft.com/en-us/azure/machine-learning/reference-yaml-overview) |

---

### Branching Strategy

To maintain a clean and organized codebase, we follow a specific branching strategy. Below are the details of our branching rules:

#### 1. Main Branch
- **Branch Name:** `main`
- **Purpose:** This is the stable branch containing the latest production-ready code. All releases are tagged from this branch.
- **Protection Rules:**
  - Pull request reviews are required before merging.
  - Status checks (e.g., CI/CD tests) must pass before merging.
  - Direct pushes to this branch are restricted to admins only.

#### 2. Development Branch
- **Branch Name:** `develop`
- **Purpose:** This branch serves as an integration branch for features. All completed features are merged here before being promoted to `main`.
- **Protection Rules:**
  - Pull request reviews are required before merging.
  - CI/CD checks must pass to ensure stability.

#### 3. Feature Branches
- **Branch Naming Convention:** `feature/<feature-name>`
- **Purpose:** Each new feature or enhancement should be developed in its own branch off of `develop`.
- **Lifecycle:**
  - Create a new feature branch from `develop`.
  - Work on the feature and commit changes.
  - Once completed, create a pull request to merge back into `develop`.

#### 4. Bugfix Branches
- **Branch Naming Convention:** `bugfix/<bug-description>`
- **Purpose:** Similar to feature branches, but specifically for bug fixes.
- **Lifecycle:**
  - Create a new bugfix branch from `develop`.
  - Work on the bug fix and commit changes.
  - Once completed, create a pull request to merge back into `develop`.

#### 5. Release Branches
- **Branch Naming Convention:** `release/<version-number>`
- **Purpose:** When preparing for a new release, create a release branch from `develop`. This branch is for finalizing the release (e.g., documentation, versioning).
- **Lifecycle:**
  - Create a new release branch from `develop`.
  - Make any final changes or fixes.
  - Merge back into `main` and `develop` after the release is complete.

#### 6. Hotfix Branches
- **Branch Naming Convention:** `hotfix/<issue-description>`
- **Purpose:** For urgent fixes that need to be applied to the production code immediately.
- **Lifecycle:**
  - Create a hotfix branch from `main`.
  - Implement the fix and commit changes.
  - Merge back into both `main` and `develop` to ensure the fix is included in future releases.

### Additional Guidelines

- **Commit Messages:** Please use meaningful commit messages that describe the changes made.
- **Pull Requests:** Always use pull requests for merges to facilitate code review and discussion.
- **Documentation:** Keep the README and other documentation updated to reflect our branching strategy and guidelines.
- **Versioning:** We follow semantic versioning (e.g., v1.0.0) for releases to help users understand the impact of changes.

## Contributing

We welcome contributions! Please read our [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on how to contribute to this repository.

Thank you for being a part of our community!
