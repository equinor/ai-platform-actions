# Inner Loop Action

A unified GitHub Action for Azure ML operations using typer for clean command routing.

## Overview

The Inner Loop action consolidates various Azure ML operations (deploy, share, waitfor) for different resource types (data, environment, component, model, job) into a single, flexible action. It uses typer to provide a clean, intuitive CLI-style interface.

## Implementation Status

**✅ FULLY IMPLEMENTED** - All deploy, share, waitfor, and delete operations are complete and ready for production use.

### Deploy Operations
- ✅ **deploy data**: Deploy data assets to Azure ML workspace
- ✅ **deploy environment**: Deploy Azure ML environments with build support
- ✅ **deploy component**: Deploy Azure ML components with automatic versioning
- ✅ **deploy model**: Register Azure ML models from YAML specifications
- ✅ **deploy job**: Submit Azure ML jobs to workspace
- ✅ **deploy online-endpoint**: Deploy managed online endpoints
- ✅ **deploy online-deployment**: Deploy managed online deployments with traffic allocation
- ✅ **deploy batch-endpoint**: Create or update an Azure ML batch endpoint
- ✅ **deploy batch-deployment**: Create or update a versioned batch deployment
- ✅ **deploy feature-set**: Register a feature set with a managed feature store (does not wait; pair with `waitfor feature-set`)
- ✅ **deploy feature-store-entity**: Register the join-key entity that feature sets reference

### Batch Release Operations
- ✅ **invoke batch-deployment**: Invoke one named deployment on a pinned data asset, datastore URI or preceding job's output
- ✅ **promote batch-deployment**: Change the endpoint default with an optional expected-current check and post-update verification
- ✅ **rollback batch-deployment**: Restore an explicitly recorded prior default deployment

Batch promotion and rollback are idempotent. A retry that already reached its target is a no-op, and the result is read back after update. `expected-current-deployment` is optional: leave it blank to replace whatever default is there (the only option for an endpoint that has no default yet), or set it to fail before mutation when the default is not what the workflow observed. The SDK does not expose an ETag precondition, so orchestrating workflows must also use a GitHub concurrency group per endpoint.

### Share Operations
- ✅ **share data**: Share data assets from workspace to registry
- ✅ **share environment**: Share environments from workspace to registry with stage promotion
- ✅ **share component**: Share components from workspace to registry with environment replacement
- ✅ **share model**: Share models from workspace to registry with stage promotion

### Waitfor Operations
- ✅ **waitfor data**: Poll workspace until a specific data asset version is registered successfully
- ✅ **waitfor environment**: Monitor environment builds (including image verification) until completion
- ✅ **waitfor component**: Track component registrations until provisioning succeeds or fails
- ✅ **waitfor model**: Ensure model registrations finish before dependent stages continue
- ✅ **waitfor job**: Observe Azure ML job lifecycle until it reaches a terminal status (Completed/Failed)
- ✅ **waitfor online-endpoint**: Wait for online endpoint provisioning to complete
- ✅ **waitfor online-deployment**: Wait for online deployment provisioning to complete
- ✅ **waitfor feature-set**: Wait for a feature set registration to finish provisioning in the feature store

### Delete Operations
- ✅ **delete online-endpoint**: Delete an online endpoint (and all its deployments)
- ✅ **delete online-deployment**: Delete an online deployment (automatically removes traffic first)

## Architecture

### Structure

The action is organized into modular Python files:

- **main.py**: Entry point that routes commands using typer
- **deploy.py**: All deploy operations with full Azure ML SDK integration
- **share.py**: All share operations with registry support and stage promotion
- **waitfor.py**: All waitfor operations for polling asset provisioning states
- **delete.py**: Delete operations for online endpoints and deployments
- **batch.py**: Shared idempotent batch default-switch operation
- **invoke.py**: Named batch deployment validation invocations
- **promote.py**: Guarded and verified batch deployment promotion
- **arm.py**: Azure Resource Manager REST access to asset containers and versions
- **getasset.py**: Helper functions for retrieving and filtering Azure ML assets
- **util.py**: Utility functions for authentication, tagging, and GitHub output
- **action.yaml**: GitHub Action composite definition

Each module uses typer's `@app.command()` decorator for clean, self-documenting CLI interfaces.

### Key Features

