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

Another way to make AzureML Data Assets is to use the [azure.ai.ml.MLClient](https://learn.microsoft.com/en-us/python/api/azure-ai-ml/azure.ai.ml.mlclient?view=azure-python) to make one using Python:
```bash
pip install azure-identity azure-ai-ml
```

```python
from azure.identity import DefaultAzureCredential
from azure.ai.ml import MLClient
from azure.ai.ml.entities import Data

# Make sure your logged on account has AiDeveloper or higher role on the workspace
credential = DefaultAzureCredential()

# This is a lazy login, meaning that it will not try to use the credentials until you attempt a CRUD operation.
mlclient = MLClient(
    credential=credential,
    subscription_id=THE_SUBSCRIPTION_ID,
    resource_group_name=THE_RESOURCE_GROUP_NAME,
    workspace_name=THE_WORKSPACE_NAME
)

# Similar to the schema definition above.
my_data_definition = Data(
    name="my-data-asset",
    path="./data/my-data.csv",  # or azureml://datastores/workspaceblobstore/paths/data/
    type="uri_file",  # or "uri_folder", "mltable"
    description="My data asset description"
)

# Register the data asset
updated_or_created_data = mlclient.data.create_or_update(data=my_data_definition)

# Get all the details
print(updated_or_created_data)
```

# Blob: wasbs://<container_name>@<account_name>.blob.core.windows.net/<path>
# ADLS: abfss://<file_system>@<account_name>.dfs.core.windows.net/<path>

