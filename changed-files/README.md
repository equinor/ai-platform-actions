# Changed Files Action

## Overview

The Changed Files action detects Azure ML asset files (environments, components, data, jobs) that have been modified between two Git references and provides them in various output formats with asset-type detection. This action inspects YAML files' `$schema` fields to automatically determine asset types, making it perfect for integration with the deploy-x action for automated Azure ML deployments.

## Usage

```yaml
- name: Detect changed files
  uses: equinor/ai-platform-actions/changed-files@main
  id: changes
  with:
    filter-pattern: "*.yaml"  # Optional: only YAML files
    output-format: "json"     # Optional: output format

- name: Check if files changed
  if: steps.changes.outputs.has-changes == 'true'
  run: |
    echo "Files changed: ${{ steps.changes.outputs.changed-files }}"
```

## Inputs

| Input | Description | Required | Default |
|-------|-------------|----------|---------|
| `base-ref` | Base reference for comparison (auto-detected if not provided) | No | Auto-detected from event |
| `head-ref` | Head reference for comparison (auto-detected if not provided) | No | Auto-detected from event |
| `filter-pattern` | Pattern to filter changed files (supports glob patterns) | No | None (all files) |
| `ignore-pattern` | Pattern to ignore changed files (takes precedence over filter-pattern) | No | None |
| `output-format` | Output format: `space-separated`, `json`, `newline-separated` | No | `space-separated` |

## Outputs

| Output | Description |
|--------|-------------|
| `changed-files` | List of changed asset paths in the specified format |
| `changed-files-json` | JSON array of objects with `asset-type` and `asset-path` fields (compatible with deploy-x) |
| `has-changes` | Boolean indicating whether any valid Azure ML asset files were changed |

## Asset Type Detection

The action automatically detects Azure ML asset types by inspecting the `$schema` field in YAML files:

- **Components**: Files with `commandComponent.schema.json` in `$schema`
- **Environments**: Files with `environment.schema.json` in `$schema` 
- **Data Assets**: Files with `data.schema.json` or `mltable.schema.json` in `$schema`
- **Jobs**: Files with `commandJob.schema.json` or `pipelineJob.schema.json` in `$schema`

Only files with recognized schemas are included in the output. Non-YAML files or YAML files without recognized schemas are ignored.

## Examples

### Basic Usage
```yaml
- name: Detect changed Azure ML assets
  uses: equinor/ai-platform-actions/changed-files@main
  id: changes

- name: Process if assets changed
  if: steps.changes.outputs.has-changes == 'true'
  run: |
    echo "Changed assets: ${{ steps.changes.outputs.changed-files }}"
    echo "Asset details: ${{ steps.changes.outputs.changed-files-json }}"
```

### Filter by Pattern
```yaml
- name: Detect changed YAML files
  uses: equinor/ai-platform-actions/changed-files@main
  id: yaml-changes
  with:
    filter-pattern: "*.yaml"

- name: Detect changed assets in components directory
  uses: equinor/ai-platform-actions/changed-files@main
  id: component-changes
  with:
    filter-pattern: "components/**"
```

### Ignore Patterns
```yaml
- name: Detect changed files excluding tests
  uses: equinor/ai-platform-actions/changed-files@main
  id: production-changes
  with:
    ignore-pattern: "test/**"

- name: Detect YAML files but ignore documentation
  uses: equinor/ai-platform-actions/changed-files@main
  id: yaml-no-docs
  with:
    filter-pattern: "*.yaml"
    ignore-pattern: "docs/**"
```

### Custom References
```yaml
- name: Compare specific commits
  uses: equinor/ai-platform-actions/changed-files@main
  id: custom-changes
  with:
    base-ref: "abc123"
    head-ref: "def456"
    output-format: "json"
```