- **Automatic Version Management**: Components automatically increment to next integer version
- **Archived Container Recovery**: Every versioned asset is two resources in Azure, a container and its versions. An archived container hides all its versions, including active ones, and the SDK cannot reach that flag. Asset lookups read both layers over the [ARM REST API](https://learn.microsoft.com/rest/api/azureml/) instead, so deploy restores an archived workspace container automatically and reports an archived registry container without touching it.
- **Command Normalization**: Multiline component commands are automatically cleaned (backslashes and line breaks removed)
- **Tag Merging**: Tags from YAML configs and command-line inputs are intelligently merged
- **Stage Promotion**: Share operations support promoting assets to specific stages (e.g., "Production")
- **Environment Replacement**: Component sharing automatically replaces workspace environments with registry equivalents
- **Flexible Authentication**: Supports both token-based (federated credentials) and DefaultAzureCredential

## Waitfor Logic Analysis

- **AzureML provisioning states**: Every waitfor command queries AzureML via `MLClient` and interprets standard provisioning statuses (`Succeeded`, `Failed`, `Creating`, etc.) exposed on workspace assets as `provisioning_state`/`status`. This mirrors how Azure signals asynchronous registrations and image builds, so the polling logic aligns with service semantics.
- **Timeout and backoff**: Polls happen every 10 seconds with a 30-minute cutoff, which matches common AzureML build durations (environment image builds rarely exceed this) while preventing pipelines from hanging indefinitely when Azure reports no progress.
- **Deploy alignment**: Deploy commands return as soon as Azure accepts a registration request, whereas actual materialization (image build, artifact copy) may still be running. The waitfor verb bridges that gap by blocking downstream steps until the deploy-requested asset reaches `Succeeded`, reducing race conditions in chained workflows.
- **Job lifecycle integration**: AzureML jobs expose a richer status model (`Queued`, `Running`, `Completed`, `Failed`). The waitfor job subject specifically looks for terminal states, enabling automated triggering of share/promote logic once a training job finishes without having to embed custom SDK scripts.
- **Tag consistency**: Because waitfor enforces optional tag matches, it works with deploy-time tagging conventions and ensures that pipelines do not accidentally observe stale assets with the same name/version but different metadata.

### Authentication

The action supports two authentication methods:

1. **Token-based authentication** (Recommended for GitHub Actions)
   - Requires: `client-id` and `tenant-id`
   - Uses `az account get-access-token` to obtain access token
   - Works with Azure federated credentials

2. **DefaultAzureCredential** (For local development)
   - No credentials required in inputs
   - Supports: Environment variables, Managed identity, Azure CLI, VS Code, Azure PowerShell, and more
   - Perfect for local testing and development

### Storage accounts without shared key access

Deploying an asset with a local path (data, model, component code, environment build context, job code snapshot) uploads artifacts to the workspace storage account. By default the Azure ML SDK fetches an account key for that upload, so no extra token is needed.

If the storage account sets `allowSharedKeyAccess: false`, the upload authenticates with Entra ID instead and needs a storage-scoped token:

```yaml
- name: Get access tokens
  id: get-token
  shell: bash
  run: |
    TOKEN=$(az account get-access-token --query accessToken --output tsv)
    STORAGE_TOKEN=$(az account get-access-token --resource https://storage.azure.com --query accessToken --output tsv)
    EXPIRES_ON=$(az account get-access-token --query expires_on --output tsv)
    echo "::add-mask::$TOKEN"
    echo "::add-mask::$STORAGE_TOKEN"
    echo "token=$TOKEN" >> "$GITHUB_OUTPUT"
    echo "storage-token=$STORAGE_TOKEN" >> "$GITHUB_OUTPUT"
    echo "expires-on=$EXPIRES_ON" >> "$GITHUB_OUTPUT"

- uses: equinor/ai-platform-actions/inner-loop@main
  with:
    storage-token: ${{ steps.get-token.outputs.storage-token }}
    # ... remaining inputs
```

The workflow identity also needs the **Storage Blob Data Contributor** role on the workspace storage account. When the action detects a denied blob request it prints this guidance before failing.

## Usage

### Deploy Data Asset

```yaml
- uses: ./inner-loop
  with:
    verb: deploy
    subject: data
    token: ${{ steps.azure-login.outputs.access-token }}
    expires-on: ${{ steps.azure-login.outputs.expires-on }}
    subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
    resource-group: my-resource-group
    workspace-name: my-workspace
    filepath: ./data/my-data.yaml
    tags: "env=prod,team=ml"
```

### Deploy Environment

```yaml
- uses: ./inner-loop
  with:
    verb: deploy
    subject: environment
    token: ${{ steps.azure-login.outputs.access-token }}
    expires-on: ${{ steps.azure-login.outputs.expires-on }}
    subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
    resource-group: my-resource-group
    workspace-name: my-workspace
    filepath: ./environments/my-env.yaml
    tags: "version=1.0"
```

### Deploy Component

```yaml
- uses: ./inner-loop
  with:
    verb: deploy
    subject: component
    token: ${{ steps.azure-login.outputs.access-token }}
    expires-on: ${{ steps.azure-login.outputs.expires-on }}
    subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
    resource-group: my-resource-group
    workspace-name: my-workspace
    filepath: ./components/my-component.yaml
    tags: "type=training,framework=pytorch"
```

**Component Features:**
- Automatically finds and increments to next integer version, counting archived versions so an existing version is never overwritten
- Restores the component container if it has been archived, which would otherwise hide every version
- Cleans multiline commands (removes `\` and line breaks)
- Merges tags from YAML and command line

### Deploy Model

```yaml
- uses: ./inner-loop
  with:
    verb: deploy
    subject: model
    token: ${{ steps.azure-login.outputs.access-token }}
    expires-on: ${{ steps.azure-login.outputs.expires-on }}
    subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
    resource-group: my-resource-group
    workspace-name: my-workspace
    filepath: ./models/my-model.yaml
    tags: "owner=mlops,stage=staging"
```

### Deploy Job

```yaml
- uses: ./inner-loop
  with:
    verb: deploy
    subject: job
    token: ${{ steps.azure-login.outputs.access-token }}
    expires-on: ${{ steps.azure-login.outputs.expires-on }}
    aml-token: ${{ steps.azure-login.outputs.aml-token }}
    subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
    resource-group: my-resource-group
    workspace-name: my-workspace
    filepath: ./jobs/my-job.yaml
```

**Note:** When token-based authentication is used, `deploy job`, `deploy sweep-job`, and `waitfor job` accept an `aml-token` with the `https://ml.azure.com/.default` scope. It is optional when `DefaultAzureCredential` is available locally.

**Note:** Every `deploy` command also accepts an optional `storage-token` with the `https://storage.azure.com/.default` scope. It is only needed when the workspace storage account has shared key access disabled (`allowSharedKeyAccess: false`), because artifact upload then authenticates with Entra ID instead of an account key. See [Storage accounts without shared key access](#storage-accounts-without-shared-key-access).

### Deploy Online Endpoint

```yaml
- uses: ./inner-loop
  with:
    verb: deploy
    subject: online-endpoint
    token: ${{ steps.azure-login.outputs.access-token }}
    expires-on: ${{ steps.azure-login.outputs.expires-on }}
    subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
    resource-group: my-resource-group
    workspace-name: my-workspace
    filepath: ./endpoints/my-endpoint.yaml
```

**Endpoint YAML example** (`my-endpoint.yaml`):
```yaml
$schema: https://azuremlschemas.azureedge.net/latest/managedOnlineEndpoint.schema.json
name: my-inference-endpoint
auth_mode: key
```

### Deploy Online Deployment with Traffic

```yaml
- name: Deploy Online Deployment
  id: deploy-deployment
  uses: ./inner-loop
  with:
    verb: deploy
    subject: online-deployment
    token: ${{ steps.azure-login.outputs.access-token }}
    expires-on: ${{ steps.azure-login.outputs.expires-on }}
    subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
    resource-group: my-resource-group
    workspace-name: my-workspace
    filepath: ./deployments/blue-deployment.yaml
    traffic-allocation: 100
```

**Deployment YAML example** (`blue-deployment.yaml`):
```yaml
$schema: https://azuremlschemas.azureedge.net/latest/managedOnlineDeployment.schema.json
name: blue
endpoint_name: my-inference-endpoint
model: azureml:my-model:1
instance_type: Standard_DS3_v2
instance_count: 1
```

### Wait for Online Deployment

```yaml
- name: Wait for Deployment
  uses: ./inner-loop
  with:
    verb: waitfor
    subject: online-deployment
    token: ${{ steps.azure-login.outputs.access-token }}
    expires-on: ${{ steps.azure-login.outputs.expires-on }}
    subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
    resource-group: my-resource-group
    workspace-name: my-workspace
    deployment-resource: ${{ steps.deploy-deployment.outputs.resource-id }}
```

### Delete Online Deployment

```yaml
- name: Delete Old Deployment
  uses: ./inner-loop
  with:
    verb: delete
    subject: online-deployment
    token: ${{ steps.azure-login.outputs.access-token }}
    expires-on: ${{ steps.azure-login.outputs.expires-on }}
    subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
    resource-group: my-resource-group
    workspace-name: my-workspace
    deployment-resource: /subscriptions/.../onlineEndpoints/my-endpoint/deployments/green
```

### Wait for Environment Readiness

```yaml
- uses: ./inner-loop
  with:
    verb: waitfor
    subject: environment
    token: ${{ steps.azure-login.outputs.access-token }}
    expires-on: ${{ steps.azure-login.outputs.expires-on }}
    subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
    resource-group: my-resource-group
    workspace-name: my-workspace
    env-ref: my-env:5
    tags: "stage=build"
```

### Wait for Job Completion

```yaml
- uses: ./inner-loop
  with:
    verb: waitfor
    subject: job
    token: ${{ steps.azure-login.outputs.access-token }}
    expires-on: ${{ steps.azure-login.outputs.expires-on }}
    aml-token: ${{ steps.azure-login.outputs.aml-token }}
    subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
    resource-group: my-resource-group
    workspace-name: my-workspace
    job-name: my-training-job
```

The waitfor verb polls Azure ML every 10 seconds (up to 30 minutes) until the specified asset exists and reports a success status. If the asset reports a failure state or the timeout expires, the action stops with a failure, allowing pipelines to halt early when provisioned artifacts break.

### Invoke a Batch Deployment

```yaml
- uses: ./inner-loop
  with:
    verb: invoke
    subject: batch-deployment
    token: ${{ steps.azure-login.outputs.access-token }}
    expires-on: ${{ steps.azure-login.outputs.expires-on }}
    aml-token: ${{ steps.azure-login.outputs.aml-token }}
    subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
    resource-group: my-resource-group
    workspace-name: my-workspace
    endpoint-name: forecast-batch
    deployment-name: candidate-17
    input-path: azureml://jobs/${{ steps.generate-inference-data.outputs.version }}/outputs/scored
    input-type: uri_folder
```

The invocation targets one named deployment directly, so it validates a candidate without touching endpoint traffic or the endpoint default. Use `promote batch-deployment` once the invocation result is accepted.

**Accepted `input-path` forms:**

| Form | Example |
|------|---------|
| Job output reference | `azureml://jobs/<job-name>/outputs/<output-name>` |
| Job output subpath | `azureml://jobs/<job-name>/outputs/<output-name>/paths/<file>` |
| Short datastore URI | `azureml://datastores/<datastore>/paths/<path>` |
| Long datastore URI | `azureml://subscriptions/<sub>/resourcegroups/<rg>/workspaces/<ws>/datastores/<datastore>/paths/<path>` |
| Registered data asset | `azureml:<name>:<version>` or `azureml:<name>@latest` |
| Public URI | `https://<host>/<path>` |
| Local path | `./data/validation` (uploaded to the workspace datastore) |

Azure ML batch endpoints only consume datastore URIs, registered data assets, public URIs and local paths. Job output references are the natural handoff from a preceding `deploy job` step, so the action resolves them to the underlying datastore URI before invoking, and appends the trailing `/` that `uri_folder` inputs require. Any other `azureml://` URI is rejected up front with the list of accepted forms instead of the SDK's generic validation error.

`invocation-job-name` pins the name of the created Azure ML job, which makes a retried workflow run observable under a known name. Leave it blank to let Azure ML generate one; a rerun with an already-used name fails. `experiment-name` groups the invocation job in the Azure ML studio experiment view.

Outputs: `invocation-job-name` and `version` carry the submitted job name, `status` its initial status, and `resource-id` its resource ID. Chain `waitfor job` on `invocation-job-name` to block until the batch job reaches a terminal state.

### Share to Registry with Stage Promotion

```yaml
- name: Deploy Component to Workspace
  id: deploy
  uses: ./inner-loop
  with:
    verb: deploy
    subject: component
    token: ${{ steps.azure-login.outputs.access-token }}
    expires-on: ${{ steps.azure-login.outputs.expires-on }}
    subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
    resource-group: my-resource-group
    workspace-name: my-workspace
    filepath: ./components/my-component.yaml

- name: Share Component to Registry
  uses: ./inner-loop
  with:
    verb: share
    subject: component
    token: ${{ steps.azure-login.outputs.access-token }}
    expires-on: ${{ steps.azure-login.outputs.expires-on }}
    subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
    resource-group: my-resource-group
    workspace-name: my-workspace
    registry-name: my-registry
    component-ref: my-component
    promote-stage: "Production"
    tags: "env=prod"
```

**Share Features:**
- Automatically increments version in registry
- Replaces workspace environment references with registry equivalents (for components)
- Supports stage promotion via tags
- Works for data, environment, component, and model assets

### Deploy to a Managed Feature Store

The feature store commands target an Azure ML [managed feature store](https://learn.microsoft.com/en-us/azure/machine-learning/concept-what-is-managed-feature-store?view=azureml-api-2), which is a workspace of kind `FeatureStore`. They take `feature-store-name` instead of `workspace-name`, and passing `workspace-name` to them fails input validation so a feature set cannot be sent to a regular workspace by mistake. The feature store itself must already exist.

Register the entity first, because the feature set YAML references it as `azureml:<entity>:<version>`. Entity versions are taken from the YAML exactly as written so those references stay stable; feature set versions are auto-incremented from the feature store like `deploy data` and `deploy component`.

```yaml
- name: Deploy Feature Store Entity
  uses: ./inner-loop
  with:
    verb: deploy
    subject: feature-store-entity
    token: ${{ steps.azure-login.outputs.access-token }}
    expires-on: ${{ steps.azure-login.outputs.expires-on }}
    subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
    resource-group: my-resource-group
    feature-store-name: my-feature-store
    filepath: ./featurestore/entities/account.yaml

- name: Deploy Feature Set
  id: feature-set
  uses: ./inner-loop
  with:
    verb: deploy
    subject: feature-set
    token: ${{ steps.azure-login.outputs.access-token }}
    expires-on: ${{ steps.azure-login.outputs.expires-on }}
    subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
    resource-group: my-resource-group
    feature-store-name: my-feature-store
    filepath: ./featurestore/featuresets/transactions/featureset_asset.yaml
    tags: "data_type=nonPII"

- name: Wait for Feature Set
  uses: ./inner-loop
  with:
    verb: waitfor
    subject: feature-set
    token: ${{ steps.azure-login.outputs.access-token }}
    expires-on: ${{ steps.azure-login.outputs.expires-on }}
    subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
    resource-group: my-resource-group
    feature-store-name: my-feature-store
    feature-set-ref: ${{ steps.feature-set.outputs.reference }}
```

`deploy feature-set` uploads the spec folder, starts provisioning and returns immediately with a reference, so chain `waitfor feature-set` whenever a later step consumes the feature set. See [Deploy Feature Set](EXAMPLES.md#deploy-feature-set) for the required spec folder layout and the `.amlignore` caveat.

The identity needs **AzureML Data Scientist** on the feature store, plus **Storage Blob Data Contributor** on its storage account for the spec folder upload.

## Inputs

| Input | Required | Description |
|-------|----------|-------------|
| `verb` | Yes | Action verb: `deploy`, `share`, `waitfor`, `delete`, `invoke`, `promote`, or `rollback` |
| `subject` | Yes | Target subject: `data`, `environment`, `component`, `model`, `job`, `feature-set`, `feature-store-entity`, `online-endpoint`, `online-deployment`, `batch-endpoint`, or `batch-deployment` |
| `token` | No* | Access token from Azure login action (*required for GitHub Actions) |
| `expires-on` | No* | Token expiration timestamp from Azure login action (*required for GitHub Actions) |
| `aml-token` | No | Access token with Azure ML scope for `deploy job`, `deploy sweep-job`, and `waitfor job`; optional when `DefaultAzureCredential` is available locally |
| `storage-token` | No | Access token with Azure Storage scope (`https://storage.azure.com/.default`) for `deploy` commands; only needed when the workspace storage account has shared key access disabled |
| `tenant-id` | No | Azure tenant ID (required for token-based auth) |
| `subscription-id` | Yes | Azure subscription ID |
| `resource-group` | Yes | Azure resource group name |
| `workspace-name` | No* | Azure ML workspace name (*required for every command except the feature store commands, which must omit it) |
| `feature-store-name` | No* | Managed feature store name (*required for `deploy feature-set`, `deploy feature-store-entity` and `waitfor feature-set`) |
| `registry-name` | No* | Azure ML registry name (*required for share operations) |
| `client-id` | No | Client ID for federated credentials (required for token-based auth) |
| `filepath` | No* | Path to configuration YAML file (*required for deploy operations) |
| `component-ref` | No* | Component name (*for share component) |
| `data-ref` | No* | Data asset name (*for share data) |
| `env-ref` | No* | Environment name (*for share environment) |
| `model-ref` | No* | Model name (*for share model) |
| `feature-set-ref` | No* | Feature set reference with an explicit version (*for waitfor feature-set) |
| `job-name` | No* | Job name (*for waitfor job) |
| `endpoint-name` | No* | Endpoint name (*for waitfor/delete online-endpoint and for invoke/promote/rollback batch-deployment) |
| `deployment-name` | No* | Deployment name (*required for invoke/promote/rollback batch-deployment) |
| `deployment-resource` | No* | Online deployment resource ID (*for waitfor/delete online-deployment) |
| `input-path` | No* | Pinned data asset or URI used to invoke a batch deployment (*required for invoke batch-deployment) |
| `input-type` | No | Batch invocation input type: `uri_folder` (default) or `uri_file` |
| `invocation-job-name` | No | Deterministic name for the created batch invocation job |
| `experiment-name` | No | Azure ML experiment name (for `deploy job`, `deploy sweep-job`, `invoke batch-deployment`) |
| `expected-current-deployment` | No | Expected batch endpoint default; promotion or rollback fails when the actual default differs |
| `traffic-allocation` | No | Traffic percentage (0-100) to allocate to deployment |
| `tags` | No | Tags in format: `key1=value1,key2=value2` |
| `promote-stage` | No | Stage to promote asset to (e.g., "Production") |
| `image-build-compute` | No | Compute cluster name for environment builds (instead of serverless) |

## Outputs

| Output | Description |
|--------|-------------|
| `resource-id` | Full Azure resource ID of the created/shared resource |
| `reference` | Azure ML reference string (e.g., `azureml:name:version`) |
| `version` | Version number of the resource (or job name for jobs) |
| `lineage-metadata` | JSON-encoded lineage metadata for a submitted job (git SHA, branch, workflow run ID) |
| `best-trial-run-id` | Run ID of the best trial in a completed sweep job |
| `invocation-job-name` | Azure ML job created by `invoke batch-deployment` |
| `status` | Status of the submitted batch invocation job |
| `previous-deployment-name` | Batch endpoint default before promotion |
| `replaced-deployment-name` | Batch endpoint default replaced during rollback |
| `default-deployment-name` | Batch endpoint default after promotion or rollback |
| `changed` | Whether promotion or rollback changed the endpoint |

## Complete Example Pipeline

```yaml
name: Deploy and Share Azure ML Assets

on:
  push:
    branches: [main]

jobs:
  deploy-and-share:
    runs-on: ubuntu-latest
    permissions:
      id-token: write
      contents: read
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Azure Login
        id: azure-login
        uses: azure/login@v1
        with:
          client-id: ${{ secrets.AZURE_CLIENT_ID }}
          tenant-id: ${{ secrets.AZURE_TENANT_ID }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
      
      - name: Deploy Environment
        id: deploy-env
        uses: ./inner-loop
        with:
          verb: deploy
          subject: environment
          token: ${{ steps.azure-login.outputs.access-token }}
          expires-on: ${{ steps.azure-login.outputs.expires-on }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
          resource-group: my-resource-group
          workspace-name: my-workspace
          filepath: ./environments/training-env.yaml
          tags: "version=1.0,env=prod"
      
      - name: Deploy Component
        id: deploy-comp
        uses: ./inner-loop
        with:
          verb: deploy
          subject: component
          token: ${{ steps.azure-login.outputs.access-token }}
          expires-on: ${{ steps.azure-login.outputs.expires-on }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
          resource-group: my-resource-group
          workspace-name: my-workspace
          filepath: ./components/training-component.yaml
          tags: "type=training"
      
      - name: Wait for Environment
        uses: ./inner-loop
        with:
          verb: waitfor
          subject: environment
          token: ${{ steps.azure-login.outputs.access-token }}
          expires-on: ${{ steps.azure-login.outputs.expires-on }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
          resource-group: my-resource-group
          workspace-name: my-workspace
          env-ref: training-env:${{ steps.deploy-env.outputs.version }}

      - name: Share Environment to Registry
        uses: ./inner-loop
        with:
          verb: share
          subject: environment
          token: ${{ steps.azure-login.outputs.access-token }}
          expires-on: ${{ steps.azure-login.outputs.expires-on }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
          resource-group: my-resource-group
          workspace-name: my-workspace
          registry-name: my-registry
          env-ref: training-env
          promote-stage: "Production"
      
      - name: Share Component to Registry
        uses: ./inner-loop
        with:
          verb: share
          subject: component
          token: ${{ steps.azure-login.outputs.access-token }}
          expires-on: ${{ steps.azure-login.outputs.expires-on }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
          resource-group: my-resource-group
          workspace-name: my-workspace
          registry-name: my-registry
          component-ref: training-component
          promote-stage: "Production"
      
      - name: Deploy Job
        uses: ./inner-loop
        with:
          verb: deploy
          subject: job
          token: ${{ steps.azure-login.outputs.access-token }}
          expires-on: ${{ steps.azure-login.outputs.expires-on }}
          aml-token: ${{ steps.azure-login.outputs.aml-token }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
          resource-group: my-resource-group
          workspace-name: my-workspace
          filepath: ./jobs/training-job.yaml
```

## Local Development

### Building the Docker Image

```bash
cd inner-loop
docker build -t inner-loop:latest .
```

### Local Testing with Azure CLI

```bash
# Authenticate with Azure CLI
az login

# Run deploy command
python main.py deploy component \
  --subscription "$SUBSCRIPTION_ID" \
  --resource-group "$RESOURCE_GROUP" \
  --workspace-name "$WORKSPACE_NAME" \
  --filepath "./components/my-component.yaml" \
  --tags "env=dev"

# Run share command
python main.py share component \
  --subscription "$SUBSCRIPTION_ID" \
  --resource-group "$RESOURCE_GROUP" \
  --workspace-name "$WORKSPACE_NAME" \
  --registry-name "$REGISTRY_NAME" \
  "my-component" \
  --promote-stage "Development"
```

## Extending the Action

### Adding a New Deploy Operation

Add a new command function in `deploy.py`:

```python
@app.command()
def my_new_asset(
    subscription_id: Annotated[str, typer.Option("--subscription","-s")],
    resource_group: Annotated[str, typer.Option("--resource-group","-g")],
    workspace_name: Annotated[str, typer.Option("--workspace-name","-w")],
    filepath: str,
    token: Optional[str] = None,
    expires_on: Optional[int] = None,
    tags: Annotated[Optional[str], typer.Option(callback=load_safe_tags)]=None
):
    """Deploy my new asset to Azure ML workspace"""
    print(f"[deploy my_new_asset] Deploying asset")
    
    client = get_workspace_client(
        subscription_id, resource_group, workspace_name, token, expires_on
    )
    
    # Load and deploy your asset
    asset = load_my_asset(source=filepath)
    result = client.my_assets.create_or_update(asset)
    
    print(f"[deploy my_new_asset] ✅ Asset deployed successfully")
    print(f"  Name: {result.name}")
    print(f"  Version: {result.version}")
    
    github_output({
        "reference": f"azureml:{result.name}:{result.version}",
        "version": result.version,
        "resource-id": result.id
    })
```

### Adding a New Share Operation

Add a new command function in `share.py` following the same pattern as existing share operations.

## Design Benefits

- ✅ **Simplicity**: Clean CLI routing with typer
- ✅ **Modularity**: Each operation is isolated and testable
- ✅ **Maintainability**: Easy to read, understand, and extend
- ✅ **Consistency**: All operations follow the same pattern
- ✅ **Robustness**: Proper error handling and version management
- ✅ **Flexibility**: Works with both CI/CD and local development
- ✅ **Compliance**: Follows AI-CONTRACT.md guidelines

## Dependencies

- Python 3.12+
- azure-ai-ml >= 1.28.1
- azure-core >= 1.35.0
- azure-identity >= 1.23.1
- typer >= 0.16.0

See [pyproject.toml](./pyproject.toml) for complete dependency list.

## Documentation

- [EXAMPLES.md](./EXAMPLES.md) - Detailed usage examples and patterns
- [AI-CONTRACT.md](../AI-CONTRACT.md) - Development principles and guidelines

## License

See the [LICENSE](../LICENSE) file in the repository root.
