# Share Data - Azure ML Data Asset Sharing Action

## Overview

Share Data is an action that shares an Azure ML Data asset from a workspace to a registry, making it available for reuse across different workspaces and subscriptions.

## Key Features

- **Cross-Workspace Sharing**: Share data assets from any workspace to any registry
- **Flexible Data Reference**: Supports multiple input formats (azureml refs, resource IDs, name:version)
- **Tag Management**: Apply custom tags to shared data assets in the registry
- **Consistent Outputs**: Returns resource ID, data reference, and version
- **Comprehensive Validation**: Input validation with clear error messages

## Usage

### Basic Data Asset Sharing

```yaml
- uses: equinor/ai-platform-actions/share-data@main
  with:
    tenant-id: ${{ secrets.AZURE_TENANT_ID }}
    subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
    resource-group: ${{ secrets.AZURE_RESOURCE_GROUP }}
    workspace-name: ${{ secrets.AZURE_ML_WORKSPACE_NAME }}
    client-id: ${{ secrets.AZURE_CLIENT_ID }}
    registry-name: ${{ secrets.AZURE_ML_REGISTRY_NAME }}
    data-ref: "azureml:training-data:1"
```

### Data Asset Sharing with Tags

```yaml
- uses: equinor/ai-platform-actions/share-data@main
  with:
    tenant-id: ${{ secrets.AZURE_TENANT_ID }}
    subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
    resource-group: ${{ secrets.AZURE_RESOURCE_GROUP }}
    workspace-name: ${{ secrets.AZURE_ML_WORKSPACE_NAME }}
    client-id: ${{ secrets.AZURE_CLIENT_ID }}
    registry-name: ${{ secrets.AZURE_ML_REGISTRY_NAME }}
    data-ref: "azureml:customer-data:3"
    tags: "dataset=production,quality=verified,pii=anonymized"
```

### Using with Deploy Data Output

```yaml
jobs:
  deploy-and-share:
    runs-on: ubuntu-latest
    steps:
      - name: Azure Login
        uses: azure/login@v2
        with:
          client-id: ${{ secrets.AZURE_CLIENT_ID }}
          tenant-id: ${{ secrets.AZURE_TENANT_ID }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
          enable-AzPSSession: true
          auth-type: SERVICE_PRINCIPAL

      - name: Deploy Data Asset
        uses: equinor/ai-platform-actions/deploy-data@main
        id: deploy
        with:
          tenant-id: ${{ secrets.AZURE_TENANT_ID }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
          resource-group: ${{ secrets.AZURE_RESOURCE_GROUP }}
          workspace-name: ${{ secrets.AZURE_ML_WORKSPACE_NAME }}
          client-id: ${{ secrets.AZURE_CLIENT_ID }}
          data-path: data/training/data.yaml
          type: uri_folder

      - name: Share to Registry
        uses: equinor/ai-platform-actions/share-data@main
        with:
          tenant-id: ${{ secrets.AZURE_TENANT_ID }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
          resource-group: ${{ secrets.AZURE_RESOURCE_GROUP }}
          workspace-name: ${{ secrets.AZURE_ML_WORKSPACE_NAME }}
          client-id: ${{ secrets.AZURE_CLIENT_ID }}
          registry-name: ${{ secrets.AZURE_ML_REGISTRY_NAME }}
          data-ref: ${{ steps.deploy.outputs.data-ref }}
          tags: "source=ci-cd,deployed-from=workspace,type=training"
```

## Inputs

| Input | Required | Description |
|-------|----------|-------------|
| `tenant-id` | ✅ | Azure tenant ID |
| `subscription-id` | ✅ | Azure subscription ID |
| `resource-group` | ✅ | Azure resource group name (for the source workspace) |
| `workspace-name` | ✅ | Azure ML workspace name (source workspace) |
| `client-id` | ✅ | Client ID configured with Federated Credentials |
| `registry-name` | ✅ | Azure ML registry name (target registry) |
| `data-ref` | ✅ | Data asset reference (see supported formats below) |
| `tags` | ❌ | Tags to apply to the shared data asset (format: `"key1=value1,key2=value2"`) |

## Data Reference Formats

The `data-ref` input supports multiple formats:

| Format | Example | Description |
|--------|---------|-------------|
| Azure ML Reference | `azureml:training-data:1` | Standard Azure ML data asset reference |
| Name:Version | `customer-data:3` | Data asset name and version separated by colon |
| Resource ID | `/subscriptions/.../data/mydata/versions/1` | Full Azure resource ID |

## Tags Format

Tags should be provided as a comma-separated string of key-value pairs:

