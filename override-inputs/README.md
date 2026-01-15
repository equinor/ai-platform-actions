# Override Inputs

Override a value in a YAML file using yq. Changes are ephemeral within the job context.

## Inputs

| Input | Description | Required |
|-------|-------------|----------|
| `file` | Path to the YAML file to modify | Yes |
| `path` | Dot-notation path to the property (e.g., `inputs.threshold`, `jobs.inference.component`) | Yes |
| `set-value` | The new value to set | Yes |

## Usage Examples

### Override a threshold value

```yaml
- name: Override threshold
  uses: equinor/ai-platform-actions/override-inputs@main
  with:
    file: ./pipeline.yaml
    path: inputs.threshold
    set-value: 45
```

### Override a component version

```yaml
- name: Override component version
  uses: equinor/ai-platform-actions/override-inputs@main
  with:
    file: ./pipeline.yaml
    path: jobs.inference.component
    set-value: azureml:testcomp:4
```

### Override compute target

```yaml
- name: Override compute
  uses: equinor/ai-platform-actions/override-inputs@main
  with:
    file: ./pipeline.yaml
    path: settings.default_compute
    set-value: azureml:unified-gpu
```

## Notes

- Uses `yq` for in-place YAML modification
- Changes only persist within the current job context
- Path uses dot-notation to navigate the YAML structure

## Related Documentation

- [Azure ML Pipeline Jobs](https://learn.microsoft.com/en-us/azure/machine-learning/concept-ml-pipelines)
- [yq documentation](https://mikefarah.gitbook.io/yq)
