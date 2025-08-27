# Deploy Changed - Automated Azure ML Asset Deployment

## Overview

The Deploy Changed action automatically detects changed Azure ML asset files (environments, components, data, jobs) in your repository and prepares them for deployment. It combines file change detection with deployment configuration generation for seamless MLOps workflows.

## Usage

### Basic Usage
```yaml
- name: Deploy changed Azure ML assets
  uses: equinor/ai-platform-actions/deploy-changed@main
  with:
    client-id: ${{ vars.AZURE_CLIENT_ID }}
```

### Custom Asset Patterns
```yaml
- name: Deploy changed assets with custom patterns
  uses: equinor/ai-platform-actions/deploy-changed@main
  with:
    client-id: ${{ vars.AZURE_CLIENT_ID }}
    asset-patterns: |
      {
        "environment": "ml/environments/**/*.yaml",
        "component": "ml/components/**/*.yml",
        "data": "data/definitions/*.yaml",
        "job": "pipelines/**/*.yaml"
      }
```

## Inputs

| Input | Description | Required | Default |
|-------|-------------|----------|---------|
| `tenant-id` | Tenant ID (falls back to vars.tenant-id) | No | Auto from vars |
| `subscription-id` | Azure subscription ID (falls back to vars.subscription-id) | No | Auto from vars |
| `resource-group` | Resource group (falls back to vars.resource-group) | No | Auto from vars |
| `workspace-name` | ML workspace name (falls back to vars.workspace-name) | No | Auto from vars |
| `client-id` | Client ID for authentication | Yes | - |
| `asset-patterns` | JSON mapping asset types to file patterns | No | Default patterns |
| `base-ref` | Base reference for comparison | No | Auto-detected |
| `head-ref` | Head reference for comparison | No | Auto-detected |
| `deployment-strategy` | `sequential` or `parallel` | No | `sequential` |

## Outputs

| Output | Description |
|--------|-------------|
| `deployed-assets` | JSON array of deployed assets with details |
| `deployment-count` | Number of assets deployed |
| `has-deployments` | Boolean indicating if any deployments occurred |

## Default Asset Patterns

```json
{
  "environment": "environments/*.yaml",
  "component": "components/*.yaml", 
  "data": "data/*.yaml",
  "job": "jobs/*.yaml"
}
```

## Deployment Strategies

### Sequential Deployment
Deploys assets one after another in a single job:

```yaml
- name: Deploy changed assets sequentially
  uses: equinor/ai-platform-actions/deploy-changed@main
  with:
    client-id: ${{ vars.AZURE_CLIENT_ID }}
    deployment-strategy: sequential
```

### Parallel Deployment (Matrix Strategy)
For parallel deployment, use the output with deploy-x and matrix strategy:

```yaml
jobs:
  detect-changes:
    runs-on: ubuntu-latest
    outputs:
      has-deployments: ${{ steps.detect.outputs.has-deployments }}
      config: ${{ steps.detect.outputs.deploy-config-b64 }}
      count: ${{ steps.detect.outputs.deployment-count }}
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - name: Detect changed assets
        id: detect
        uses: equinor/ai-platform-actions/deploy-changed@main
        with:
          client-id: ${{ vars.AZURE_CLIENT_ID }}
          deployment-strategy: parallel

  deploy-parallel:
    needs: detect-changes
    if: needs.detect-changes.outputs.has-deployments == 'true'
    runs-on: ubuntu-latest
    strategy:
      matrix:
        index: ${{ range(0, fromJson(needs.detect-changes.outputs.count)) }}
    steps:
      - uses: actions/checkout@v4
      - name: Deploy asset
        uses: equinor/ai-platform-actions/deploy-x@main
        with:
          client-id: ${{ vars.AZURE_CLIENT_ID }}
          config: ${{ needs.detect-changes.outputs.config }}
          index: ${{ matrix.index }}
```

## Complete Workflow Examples