```yaml
# Single tag
tags: "dataset=production"

# Multiple tags
tags: "dataset=training,quality=verified,pii=anonymized,source=external"

# Tags for data governance
tags: "classification=public,retention=7years,owner=data-team"
```

## Outputs

| Output | Description |
|--------|-------------|
| `resource-id` | Resource ID of the shared data asset in the registry |
| `data-ref` | Reference string of data asset within Azure ML registry (format: `azureml:name:version`) |
| `data-version` | The version of the data asset within the registry |

## Complete Workflow Examples

### Deploy and Share Pattern

```yaml
name: Deploy and Share Data Asset

on:
  push:
    branches: [main]
    paths: [data/**]

jobs:
  deploy-and-share:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Azure Login
        uses: azure/login@v2
        with:
          client-id: ${{ secrets.AZURE_CLIENT_ID }}
          tenant-id: ${{ secrets.AZURE_TENANT_ID }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
          enable-AzPSSession: true
          auth-type: SERVICE_PRINCIPAL

      - name: Deploy Data Asset
        uses: equinor/ai-platform-actions/deploy-data@main
        id: deploy
        with:
          tenant-id: ${{ secrets.AZURE_TENANT_ID }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
          resource-group: ${{ secrets.AZURE_RESOURCE_GROUP }}
          workspace-name: ${{ secrets.AZURE_ML_WORKSPACE_NAME }}
          client-id: ${{ secrets.AZURE_CLIENT_ID }}
          data-path: data/training/data.yaml
          type: uri_folder

      - name: Share to Registry
        uses: equinor/ai-platform-actions/share-data@main
        id: share
        with:
          tenant-id: ${{ secrets.AZURE_TENANT_ID }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
          resource-group: ${{ secrets.AZURE_RESOURCE_GROUP }}
          workspace-name: ${{ secrets.AZURE_ML_WORKSPACE_NAME }}
          client-id: ${{ secrets.AZURE_CLIENT_ID }}
          registry-name: ${{ secrets.AZURE_ML_REGISTRY_NAME }}
          data-ref: ${{ steps.deploy.outputs.data-ref }}
          tags: "source=github-actions,commit=${{ github.sha }},branch=${{ github.ref_name }}"

      - name: Output Results
        run: |
          echo "Data asset deployed to workspace: ${{ steps.deploy.outputs.data-ref }}"
          echo "Data asset shared to registry: ${{ steps.share.outputs.data-ref }}"
          echo "Registry Resource ID: ${{ steps.share.outputs.resource-id }}"
```

### Matrix Strategy for Multiple Data Assets

```yaml
name: Share Multiple Data Assets

on:
  workflow_dispatch:
    inputs:
      datasets:
        description: 'JSON array of data assets to share'
        required: true
        default: '[{"ref":"azureml:training:1","tags":"type=training,verified=true"},{"ref":"azureml:validation:2","tags":"type=validation,verified=true"}]'

jobs:
  share-datasets:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        dataset: ${{ fromJson(github.event.inputs.datasets) }}
    steps:
      - name: Azure Login
        uses: azure/login@v2
        with:
          client-id: ${{ secrets.AZURE_CLIENT_ID }}
          tenant-id: ${{ secrets.AZURE_TENANT_ID }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
          enable-AzPSSession: true
          auth-type: SERVICE_PRINCIPAL

      - name: Share Data Asset
        uses: equinor/ai-platform-actions/share-data@main
        with:
          tenant-id: ${{ secrets.AZURE_TENANT_ID }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
          resource-group: ${{ secrets.AZURE_RESOURCE_GROUP }}
          workspace-name: ${{ secrets.AZURE_ML_WORKSPACE_NAME }}
          client-id: ${{ secrets.AZURE_CLIENT_ID }}
          registry-name: ${{ secrets.AZURE_ML_REGISTRY_NAME }}
          data-ref: ${{ matrix.dataset.ref }}
          tags: ${{ matrix.dataset.tags }}
```

## How It Works

The share-data action performs the following steps:

1. **Action Summary**: Shows what data asset will be shared, from which workspace to which registry
2. **Input Validation**: Validates all required parameters and tags format
3. **Azure ML Extension**: Ensures the Azure ML CLI extension is installed
4. **Data Asset Sharing**: Executes `az ml data share` with the specified parameters and tags
5. **Reference Extraction**: Extracts data asset reference and version from the returned resource ID
6. **Results Output**: Displays the sharing results and registry information

## Error Handling

The action includes comprehensive error handling for:
- Missing required parameters
- Invalid tag formats
- Data asset sharing failures
- Resource ID parsing errors

## Prerequisites

- Azure authentication must be configured (using `azure/login@v2`)
- The source data asset must exist in the specified workspace
- The target registry must exist and be accessible
- Appropriate permissions for sharing data assets between workspace and registry
