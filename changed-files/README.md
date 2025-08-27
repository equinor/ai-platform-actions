# Changed Files Action

## Overview

The Changed Files action detects files that have been modified between two Git references (commits, branches, etc.) and provides them in various output formats. This action is particularly useful for triggering deployments or actions only when specific files have changed.

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
| `changed-files` | List of changed files in the specified format |
| `changed-files-json` | List of changed files as JSON array (always available) |
| `has-changes` | Boolean indicating whether any files were changed |

## Examples

### Basic Usage
```yaml
- name: Detect all changed files
  uses: equinor/ai-platform-actions/changed-files@main
  id: changes

- name: Process if files changed
  if: steps.changes.outputs.has-changes == 'true'
  run: |
    echo "Changed files: ${{ steps.changes.outputs.changed-files }}"
```

### Filter by Pattern
```yaml
- name: Detect changed YAML files
  uses: equinor/ai-platform-actions/changed-files@main
  id: yaml-changes
  with:
    filter-pattern: "*.yaml"

- name: Detect changed files in components directory
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

### JSON Output for Matrix
```yaml
jobs:
  detect-changes:
    runs-on: ubuntu-latest
    outputs:
      changed-files: ${{ steps.changes.outputs.changed-files-json }}
      has-changes: ${{ steps.changes.outputs.has-changes }}
    steps:
      - uses: equinor/ai-platform-actions/changed-files@main
        id: changes
        with:
          filter-pattern: "components/*.yaml"
          output-format: "json"

  process-changes:
    needs: detect-changes
    if: needs.detect-changes.outputs.has-changes == 'true'
    runs-on: ubuntu-latest
    strategy:
      matrix:
        file: ${{ fromJson(needs.detect-changes.outputs.changed-files) }}
    steps:
      - name: Process file
        run: echo "Processing ${{ matrix.file }}"
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
```
file1.yaml file2.yaml components/comp1.yaml
```

### JSON
```json
["file1.yaml", "file2.yaml", "components/comp1.yaml"]
```

### Newline-separated
```
file1.yaml
file2.yaml
components/comp1.yaml
```

## Integration with Deploy-X

This action pairs perfectly with deploy-x for conditional deployments:

```yaml
- name: Detect changed deployment files
  uses: equinor/ai-platform-actions/changed-files@main
  id: changes
  with:
    filter-pattern: "deployments/*.yaml"
    ignore-pattern: "deployments/test/**"

- name: Deploy changed files
  if: steps.changes.outputs.has-changes == 'true'
  uses: equinor/ai-platform-actions/deploy-x@main
  with:
    client-id: ${{ vars.AZURE_CLIENT_ID }}
    config: ${{ steps.generate-config.outputs.config }}
```
