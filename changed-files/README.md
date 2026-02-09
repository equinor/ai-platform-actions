# Changed Files Action

## Overview

The Changed Files action detects Azure ML asset files (environments, components, data, jobs) that have been modified between two Git references. It outputs a JSON array with `subject` and `filepath` fields that map directly to the [inner-loop](../inner-loop/README.md) action's inputs, enabling automated detect-and-deploy workflows.

The action inspects each YAML file's `$schema` field to determine the asset type automatically.

## Usage

```yaml
- name: Detect changed files
  uses: equinor/ai-platform-actions/changed-files@main
  id: changes
  with:
    filter-pattern: "*.yaml"

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
| `changed-files-json` | JSON array of objects with `subject` and `filepath` fields (inner-loop compatible) |
| `has-changes` | Boolean indicating whether any valid Azure ML asset files were changed |

## Asset Type Detection

The action automatically detects Azure ML asset types by inspecting the `$schema` field in YAML files:

| Detected `subject` | Schema pattern |
|---|---|
| `component` | `commandComponent.schema.json` |
| `environment` | `environment.schema.json` |
| `data` | `data.schema.json` or `mltable.schema.json` |
| `job` | `commandJob.schema.json` or `pipelineJob.schema.json` |

Asset types without a standard `$schema` pattern (`model`, `online-endpoint`, `online-deployment`) are not auto-detected and should be deployed directly via inner-loop.

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

### Filter and Ignore Patterns

```yaml
- name: Detect YAML files but ignore test and docs
  uses: equinor/ai-platform-actions/changed-files@main
  id: changes
  with:
    filter-pattern: "**/*.yaml"
    ignore-pattern: "test/**"
```

### Custom References

```yaml
- name: Compare specific commits
  uses: equinor/ai-platform-actions/changed-files@main
  id: changes
  with:
    base-ref: "abc123"
    head-ref: "def456"
    output-format: "json"
```

## Integration with Inner-Loop

The `changed-files-json` output produces objects with `subject` and `filepath` fields that map directly to inner-loop inputs. Use a [matrix strategy](https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/running-variations-of-jobs-in-a-workflow) to deploy each changed asset in parallel:

```yaml
jobs:
  detect:
    runs-on: ubuntu-latest
    outputs:
      assets: ${{ steps.changes.outputs.changed-files-json }}
      has-changes: ${{ steps.changes.outputs.has-changes }}
    steps:
      - uses: equinor/ai-platform-actions/changed-files@main
        id: changes
        with:
          filter-pattern: "**/*.yaml"
          ignore-pattern: "test/**"

  deploy:
    needs: detect
    if: needs.detect.outputs.has-changes == 'true'
    runs-on: ubuntu-latest
    strategy:
      matrix:
        asset: ${{ fromJson(needs.detect.outputs.assets) }}
      fail-fast: false
    steps:
      - uses: actions/checkout@v4

      - name: Azure Login
        uses: azure/login@v2
        with:
          client-id: ${{ vars.AZURE_CLIENT_ID }}
          tenant-id: ${{ vars.AZURE_TENANT_ID }}
          subscription-id: ${{ vars.AZURE_SUBSCRIPTION_ID }}

      - uses: equinor/ai-platform-actions/inner-loop@main
        with:
          verb: deploy
          subject: ${{ matrix.asset.subject }}
          filepath: ${{ matrix.asset.filepath }}
          subscription-id: ${{ vars.AZURE_SUBSCRIPTION_ID }}
          resource-group: ${{ vars.AZURE_RESOURCE_GROUP }}
          workspace-name: ${{ vars.AZURE_ML_WORKSPACE }}
```

### With Override-Inputs

Use [override-inputs](../override-inputs/README.md) between change detection and deployment to modify YAML values ephemerally (e.g., swapping compute targets per environment):

```yaml
      - uses: actions/checkout@v4

      - uses: equinor/ai-platform-actions/override-inputs@main
        with:
          file: ${{ matrix.asset.filepath }}
          path: settings.default_compute
          set-value: azureml:my-gpu-cluster

      - uses: equinor/ai-platform-actions/inner-loop@main
        with:
          verb: deploy
          subject: ${{ matrix.asset.subject }}
          filepath: ${{ matrix.asset.filepath }}
          subscription-id: ${{ vars.AZURE_SUBSCRIPTION_ID }}
          resource-group: ${{ vars.AZURE_RESOURCE_GROUP }}
          workspace-name: ${{ vars.AZURE_ML_WORKSPACE }}
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

## Event Type Support

The action automatically detects the appropriate Git references based on the GitHub event type:

- **Pull Requests**: Compares base branch to head branch
- **Merge Groups**: Compares merge group base to head
- **Push Events**: Compares before and after commits
- **Custom**: Use `base-ref` and `head-ref` inputs for custom comparisons

## Output Formats

### Space-separated (default)
```
environments/dev.yaml components/train.yaml data/dataset.yaml
```

### JSON
```json
[
  {"subject": "environment", "filepath": "environments/dev.yaml"},
  {"subject": "component", "filepath": "components/train.yaml"},
  {"subject": "data", "filepath": "data/dataset.yaml"}
]
```

### Newline-separated
```
environments/dev.yaml
components/train.yaml
data/dataset.yaml
```

The `changed-files-json` output always contains the full JSON object format regardless of the `output-format` setting.

## Related Documentation

- [Inner-Loop Action](../inner-loop/README.md)
- [Override-Inputs Action](../override-inputs/README.md)
- [Azure ML YAML schemas](https://learn.microsoft.com/en-us/azure/machine-learning/reference-yaml-overview)
- [GitHub Actions matrix strategy](https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/running-variations-of-jobs-in-a-workflow)
