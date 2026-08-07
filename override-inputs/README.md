# Override Inputs

Override a value in a YAML file using yq. Changes are ephemeral within the job context.

## Inputs

| Input | Description | Required | Default |
|-------|-------------|----------|---------|
| `file` | Path to the YAML file to modify | Yes | |
| `path` | Dot-notation path to the property (e.g., `inputs.threshold`, `jobs.inference.component`) | Yes | |
| `set-value` | The new value to set | Yes | |
| `value-type` | How to interpret `set-value`: `auto`, `string` or `raw` (see [Value types](#value-types)) | No | `string` |

## Value types

| `value-type` | Behaviour | `set-value: 45` writes |
|--------------|-----------|------------------------|
| `string` (current default) | The value is always written as a quoted string | `threshold: "45"` |
| `auto` | The value is parsed as YAML, so numbers, booleans and strings keep their natural type | `threshold: 45` |
| `raw` | The value is a yq expression, evaluated as-is | `threshold: 45` |

Notes:

- Leaving `value-type` unset is deprecated. It currently resolves to `string` and logs a warning; a future major release will change the default to `auto`. Set it explicitly to pin the behaviour you want.
- With `auto`, a value containing a colon followed by a space (e.g. `key: value`) is parsed as a nested mapping. Use `string` when the value must stay a scalar.
- With `auto`, references such as `azureml:testcomp:4` remain strings, since there is no colon-space.
- `raw` inserts `set-value` directly into the yq expression, so it must only be used with trusted values.

## Usage Examples

### Override a threshold value

```yaml
- name: Override threshold
  uses: equinor/ai-platform-actions/override-inputs@main
  with:
    file: ./pipeline.yaml
    path: inputs.threshold
    set-value: 45
    value-type: auto   # writes 45, not "45"
```

### Override a value that must stay a string

```yaml
- name: Override version label
  uses: equinor/ai-platform-actions/override-inputs@main
  with:
    file: ./pipeline.yaml
    path: inputs.version_label
    set-value: 1.0
    value-type: string
```

### Override using a yq expression

```yaml
- name: Override tag with commit sha
  uses: equinor/ai-platform-actions/override-inputs@main
  with:
    file: ./pipeline.yaml
    path: tags.commit
    set-value: strenv(GITHUB_SHA)
    value-type: raw
```

### Override a component version

```yaml
- name: Override component version
  uses: equinor/ai-platform-actions/override-inputs@main
  with:
    file: ./pipeline.yaml
    path: jobs.inference.component
    set-value: azureml:testcomp:4
    value-type: string
```

### Override compute target

```yaml
- name: Override compute
  uses: equinor/ai-platform-actions/override-inputs@main
  with:
    file: ./pipeline.yaml
    path: settings.default_compute
    set-value: azureml:unified-gpu
    value-type: string
```

## Notes

- Uses `yq` for in-place YAML modification
- Changes only persist within the current job context
- Path uses dot-notation to navigate the YAML structure, restricted to keys and numeric indices (e.g. `jobs.inference.component`, `inputs.items[0]`)

## Related Documentation

- [Azure ML Pipeline Jobs](https://learn.microsoft.com/en-us/azure/machine-learning/concept-ml-pipelines)
- [yq documentation](https://mikefarah.gitbook.io/yq)
