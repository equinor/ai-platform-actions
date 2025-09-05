# Deploy X - Universal Azure ML Deployment Action

## Overview

Deploy X is a universal deployment action that can deploy any Azure ML asset (environments, components, data, or jobs) by dispatching to the appropriate specialized deployment action. This action is designed to work seamlessly with matrix strategies for parallel deployment of multiple assets.

## Key Features

- **Universal Dispatcher**: Works with all Azure ML asset types (environments, components, data, jobs)
- **Matrix Strategy Compatible**: Designed for parallel deployment using GitHub Actions matrix strategies
- **Simple Input Model**: All Azure parameters are required - no fallback complexity
- **Pre-deployment Summary**: Shows what will be deployed before starting
- **Unified Outputs**: Consistent output format regardless of asset type

## Usage

### Single Asset Deployment

```yaml
- uses: equinor/ai-platform-actions/deploy-x@main
  with:
    tenant-id: ${{ secrets.AZURE_TENANT_ID }}
    subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
    resource-group: ${{ secrets.AZURE_RESOURCE_GROUP }}
    workspace-name: ${{ secrets.AZURE_ML_WORKSPACE_NAME }}
    client-id: ${{ secrets.AZURE_CLIENT_ID }}
    asset-type: environment
    asset-path: environments/training/environment.yaml
```

### Matrix Strategy with changed-files (Recommended)

The most common pattern is to use with the `changed-files` action:

```yaml
jobs:
  detect-changes:
    runs-on: ubuntu-latest
    outputs:
      changed-files: ${{ steps.changed-files.outputs.changed-files-json }}
      has-changes: ${{ steps.changed-files.outputs.has-changes }}
    steps:
      - uses: equinor/ai-platform-actions/changed-files@main
        id: changed-files

  deploy-assets:
    if: ${{ needs.detect-changes.outputs.has-changes == 'true' }}
    needs: detect-changes
    runs-on: ubuntu-latest
    strategy:
      matrix:
        asset: ${{ fromJson(needs.detect-changes.outputs.changed-files) }}
    steps:
      - name: Azure Login
        uses: azure/login@v2
        with:
          client-id: ${{ secrets.AZURE_CLIENT_ID }}
          tenant-id: ${{ secrets.AZURE_TENANT_ID }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
          enable-AzPSSession: true
          auth-type: SERVICE_PRINCIPAL

      - uses: equinor/ai-platform-actions/deploy-x@main
        with:
          tenant-id: ${{ secrets.AZURE_TENANT_ID }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
          resource-group: ${{ secrets.AZURE_RESOURCE_GROUP }}
          workspace-name: ${{ secrets.AZURE_ML_WORKSPACE_NAME }}
          client-id: ${{ secrets.AZURE_CLIENT_ID }}
          asset-type: ${{ matrix.asset.asset-type }}
          asset-path: ${{ matrix.asset.asset-path }}
```

## Inputs

| Input | Required | Description |
|-------|----------|-------------|
| `tenant-id` | ✅ | Azure tenant ID |
| `subscription-id` | ✅ | Azure subscription ID |
| `resource-group` | ✅ | Azure resource group name |
| `workspace-name` | ✅ | Azure ML workspace name |
| `client-id` | ✅ | Client ID configured with Federated Credentials |
| `asset-type` | ✅ | Type of Azure ML asset (`environment`, `component`, `data`, `job`) |
| `asset-path` | ✅ | Path to the asset definition YAML file |
| `type` | ❌ | Type parameter for data assets |
| `compute` | ❌ | Compute parameter for job assets (defaults to `serverless`) |

## Outputs

| Output | Description |
|--------|-------------|
| `resource-id` | Resource ID of the deployed asset |
| `asset-ref` | Reference string of asset within AzureML workspace |
| `asset-version` | The registered version/name of the asset within the workspace |

## Supported Asset Types

| Asset Type | Description | Optional Parameters |
|------------|-------------|-------------------|
| `environment` | Azure ML environments | - |
| `component` | Azure ML components | - |
| `data` | Azure ML data assets | `type` |
| `job` | Azure ML jobs | `compute` |

## Examples

### Deploy Specific Asset Types