### Simple Sequential Deployment
```yaml
name: Deploy Changed ML Assets

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
          
      - name: Deploy changed assets
        uses: equinor/ai-platform-actions/deploy-changed@main
        with:
          client-id: ${{ vars.AZURE_CLIENT_ID }}
          
      - name: Summary
        run: |
          echo "Deployed ${{ steps.deploy.outputs.deployment-count }} assets"
```

### Advanced Parallel Deployment
```yaml
name: Advanced ML Asset Deployment

on:
  push:
    branches: [main]

jobs:
  detect-changes:
    runs-on: ubuntu-latest
    outputs:
      has-deployments: ${{ steps.detect.outputs.has-deployments }}
      config: ${{ steps.detect.outputs.deploy-config-b64 }}
      count: ${{ steps.detect.outputs.deployment-count }}
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
          
      - name: Detect changed ML assets
        id: detect
        uses: equinor/ai-platform-actions/deploy-changed@main
        with:
          client-id: ${{ vars.AZURE_CLIENT_ID }}
          deployment-strategy: parallel
          asset-patterns: |
            {
              "environment": "ml/envs/**/*.{yaml,yml}",
              "component": "ml/components/**/*.{yaml,yml}",
              "data": "data/**/*.yaml",
              "job": "pipelines/**/*.yaml"
            }

  deploy-environments:
    needs: detect-changes
    if: needs.detect-changes.outputs.has-deployments == 'true'
    runs-on: ubuntu-latest
    strategy:
      matrix:
        index: ${{ range(0, fromJson(needs.detect-changes.outputs.count)) }}
    steps:
      - uses: actions/checkout@v4
      
      - name: Deploy asset
        uses: equinor/ai-platform-actions/deploy-x@main
        with:
          client-id: ${{ vars.AZURE_CLIENT_ID }}
          config: ${{ needs.detect-changes.outputs.config }}
          index: ${{ matrix.index }}

  summary:
    needs: [detect-changes, deploy-environments]
    if: always()
    runs-on: ubuntu-latest
    steps:
      - name: Deployment Summary
        run: |
          if [ "${{ needs.detect-changes.outputs.has-deployments }}" = "true" ]; then
            echo "✅ Deployed ${{ needs.detect-changes.outputs.count }} Azure ML assets"
          else
            echo "ℹ️ No Azure ML assets changed - no deployments needed"
          fi
```

### Conditional Deployment by Asset Type
```yaml
- name: Detect changes
  id: detect
  uses: equinor/ai-platform-actions/deploy-changed@main
  with:
    client-id: ${{ vars.AZURE_CLIENT_ID }}
    asset-patterns: |
      {
        "environment": "environments/**/*.yaml",
        "component": "components/**/*.yaml"
      }

- name: Deploy only if environments or components changed
  if: steps.detect.outputs.has-deployments == 'true'
  run: |
    echo "Deploying ${{ steps.detect.outputs.deployment-count }} assets"
```

## Asset Pattern Examples

### Standard Structure
```json
{
  "environment": "environments/*.yaml",
  "component": "components/*.yaml",
  "data": "data/*.yaml", 
  "job": "jobs/*.yaml"
}
```

### Nested Structure
```json
{
  "environment": "ml/environments/**/*.{yaml,yml}",
  "component": "ml/components/**/*.{yaml,yml}",
  "data": "datasets/**/*.yaml",
  "job": "pipelines/**/*.yaml"
}
```

### Monorepo Structure
```json
{
  "environment": "projects/*/environments/*.yaml",
  "component": "projects/*/components/*.yaml",
  "data": "shared/data/*.yaml",
  "job": "projects/*/jobs/*.yaml"
}
```

## How It Works

1. **Change Detection**: Analyzes Git diff to find changed files
2. **Pattern Matching**: Filters changes using configurable asset patterns
3. **Config Generation**: Creates deployment configurations for changed assets
4. **Strategy Selection**: Prepares for sequential or parallel deployment
5. **Output Generation**: Provides deployment-ready configurations

This action streamlines MLOps workflows by automatically detecting and preparing changed Azure ML assets for deployment, eliminating manual file tracking and reducing deployment overhead.
