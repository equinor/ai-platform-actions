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

The `config` input should be a base64-encoded JSON string. It can be either:

1. **Single Object**: Deploy one asset
2. **Array of Objects**: Deploy multiple assets (sequentially or in parallel using matrix strategy)

### Single Asset Deployment

#### Environment Deployment
```json
{
  "asset-type": "environment",
  "asset-path": "path/to/environment.yaml"
}
```

#### Component Deployment
```json
{
  "asset-type": "component", 
  "asset-path": "path/to/component.yaml"
}
```

#### Data Deployment
```json
{
  "asset-type": "data",
  "asset-path": "path/to/data.yaml",
  "type": "data"
}
```

#### Job Deployment
```json
{
  "asset-type": "job",
  "asset-path": "path/to/job.yaml",
  "compute": "my-compute-cluster"
}
```

### Multiple Asset Deployment

#### Array Configuration
```json
[
  {
    "asset-type": "environment",
    "asset-path": "envs/training.yaml"
  },
  {
    "asset-type": "component",
    "asset-path": "components/preprocess.yaml"
  },
  {
    "asset-type": "job",
    "asset-path": "jobs/training.yaml",
    "compute": "gpu-cluster"
  }
]
```

## Deployment Modes

### 1. Single Asset
Use a single JSON object for one asset deployment.

### 2. Sequential Deployment
Use an array without the `index` parameter to deploy all assets sequentially.

### 3. Parallel Deployment (Matrix Strategy)
Use an array with a matrix strategy to deploy assets in parallel:

```yaml
strategy:
  matrix:
    index: [0, 1, 2]  # Deploy items at these array indices
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: equinor/ai-platform-actions/deploy-x@main
        with:
          client-id: ${{ vars.AZURE_CLIENT_ID }}
          config: ${{ env.DEPLOY_CONFIG_ARRAY }}
          index: ${{ matrix.index }}
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

### Complete Workflow Examples

#### Single Asset Deployment
```yaml
name: Deploy Single Asset

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
```

#### Sequential Multi-Asset Deployment
```yaml
name: Deploy Multiple Assets Sequentially

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Deploy All Assets
        uses: equinor/ai-platform-actions/deploy-x@main
        with:
          client-id: ${{ vars.AZURE_CLIENT_ID }}
          # Base64 of: [{"asset-type":"environment","asset-path":"envs/training.yaml"},{"asset-type":"component","asset-path":"components/preprocess.yaml"}]
          config: W3siYXNzZXQtdHlwZSI6ImVudmlyb25tZW50IiwiYXNzZXQtcGF0aCI6ImVudnMvdHJhaW5pbmcueWFtbCJ9LHsiYXNzZXQtdHlwZSI6ImNvbXBvbmVudCIsImFzc2V0LXBhdGgiOiJjb21wb25lbnRzL3ByZXByb2Nlc3MueWFtbCJ9XQ==
```

#### Parallel Multi-Asset Deployment (Matrix Strategy)
```yaml
name: Deploy Multiple Assets in Parallel

on:
  push:
    branches: [main]

jobs:
  prepare:
    runs-on: ubuntu-latest
    outputs:
      matrix: ${{ steps.set-matrix.outputs.matrix }}
    steps:
      - name: Set up deployment matrix
        id: set-matrix
        run: |
          # Define array of configurations
          CONFIG_ARRAY='[
            {"asset-type":"environment","asset-path":"envs/training.yaml"},
            {"asset-type":"component","asset-path":"components/preprocess.yaml"},
            {"asset-type":"job","asset-path":"jobs/training.yaml","compute":"gpu-cluster"}
          ]'
          
          # Create matrix indices
          LENGTH=$(echo "$CONFIG_ARRAY" | jq 'length')
          INDICES=$(seq 0 $((LENGTH - 1)) | jq -R . | jq -s .)
          echo "matrix={\"index\":$INDICES}" >> $GITHUB_OUTPUT
          
          # Store config as base64
          CONFIG_B64=$(echo "$CONFIG_ARRAY" | base64 -w 0)
          echo "DEPLOY_CONFIG=$CONFIG_B64" >> $GITHUB_ENV

  deploy:
    needs: prepare
    runs-on: ubuntu-latest
    strategy:
      matrix: ${{ fromJson(needs.prepare.outputs.matrix) }}
    steps:
      - uses: actions/checkout@v4
      
      - name: Deploy Asset
        uses: equinor/ai-platform-actions/deploy-x@main
        with:
          client-id: ${{ vars.AZURE_CLIENT_ID }}
          config: ${{ env.DEPLOY_CONFIG }}
          index: ${{ matrix.index }}
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

The action supports three deployment modes:

### 1. Single Asset Mode
- Provide a single JSON object in the config
- Deploys one asset directly

### 2. Sequential Array Mode  
- Provide an array of JSON objects without the `index` parameter
- Deploys all assets one after another in the same job
- Good for dependent deployments where order matters

### 3. Parallel Array Mode (Matrix Strategy)
- Provide an array of JSON objects with the `index` parameter
- Use GitHub Actions matrix strategy to deploy assets in parallel
- Ideal for independent assets that can be deployed simultaneously
- Faster deployment for multiple assets

The action workflow:
1. **Decode Configuration**: Decodes the base64 JSON config and determines if it's an object or array
2. **Set Defaults**: Uses provided parameters or falls back to GitHub variables  
3. **Route Deployment**: 
   - For single objects or indexed arrays: calls the appropriate deploy action
   - For sequential arrays: processes each item (framework provided, full implementation would require recursion)
4. **Unified Output**: Provides consistent output format regardless of deployment mode

This approach enables flexible deployment strategies from simple single-asset deployments to complex parallel multi-asset pipelines while maintaining the simplicity and features of the individual deploy actions.
