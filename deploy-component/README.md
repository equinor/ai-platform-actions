# How does it work?

## Usage

To use this action from another repository, add a step to your GitHub Actions workflow that references this action. For example:

```yaml
jobs:
  deploy-component:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4
      - name: Deploy Azure ML Component
        uses: equinor/ai-platform-actions/deploy-component@main
        with:
          tenant-id: ${{ vars.AZURE_TENANT_ID }}
          subscription-id: ${{ vars.AZURE_SUBSCRIPTION_ID }}
          resource-group: ${{ vars.AZURE_RESOURCE_GROUP }}
          workspace-name: ${{ vars.AZURE_ML_WORKSPACE_NAME }}
          client-id: ${{ vars.AZURE_CLIENT_ID }}
          component-path: path/to/component.yaml
```

Replace the input values with the actual values required for your use case. See the action's `action.yaml` for all available inputs and configuration options.

The Github action is a simple wrapper of the az cli command:
[az ml component](https://learn.microsoft.com/en-us/cli/azure/ml/component?view=azure-cli-latest#az-ml-component-create)
```bash
az ml component create --file PATH/FILE.yaml
    [--name]
    [--registry-name]
    [--resource-group]
    [--set]
    [--skip-validation]
    [--version]
    [--workspace-name]
```

Notice that the most important part of this command is the content of PATH/FILE.yaml.  
Configuration for the component should be put in the yaml file that is a required input of this action.

The --version argument is not used here. This means a new version will be created (unless the contents otherwise are exactly the same as in an exisiting version of a component with the same name).

The most important configuration of a component (``` type, environment, command, code, name, display-name, description,  is_deterministic ```) can be set there according to the [CLI (v2) component YAML schema](https://learn.microsoft.com/en-us/azure/machine-learning/reference-yaml-component-command?view=azureml-api-2).  
In particular, the ``` is_deterministic``` is important for the behaviour: If ```True```, it skips execution if the input is the same as a previous execution, and output is then set to the same as the first output.
If ```False```, the component always executes, no matter if the input is the same.

Components can be of different types (command, parallel, pipeline) and should be configured according to their specific requirements and use cases.
