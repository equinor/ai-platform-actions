# Share Environment - Azure ML Environment Sharing Action

## Overview

Share Environment is an action that shares an Azure ML Environment from a workspace to a registry, making it available for reuse across different workspaces and subscriptions.

## Key Features

- **Cross-Workspace Sharing**: Share environments from any workspace to any registry
- **Flexible Environment Reference**: Supports multiple input formats (azureml refs, resource IDs, name:version)
- **Tag Management**: Apply custom tags to shared environments in the registry
- **Consistent Outputs**: Returns resource ID, environment reference, and version
- **Comprehensive Validation**: Input validation with clear error messages

## Usage

### Basic Environment Sharing

```yaml
- uses: equinor/ai-platform-actions/share-environment@main
  with:
    tenant-id: ${{ secrets.AZURE_TENANT_ID }}
    subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
    resource-group: ${{ secrets.AZURE_RESOURCE_GROUP }}
    workspace-name: ${{ secrets.AZURE_ML_WORKSPACE_NAME }}
    client-id: ${{ secrets.AZURE_CLIENT_ID }}
    registry-name: ${{ secrets.AZURE_ML_REGISTRY_NAME }}
    environment-ref: "azureml:myenv:1"
```

### Environment Sharing with Tags

```yaml
- uses: equinor/ai-platform-actions/share-environment@main
  with:
    tenant-id: ${{ secrets.AZURE_TENANT_ID }}
    subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
    resource-group: ${{ secrets.AZURE_RESOURCE_GROUP }}
    workspace-name: ${{ secrets.AZURE_ML_WORKSPACE_NAME }}
    client-id: ${{ secrets.AZURE_CLIENT_ID }}
    registry-name: ${{ secrets.AZURE_ML_REGISTRY_NAME }}
    environment-ref: "azureml:training-env:2"
    tags: "team=ml-ops,environment=production,verified=true"
```