```yaml
# Deploy environment
- uses: equinor/ai-platform-actions/deploy-x@main
  with:
    tenant-id: ${{ secrets.AZURE_TENANT_ID }}
    subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
    resource-group: ${{ secrets.AZURE_RESOURCE_GROUP }}
    workspace-name: ${{ secrets.AZURE_ML_WORKSPACE_NAME }}
    client-id: ${{ secrets.AZURE_CLIENT_ID }}
    asset-type: environment
    asset-path: environments/training/environment.yaml

# Deploy data asset with type
- uses: equinor/ai-platform-actions/deploy-x@main
  with:
    tenant-id: ${{ secrets.AZURE_TENANT_ID }}
    subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
    resource-group: ${{ secrets.AZURE_RESOURCE_GROUP }}
    workspace-name: ${{ secrets.AZURE_ML_WORKSPACE_NAME }}
    client-id: ${{ secrets.AZURE_CLIENT_ID }}
    asset-type: data
    asset-path: data/training-data.yaml
    type: uri_folder

# Deploy job with custom compute
- uses: equinor/ai-platform-actions/deploy-x@main
  with:
    tenant-id: ${{ secrets.AZURE_TENANT_ID }}
    subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
    resource-group: ${{ secrets.AZURE_RESOURCE_GROUP }}
    workspace-name: ${{ secrets.AZURE_ML_WORKSPACE_NAME }}
    client-id: ${{ secrets.AZURE_CLIENT_ID }}
    asset-type: job
    asset-path: jobs/training-job.yaml
    compute: gpu-cluster
```

### Complete Workflow Example

```yaml
name: Deploy Changed Azure ML Assets

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  detect-changes:
    runs-on: ubuntu-latest
    outputs:
      changed-files: ${{ steps.changed-files.outputs.changed-files-json }}
      has-changes: ${{ steps.changed-files.outputs.has-changes }}
    steps:
      - uses: equinor/ai-platform-actions/changed-files@main
        id: changed-files
        with:
          filter-pattern: "assets/**/*.yaml"
          ignore-pattern: "test/**"

  deploy-assets:
    if: ${{ needs.detect-changes.outputs.has-changes == 'true' }}
    needs: detect-changes
    runs-on: ubuntu-latest
    strategy:
      matrix:
        asset: ${{ fromJson(needs.detect-changes.outputs.changed-files) }}
      max-parallel: 3
      fail-fast: false
    steps:
      - name: Azure Login
        uses: azure/login@v2
        with:
          client-id: ${{ secrets.AZURE_CLIENT_ID }}
          tenant-id: ${{ secrets.AZURE_TENANT_ID }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
          enable-AzPSSession: true
          auth-type: SERVICE_PRINCIPAL

      - uses: equinor/ai-platform-actions/deploy-x@main
        id: deploy
        with:
          tenant-id: ${{ secrets.AZURE_TENANT_ID }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
          resource-group: ${{ secrets.AZURE_RESOURCE_GROUP }}
          workspace-name: ${{ secrets.AZURE_ML_WORKSPACE_NAME }}
          client-id: ${{ secrets.AZURE_CLIENT_ID }}
          asset-type: ${{ matrix.asset.asset-type }}
          asset-path: ${{ matrix.asset.asset-path }}

      - name: Output deployment results
        run: |
          echo "Deployed: ${{ matrix.asset.asset-type }} at ${{ matrix.asset.asset-path }}"
          echo "Resource ID: ${{ steps.deploy.outputs.resource-id }}"
          echo "Asset Reference: ${{ steps.deploy.outputs.asset-ref }}"
```

## How It Works

The deploy-x action acts as a smart dispatcher with a simple, explicit input model:

1. **Pre-deployment Summary**: Shows what will be deployed (asset type, path, target workspace)
2. **Input Validation**: Validates asset type and checks that asset files exist
3. **Asset Dispatch**: Routes to the appropriate deployment action based on `asset-type`:
   - `environment` → `deploy-environment`
   - `component` → `deploy-component`
   - `data` → `deploy-data`
   - `job` → `deploy-job`
4. **Unified Output**: Returns consistent outputs regardless of the underlying deployment action

This design enables:
- **Explicit Configuration**: All required parameters must be provided - no hidden fallbacks
- **Clear Visibility**: Summary shows exactly what will be deployed before starting
- **Parallel Deployment**: Perfect for matrix strategies with multiple assets
- **Consistent Experience**: Same inputs/outputs across all asset types
- **Specialized Logic**: Leverages the specific deployment actions for each asset type