### JSON Output with Asset Types
```yaml
jobs:
  detect-changes:
    runs-on: ubuntu-latest
    outputs:
      changed-assets: ${{ steps.changes.outputs.changed-files-json }}
      has-changes: ${{ steps.changes.outputs.has-changes }}
    steps:
      - uses: equinor/ai-platform-actions/changed-files@main
        id: changes
        with:
          filter-pattern: "**/*.yaml"
          output-format: "json"

  deploy-assets:
    needs: detect-changes
    if: needs.detect-changes.outputs.has-changes == 'true'
    runs-on: ubuntu-latest
    strategy:
      matrix:
        asset: ${{ fromJson(needs.detect-changes.outputs.changed-assets) }}
    steps:
      - name: Deploy asset
        run: |
          echo "Deploying ${{ matrix.asset.asset-type }}: ${{ matrix.asset.asset-path }}"
```

## Filter Patterns

The action supports glob patterns for both filtering and ignoring files:

### Include Patterns (filter-pattern)
- `*.yaml` - All YAML files
- `*.yml` - All YML files
- `components/**` - All files in components directory and subdirectories
- `jobs/*.yaml` - YAML files in jobs directory only
- `**/*.py` - All Python files recursively

### Ignore Patterns (ignore-pattern)
- `test/**` - Ignore all files in test directories
- `*.md` - Ignore all Markdown files
- `docs/**` - Ignore all documentation files
- `**/*test*` - Ignore all files with "test" in the name
- `.github/**` - Ignore GitHub workflow files

### Pattern Precedence
When both patterns are specified:
1. **ignore-pattern** is applied first (excludes files)
2. **filter-pattern** is applied second (includes files from remaining)

Example: `filter-pattern: "*.yaml"` and `ignore-pattern: "test/**"` will include all YAML files except those in test directories.

## Event Type Support

The action automatically detects the appropriate Git references based on the GitHub event type:

- **Pull Requests**: Compares base branch to head branch
- **Merge Groups**: Compares merge group base to head
- **Push Events**: Compares before and after commits
- **Custom**: Use `base-ref` and `head-ref` inputs for custom comparisons

## Output Formats

### Space-separated (default)
Returns only the asset paths:
```
environments/dev.yaml components/train.yaml data/dataset.yaml
```

### JSON
Returns array of objects with asset-type and asset-path:
```json
[
  {"asset-type": "environment", "asset-path": "environments/dev.yaml"},
  {"asset-type": "component", "asset-path": "components/train.yaml"},
  {"asset-type": "data", "asset-path": "data/dataset.yaml"}
]
```

### Newline-separated
Returns only the asset paths, one per line:
```
environments/dev.yaml
components/train.yaml
data/dataset.yaml
```

**Note**: The `changed-files-json` output always contains the full object format with asset-type information, regardless of the `output-format` setting.

## Integration with Deploy-X

This action is designed to work seamlessly with deploy-x for automated Azure ML asset deployments. The `changed-files-json` output provides the exact format expected by deploy-x:

```yaml
- name: Detect changed Azure ML assets
  uses: equinor/ai-platform-actions/changed-files@main
  id: changes
  with:
    filter-pattern: "**/*.yaml"
    ignore-pattern: "test/**"

- name: Deploy changed assets
  if: steps.changes.outputs.has-changes == 'true'
  uses: equinor/ai-platform-actions/deploy-x@main
  with:
    client-id: ${{ vars.AZURE_CLIENT_ID }}
    config: ${{ base64(steps.changes.outputs.changed-files-json) }}
```

### Why This Integration Works

1. **Asset Type Detection**: The action automatically detects whether a YAML file is an environment, component, data asset, or job by inspecting its `$schema` field
2. **Compatible Format**: The JSON output matches exactly what deploy-x expects: objects with `asset-type` and `asset-path` fields
3. **Base64 Encoding**: Simply wrap the JSON output with `base64()` function to meet deploy-x's input requirements
4. **Filtering**: Use pattern matching to target specific directories or file types for deployment
