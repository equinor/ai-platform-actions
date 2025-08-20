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