### Using with Deploy Environment Output

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

      - name: Deploy Environment
        uses: equinor/ai-platform-actions/deploy-environment@main
        id: deploy
        with:
          tenant-id: ${{ secrets.AZURE_TENANT_ID }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
          resource-group: ${{ secrets.AZURE_RESOURCE_GROUP }}
          workspace-name: ${{ secrets.AZURE_ML_WORKSPACE_NAME }}
          client-id: ${{ secrets.AZURE_CLIENT_ID }}
          environment-path: environments/training/environment.yaml

      - name: Share to Registry
        uses: equinor/ai-platform-actions/share-environment@main
        with:
          tenant-id: ${{ secrets.AZURE_TENANT_ID }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
          resource-group: ${{ secrets.AZURE_RESOURCE_GROUP }}
          workspace-name: ${{ secrets.AZURE_ML_WORKSPACE_NAME }}
          client-id: ${{ secrets.AZURE_CLIENT_ID }}
          registry-name: ${{ secrets.AZURE_ML_REGISTRY_NAME }}
          environment-ref: ${{ steps.deploy.outputs.environment-ref }}
          tags: "source=ci-cd,deployed-from=workspace"
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
| `environment-ref` | ✅ | Environment reference (see supported formats below) |
| `tags` | ❌ | Tags to apply to the shared environment (format: `"key1=value1,key2=value2"`) |

## Environment Reference Formats

The `environment-ref` input supports multiple formats:

| Format | Example | Description |
|--------|---------|-------------|
| Azure ML Reference | `azureml:myenv:1` | Standard Azure ML environment reference |
| Name:Version | `training-env:2` | Environment name and version separated by colon |
| Resource ID | `/subscriptions/.../environments/myenv/versions/1` | Full Azure resource ID |

## Tags Format

Tags should be provided as a comma-separated string of key-value pairs:

```yaml
# Single tag
tags: "environment=production"

# Multiple tags
tags: "team=ml-ops,environment=production,verified=true,cost-center=ml"

# Tags with special characters (avoid spaces and special chars in keys)
tags: "build-number=123,commit-sha=abc123,release-date=2024-01-15"
```

## Outputs

| Output | Description |
|--------|-------------|
| `resource-id` | Resource ID of the shared environment in the registry |
| `environment-ref` | Reference string of environment within Azure ML registry (format: `azureml:name:version`) |
| `environment-version` | The version of the environment within the registry |

## Complete Workflow Examples

### Deploy and Share Pattern

```yaml
name: Deploy and Share Environment

on:
  push:
    branches: [main]
    paths: [environments/**]

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

      - name: Deploy Environment
        uses: equinor/ai-platform-actions/deploy-environment@main
        id: deploy
        with:
          tenant-id: ${{ secrets.AZURE_TENANT_ID }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
          resource-group: ${{ secrets.AZURE_RESOURCE_GROUP }}
          workspace-name: ${{ secrets.AZURE_ML_WORKSPACE_NAME }}
          client-id: ${{ secrets.AZURE_CLIENT_ID }}
          environment-path: environments/training/environment.yaml

      - name: Share to Registry
        uses: equinor/ai-platform-actions/share-environment@main
        id: share
        with:
          tenant-id: ${{ secrets.AZURE_TENANT_ID }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
          resource-group: ${{ secrets.AZURE_RESOURCE_GROUP }}
          workspace-name: ${{ secrets.AZURE_ML_WORKSPACE_NAME }}
          client-id: ${{ secrets.AZURE_CLIENT_ID }}
          registry-name: ${{ secrets.AZURE_ML_REGISTRY_NAME }}
          environment-ref: ${{ steps.deploy.outputs.environment-ref }}
          tags: "source=github-actions,commit=${{ github.sha }},branch=${{ github.ref_name }}"

      - name: Output Results
        run: |
          echo "Environment deployed to workspace: ${{ steps.deploy.outputs.environment-ref }}"
          echo "Environment shared to registry: ${{ steps.share.outputs.environment-ref }}"
          echo "Registry Resource ID: ${{ steps.share.outputs.resource-id }}"
```

### Matrix Strategy for Multiple Environments

```yaml
name: Share Multiple Environments

on:
  workflow_dispatch:
    inputs:
      environments:
        description: 'JSON array of environments to share'
        required: true
        default: '[{"ref":"azureml:training:1","tags":"env=prod"},{"ref":"azureml:inference:2","tags":"env=prod,verified=true"}]'

jobs:
  share-environments:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        environment: ${{ fromJson(github.event.inputs.environments) }}
    steps:
      - name: Azure Login
        uses: azure/login@v2
        with:
          client-id: ${{ secrets.AZURE_CLIENT_ID }}
          tenant-id: ${{ secrets.AZURE_TENANT_ID }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
          enable-AzPSSession: true
          auth-type: SERVICE_PRINCIPAL

      - name: Share Environment
        uses: equinor/ai-platform-actions/share-environment@main
        with:
          tenant-id: ${{ secrets.AZURE_TENANT_ID }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
          resource-group: ${{ secrets.AZURE_RESOURCE_GROUP }}
          workspace-name: ${{ secrets.AZURE_ML_WORKSPACE_NAME }}
          client-id: ${{ secrets.AZURE_CLIENT_ID }}
          registry-name: ${{ secrets.AZURE_ML_REGISTRY_NAME }}
          environment-ref: ${{ matrix.environment.ref }}
          tags: ${{ matrix.environment.tags }}
```

## How It Works

The share-environment action performs the following steps:

1. **Action Summary**: Shows what environment will be shared, from which workspace to which registry
2. **Input Validation**: Validates all required parameters and tags format
3. **Azure ML Extension**: Ensures the Azure ML CLI extension is installed
4. **Environment Sharing**: Executes `az ml environment share` with the specified parameters and tags
5. **Reference Extraction**: Extracts environment reference and version from the returned resource ID
6. **Results Output**: Displays the sharing results and registry information

## Error Handling

The action includes comprehensive error handling for:
- Missing required parameters
- Invalid tag formats
- Environment sharing failures
- Resource ID parsing errors

## Prerequisites

- Azure authentication must be configured (using `azure/login@v2`)
- The source environment must exist in the specified workspace
- The target registry must exist and be accessible
- Appropriate permissions for sharing environments between workspace and registry
