# How does it work?

## Prerequisites

**Important:** This action requires Azure authentication to be configured before use. Add the Azure login step to your workflow before calling this action:

```yaml
- name: Azure Login
  uses: azure/login@v2
  with:
    client-id: ${{ secrets.AZURE_CLIENT_ID }}
    tenant-id: ${{ secrets.AZURE_TENANT_ID }}
    subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
    enable-AzPSSession: true
    auth-type: SERVICE_PRINCIPAL
```

## Usage

To use this action from another repository, add a step to your GitHub Actions workflow that references this action. For example:

```yaml
jobs:
  deploy-job:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4
      
      - name: Azure Login
        uses: azure/login@v2
        with:
          client-id: ${{ secrets.AZURE_CLIENT_ID }}
          tenant-id: ${{ secrets.AZURE_TENANT_ID }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
          enable-AzPSSession: true
          auth-type: SERVICE_PRINCIPAL
      
      - name: Deploy Azure ML Job
        uses: equinor/ai-platform-actions/deploy-job@main
        with:
          tenant-id: ${{ vars.AZURE_TENANT_ID }}
          subscription-id: ${{ vars.AZURE_SUBSCRIPTION_ID }}
          resource-group: ${{ vars.AZURE_RESOURCE_GROUP }}
          workspace-name: ${{ vars.AZURE_ML_WORKSPACE_NAME }}
          client-id: ${{ vars.AZURE_CLIENT_ID }}
          job-path: path/to/job.yaml
          compute: my-compute-cluster  # Optional: defaults to 'serverless'
```

Replace the input values with the actual values required for your use case. See the action's `action.yaml` for all available inputs and configuration options.

The Github action is a simple wrapper of the az cli command:
[az ml job](https://learn.microsoft.com/en-us/cli/azure/ml/job?view=azure-cli-latest#az-ml-job-create)
```bash
az ml job create 
    [--file]
    [--name]
    [--no-wait]
    [--registry-name]
    [--resource-group]
    [--set]
    [--skip-validation]
    [--stream]
    [--workspace-name]
```

Notice that there are a number of arguments not used in the input of this action.  
Instead, those arguments should be put in the job.yaml file that is in the input.

## Compute Configuration

This action includes a `compute` input parameter that allows you to specify which compute target the job should run on:
- **Default**: `serverless` - Uses Azure ML serverless compute (no compute override applied)
- **Custom**: Specify the name of an existing compute cluster or Kubernetes cluster within your workspace
- When `compute` is set to `serverless`, the action runs without setting the compute property, allowing the job to use serverless compute or any compute specified in the job YAML file
- When `compute` is set to a custom value, the action uses `--set compute=${{ inputs.compute }}` to override any compute setting in the job YAML file

The most important ones (``` type, environment, code, command, inputs, outputs ```)  
can be set there according to the [CLI (v2) job YAML schema](https://learn.microsoft.com/en-us/azure/machine-learning/reference-yaml-job-command?view=azureml-api-2).

Note: When using a custom compute target, the action input will override any `compute` setting in your job YAML file.

Jobs can be of different types (command, pipeline, sweep) and should be configured according to their specific requirements and use cases.

Another way to create AzureML Jobs is to use the [azure.ai.ml.MLClient](https://learn.microsoft.com/en-us/python/api/azure-ai-ml/azure.ai.ml.mlclient?view=azure-python) to make one using Python:
```bash
pip install azure-identity azure-ai-ml
```

```python
from azure.identity import DefaultAzureCredential
from azure.ai.ml import MLClient
from azure.ai.ml.entities import CommandJob

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
my_job_definition = CommandJob(
    display_name="My Job",
    description="My job description",
    code="./src",  # Path to your code directory
    command="python main.py --input ${{inputs.input_data}} --output ${{outputs.output_data}}",
    environment="azureml:my-environment:1",  # Reference to an environment
    compute="my-compute-cluster",  # Name of compute target
    inputs={
        "input_data": {"type": "uri_folder", "path": "azureml://datastores/workspaceblobstore/paths/data/"}
    },
    outputs={
        "output_data": {"type": "uri_folder"}
    }
)

# Submit the job
submitted_job = mlclient.jobs.create_or_update(job=my_job_definition)

# Get all the details
print(submitted_job)
```

## Input



## Output

You may access the output of a job by referring to it using a specific pattern:  
```azureml://jobs/{job-name}/outputs/artifacts/outputs/{files-written-by-job}```  
The ```{job-name}``` is what you see when selecting "Job" menu in the workspace GUI.
It defaults to a ```pronoun_substantive_GUID``` pattern.  
The ```azureml://jobs/{job-name}/outputs/artifacts/outputs/``` is the default working directory when the jobs are run, so ```{files-written-by-job}``` are the result if just writing files directly. (Actually it is the result of those files being copied to the workspace storage account upon finishing a job).  


```
```