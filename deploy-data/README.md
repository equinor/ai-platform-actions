# How does it work?

## Usage

To use this action from another repository, add a step to your GitHub Actions workflow that references this action. For example:

```yaml
jobs:
  deploy-data:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4
      - name: Deploy Azure ML Data Asset
        uses: equinor/ai-platform-actions/deploy-data@main
        with:
          tenant-id: ${{ vars.AZURE_TENANT_ID }}
          subscription-id: ${{ vars.AZURE_SUBSCRIPTION_ID }}
          resource-group: ${{ vars.AZURE_RESOURCE_GROUP }}
          workspace-name: ${{ vars.AZURE_ML_WORKSPACE_NAME }}
          client-id: ${{ vars.AZURE_CLIENT_ID }}
          data-path: path/to/data.yaml
          type: data | datastore | mltable
```

Replace the input values with the actual values required for your use case. See the action's `action.yaml` for all available inputs and configuration options.

The Github action is a simple wrapper of the az cli command:
[az ml data](https://learn.microsoft.com/en-us/cli/azure/ml/data?view=azure-cli-latest#az-ml-data-create)
```bash
az ml data create --file PATH/FILE.yaml
    [--datastore]
    [--description]
    [--name]
    [--no-wait]
    [--registry-name]
    [--resource-group]
    [--set]
    [--tags]
    [--type]
    [--version]
    [--workspace-name]
```

Notice that there are a number of arguments not used in the input of this action,  
since this action requires it to be specified in the data.yaml file!

Because the command ``` az ml data create ``` requires different schemas depending on the ``` type ``` parameter, this action takes ``` type ``` as a required input, and calls the cli command with it.  
So within the yaml file, the ``` type ``` parameter can be omitted, but it is important that the yaml file matches the specified ``` type ``` give to the action, and has to be one of ``` mltable, data, datastore ```.  

Schemas:  
[MLTable schema](https://learn.microsoft.com/en-us/azure/machine-learning/reference-yaml-mltable?view=azureml-api-2)  
[Data schema](https://learn.microsoft.com/en-us/azure/machine-learning/reference-yaml-data?view=azureml-api-2)  
[Datastore Blob schema](https://learn.microsoft.com/en-us/azure/machine-learning/reference-yaml-datastore-blob?view=azureml-api-2)
[Datastore File schema](https://learn.microsoft.com/en-us/azure/machine-learning/reference-yaml-datastore-files?view=azureml-api-2)  
[Datastore Data Lake Gen2](https://learn.microsoft.com/en-us/azure/machine-learning/reference-yaml-datastore-data-lake-gen2?view=azureml-api-2)  
Do yourself a favour, and don't use the Data Lake Gen1. It is (or should be) deprecated.

The most important ones (``` name, path, description ```) according to the correct YAML schema.

