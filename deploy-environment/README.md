# How does it work?

## Usage

To use this action from another repository, add a step to your GitHub Actions workflow that references this action. For example:

```yaml
jobs:
  deploy-environment:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4
      - name: Deploy Azure ML Environment
        uses: equinor/ai-platform-actions/deploy-environment@main
        with:
          tenant-id: ${{ vars.tenant-id }}
          subscription-id: ${{ vars.subscription-id }}
          resource-group: ${{ vars.resource-group }}
          workspace-name: ${{ vars.workspace-name }}
          client-id: ${{ vars.client-id }}
          environment-file: path/to/environment.yaml
```

Replace `environment-file` and other inputs with the actual values required for your use case.  
Notice that only client-ids were federated credentials are used are supported in this action.  
This include Service Principals and User Assigned Managed Identities.  
It is preferrable to use UAMIs, as the token obtained by the Github worker differs:  
The Service Principal have a timeout of one hour, while the UAMI one is a day. (ML jobs may take some time to finish).  

The Github action is a simple wrapper of the az cli command:
[az ml environment](https://learn.microsoft.com/en-us/cli/azure/ml/environment?view=azure-cli-latest#az-ml-environment-create)
```bash
az ml environment create 
    [--build-context]
    [--conda-file]
    [--datastore]
    [--description]
    [--dockerfile-path]
    [--file]
    [--image]
    [--name]
    [--no-wait]
    [--os-type]
    [--registry-name]
    [--resource-group]
    [--set]
    [--tags]
    [--version]
    [--workspace-name]
```

Notice that there are a number of arguments not used in the input of this action.  
Instead, those arguments should be put in the environment.yaml file that is in the input.

The most important ones (``` name, description, build-context, conda-file, dockerfile-path, image, os-type, tags ```)  
can be set there according to the [CLI (v2) environment YAML schema](https://learn.microsoft.com/en-us/azure/machine-learning/reference-yaml-environment?view=azureml-api-2).

Environments destinded for inference usage should also consider setting the specialised inference_config attributes.

Another way to make an AzureML Environment is to use the [azure.ai.ml.MLClient](https://learn.microsoft.com/en-us/python/api/azure-ai-ml/azure.ai.ml.mlclient?view=azure-python) to make one using Python:
```bash
pip install azure-identity azure-ai-ml
```

```python
from azure.identity import DefaultAzureCredential
from azure.ai.ml import MLClient
from azure.ai.ml.entities import Environment

# Make sure your loggoed on account has AiDeveloper or higher role on the workspace
credential = DefaultAzureCredential()

# This is a lazy login, meaning that it will not try to use the credentials until you attempt a CRUD operation.
mlclient = MLClient(
    credential=credential,
    subscription_id=THE_SUBSCRIPTION_ID,
    resource_group_name=THE_RESOURCE_GROUP_NAME,
    workspace_name=THE_WORKSPACE_NAME
)

# Similar to the schema definition above.
my_environment_definition = Environment(
    # Fill in all the necessary properties
)

# Probably takes a while to build and register
updated_or_created_env = mlclient.enviroment.create_or_update(environment=my_environment_definition)

# Get all the details
print(updated_or_created_env)

```

## Useful docker images for enviornments

[Current base for AzureML containers](https://github.com/Azure/AzureML-Containers/tree/master/images)

You will see them referenced as:  
```openmpi{mpiversion}-ubuntu{ubuntuversion}``` - Regular jobs,  
```openmpi{mpiversion}-cuda{cudaversion}-ubuntu{ubuntuversion}``` - Jobs running on GPUs,  
```openmpi{mpiversion}-cuda{cudaversion}-cudnn{cudnnversion}-ubuntu{ubuntuversion}``` - GPU jobs with cudnn driver.  

What it means:  
mpi : Message Passing Interface. An old but still very widely used technology for executing processes in parallell on multi-core architectures. Remember to set LD_LIBRARY_PATH before using mpirun or mpiexec.  
cuda: Compute Unified Device Architecture. Allows easy use of Nvidia GPUs (widely used on Azure).  
cudnn: CUda Deep Neural Network. Libraries for optimized use of neural networks are installed.  

On AzureML, there are a number of curated Environments ready to use.
Choose ```Environments``` - ```Curated Environments``` - choose one, f.ex ```minimal-py312-cuda12.4-inference:1```.
When referring to this environment in a YAML file or from python, write  
```azureml://registries/azureml/environments/minimal-py312-cuda12.4-inference:1```  

An AzureML Workspace is associated with a Container Registry.  
All Environments you build and register are stored there, and may be used by any job you run.
When you register an Environment (f.ex when using this action), it may be referred to as  
```azureml:{environment-name}:{environment-version}```
Both the reference and the version are outputs of the action, while the name is an input.  

When inspecting an Environment, you will find it has a "Azure container registry" property.  
This is the direct link to the AzureContainer Registry and the name.  You may use docker pull on it to fetch the image locally,  
although first remember to log in to the ACR using ```az acr login --name {container-registry-name}``` before ```docker pull {image-link}```.  



