# Deploy X - Universal Azure ML Deployment Action

## Overview

Deploy X is a universal deployment action that can deploy any Azure ML asset (environments, components, data, or jobs) based on a base64-encoded JSON configuration. This action acts as a dispatcher to the specific deploy actions.

## Usage

To use this action from another repository, add a step to your GitHub Actions workflow that references this action:

```yaml
jobs:
  deploy-asset:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4
      - name: Deploy Azure ML Asset
        uses: equinor/ai-platform-actions/deploy-x@main
        with:
          client-id: ${{ vars.AZURE_CLIENT_ID }}
          config: ${{ env.DEPLOY_CONFIG }}  # Base64-encoded JSON
```

## Configuration Format

The `config` input should be a base64-encoded JSON string with the following structure:

### Environment Deployment
```json
{
  "asset-type": "environment",
  "asset-path": "path/to/environment.yaml"
}
```

### Component Deployment
```json
{
  "asset-type": "component", 
  "asset-path": "path/to/component.yaml"
}
```

### Data Deployment
```json
{
  "asset-type": "data",
  "asset-path": "path/to/data.yaml",
  "type": "data"
}
```

### Job Deployment
```json
{
  "asset-type": "job",
  "asset-path": "path/to/job.yaml",
  "compute": "my-compute-cluster"
}
```

## Parameter Fallback

This action supports optional parameters that fall back to GitHub variables if not provided:

- `tenant-id` → falls back to `${{ vars.tenant-id }}`
- `subscription-id` → falls back to `${{ vars.subscription-id }}`
- `resource-group` → falls back to `${{ vars.resource-group }}`
- `workspace-name` → falls back to `${{ vars.workspace-name }}`

## Examples

### Creating Base64 Config

You can create the base64-encoded config in various ways:

#### Using bash:
```bash
echo '{"asset-type":"component","asset-path":"./components/my-component.yaml"}' | base64
```

#### Using PowerShell:
```powershell
[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes('{"asset-type":"job","asset-path":"./jobs/training.yaml","compute":"gpu-cluster"}'))
```

#### In GitHub Actions:
```yaml
- name: Prepare config
  run: |
    CONFIG='{"asset-type":"environment","asset-path":"./envs/training-env.yaml"}'
    echo "DEPLOY_CONFIG=$(echo $CONFIG | base64 -w 0)" >> $GITHUB_ENV

- name: Deploy Asset
  uses: equinor/ai-platform-actions/deploy-x@main
  with:
    client-id: ${{ vars.AZURE_CLIENT_ID }}
    config: ${{ env.DEPLOY_CONFIG }}
```

### Complete Workflow Example

```yaml
name: Deploy ML Assets

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Deploy Environment
        uses: equinor/ai-platform-actions/deploy-x@main
        with:
          client-id: ${{ vars.AZURE_CLIENT_ID }}
          config: eyJhc3NldC10eXBlIjoiZW52aXJvbm1lbnQiLCJhc3NldC1wYXRoIjoiLi9lbnZzL3RyYWluaW5nLWVudi55YW1sIn0=
      
      - name: Deploy Component  
        uses: equinor/ai-platform-actions/deploy-x@main
        with:
          client-id: ${{ vars.AZURE_CLIENT_ID }}
          config: eyJhc3NldC10eXBlIjoiY29tcG9uZW50IiwiYXNzZXQtcGF0aCI6Ii4vY29tcG9uZW50cy9wcmVwcm9jZXNzLnlhbWwifQ==
      
      - name: Deploy Training Job
        uses: equinor/ai-platform-actions/deploy-x@main
        with:
          client-id: ${{ vars.AZURE_CLIENT_ID }}
          config: eyJhc3NldC10eXBlIjoiam9iIiwiYXNzZXQtcGF0aCI6Ii4vam9icy90cmFpbmluZy55YW1sIiwiY29tcHV0ZSI6ImdwdS1jbHVzdGVyIn0=
```

## Supported Asset Types

| Asset Type | Required Fields | Optional Fields |
|------------|----------------|-----------------|
| `environment` | `asset-path` | - |
| `component` | `asset-path` | - |
| `data` | `asset-path`, `type` | - |
| `job` | `asset-path` | `compute` |

## Outputs

The action provides unified outputs that work regardless of the asset type:

- `resource-id`: Full Azure resource ID of the deployed asset
- `asset-ref`: Reference string for the asset within the workspace
- `asset-version`: Version/name of the asset within the workspace

## How It Works

1. **Decode Configuration**: Decodes the base64 JSON config and extracts parameters
2. **Set Defaults**: Uses provided parameters or falls back to GitHub variables
3. **Route to Specific Action**: Calls the appropriate deploy action based on `asset-type`
4. **Unified Output**: Provides consistent output format regardless of asset type

This action simplifies deployment workflows by providing a single interface for all Azure ML asset types while maintaining the flexibility and features of the individual deploy actions.
