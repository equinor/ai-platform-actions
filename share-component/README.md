# Share Component Action

This action shares an Azure ML Component from a workspace to a registry, enabling component reuse across different environments and teams.

## Description

The Share Component action allows you to share Azure ML Components from a source workspace to a target registry. This is useful for:

- Making components available across multiple workspaces
- Creating reusable component libraries in registries
- Promoting components from development to production environments
- Sharing components across teams and organizations

## Usage

### Basic Example

```yaml
- name: Azure Login
  uses: azure/login@v2
  with:
    client-id: ${{ vars.AZURE_CLIENT_ID }}
    tenant-id: ${{ vars.AZURE_TENANT_ID }}
    subscription-id: ${{ vars.AZURE_SUBSCRIPTION_ID }}
    enable-AzPSSession: true
    auth-type: SERVICE_PRINCIPAL
  id: azure-login

- name: Share component to registry
  uses: ./share-component
  with:
    token: ${{ steps.azure-login.outputs.access-token }}
    expires-on: ${{ steps.azure-login.outputs.expires-on }}
    tenant-id: ${{ vars.AZURE_TENANT_ID }}
    subscription-id: ${{ vars.AZURE_SUBSCRIPTION_ID }}
    resource-group: "my-resource-group"
    workspace-name: "my-workspace"
    client-id: ${{ vars.AZURE_CLIENT_ID }}
    registry-name: "my-registry"
    component-ref: "azureml:preprocess_data:1"
```

### Example with Tags

```yaml
- name: Azure Login
  uses: azure/login@v2
  with:
    client-id: ${{ vars.AZURE_CLIENT_ID }}
    tenant-id: ${{ vars.AZURE_TENANT_ID }}
    subscription-id: ${{ vars.AZURE_SUBSCRIPTION_ID }}
    enable-AzPSSession: true
    auth-type: SERVICE_PRINCIPAL
  id: azure-login

- name: Share component with tags
  uses: ./share-component
  with:
    token: ${{ steps.azure-login.outputs.access-token }}
    expires-on: ${{ steps.azure-login.outputs.expires-on }}
    tenant-id: ${{ vars.AZURE_TENANT_ID }}
    subscription-id: ${{ vars.AZURE_SUBSCRIPTION_ID }}
    resource-group: "my-resource-group"
    workspace-name: "my-workspace"
    client-id: ${{ vars.AZURE_CLIENT_ID }}
    registry-name: "my-registry"
    component-ref: "train_model:2"
    tags: "purpose=training,language=python,validated=true"
```

### Complete Workflow Example

```yaml
name: Share ML Component

on:
  workflow_dispatch:
    inputs:
      component_ref:
        description: 'Component reference to share'
        required: true
        default: 'azureml:preprocess:1'
      registry_name:
        description: 'Target registry name'
        required: true
        default: 'shared-components-registry'

permissions:
  id-token: write
  contents: read

jobs:
  share-component:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Azure Login
        uses: azure/login@v2
        with:
          client-id: ${{ vars.AZURE_CLIENT_ID }}
          tenant-id: ${{ vars.AZURE_TENANT_ID }}
          subscription-id: ${{ vars.AZURE_SUBSCRIPTION_ID }}
          enable-AzPSSession: true
          auth-type: SERVICE_PRINCIPAL
        id: azure-login

      - name: Share Component
        uses: ./share-component
        id: share
        with:
          token: ${{ steps.azure-login.outputs.access-token }}
          expires-on: ${{ steps.azure-login.outputs.expires-on }}
          tenant-id: ${{ vars.AZURE_TENANT_ID }}
          subscription-id: ${{ vars.AZURE_SUBSCRIPTION_ID }}
          resource-group: ${{ vars.AZURE_RESOURCE_GROUP }}
          workspace-name: ${{ vars.AZURE_WORKSPACE_NAME }}
          client-id: ${{ vars.AZURE_CLIENT_ID }}
          registry-name: ${{ github.event.inputs.registry_name }}
          component-ref: ${{ github.event.inputs.component_ref }}
          tags: "shared-by=github-actions,date=${{ github.run_number }}"

      - name: Display Results
        run: |
          echo "Component shared successfully!"
          echo "Resource ID: ${{ steps.share.outputs.resource-id }}"
          echo "Component Reference: ${{ steps.share.outputs.component-ref }}"
          echo "Component Version: ${{ steps.share.outputs.component-version }}"
```

## Inputs

| Name | Description | Required | Default |
|------|-------------|----------|---------|
| `token` | Access token from Azure login action | ✅ | |
| `expires-on` | Token expiration timestamp from Azure login action | ✅ | |
| `tenant-id` | Azure tenant ID | ✅ | |
| `subscription-id` | Azure subscription ID | ✅ | |
| `resource-group` | Azure resource group name (for the workspace) | ✅ | |
| `workspace-name` | Azure Machine Learning workspace name (source workspace) | ✅ | |
| `client-id` | Client ID configured with Federated Credentials | ✅ | |
| `registry-name` | Azure ML registry name (target registry) | ✅ | |
| `component-ref` | Component reference (e.g., "azureml:mycomponent:1" or resource-id or "name:version") | ✅ | |
| `tags` | Tags to set on the shared component (format: "key1=value1,key2=value2") | ❌ | |

### Component Reference Formats

The `component-ref` input accepts several formats:

- **azureml URI**: `azureml:component_name:1`
- **Name and version**: `component_name:1`
- **Resource ID**: Full Azure resource identifier
- **Name only**: `component_name` (uses latest version)

### Tags Format

Tags should be provided as comma-separated key=value pairs:
- `"environment=production,validated=true"`
- `"team=ml-ops,project=customer-analytics"`
- `"version=1.0,stable=true"`

## Outputs

| Name | Description | Example |
|------|-------------|---------|
| `resource-id` | Resource ID of the shared component in the registry | `/subscriptions/.../providers/Microsoft.MachineLearningServices/registries/my-registry/components/preprocess/versions/1` |
| `component-ref` | Reference string of component within Azure ML registry | `azureml:preprocess:1` |
| `component-version` | The version of the component within the registry | `1` |

## Prerequisites

### Azure Resources
- Source Azure ML workspace containing the component
- Target Azure ML registry
- Appropriate permissions to read from workspace and write to registry

### Authentication
This action requires Azure authentication via the `azure/login` action with token outputs enabled:

```yaml
- name: Azure Login
  uses: azure/login@v2
  with:
    client-id: ${{ vars.AZURE_CLIENT_ID }}
    tenant-id: ${{ vars.AZURE_TENANT_ID }}
    subscription-id: ${{ vars.AZURE_SUBSCRIPTION_ID }}
    enable-AzPSSession: true
    auth-type: SERVICE_PRINCIPAL
  id: azure-login
```

The action requires:
- Service Principal with Federated Credentials
- `client-id`, `tenant-id`, and `subscription-id`
- Token outputs from azure-login: `access-token` and `expires-on`

### Required Permissions
The authenticated principal needs:
- **Workspace**: `AzureML Data Scientist` or `Reader` role
- **Registry**: `AzureML Registry User` or `Contributor` role

## Error Handling

The action validates inputs and provides clear error messages:

- **Missing required inputs**: Lists all missing required parameters
- **Invalid tags format**: Shows correct tag format with examples
- **Component not found**: Indicates if the component reference is invalid
- **Permission errors**: Shows authentication or authorization issues
- **Registry access**: Validates registry exists and is accessible

## Notes

### Component Sharing Process
1. The action validates all inputs and creates Azure ML client connections
2. Connects to the source workspace using the provided authentication token
3. Retrieves the specified component from the workspace
4. Applies any additional tags to the component metadata
5. Connects to the target registry using the same authentication
6. Uses the Azure ML Python SDK `create_or_update` method to share the component
7. Provides outputs for downstream use

**Note:** This action uses the Azure ML Python SDK instead of Azure CLI because the `az ml component share` command is not available. The Python SDK's `create_or_update` method provides equivalent functionality for sharing components to registries.

### Registry vs Workspace
- **Workspace**: Development environment for creating and testing components
- **Registry**: Shared repository for reusable components across workspaces
- Components in registries can be used by multiple workspaces

### Version Management
- When sharing a component, it maintains its original version
- If a component with the same name and version already exists in the registry, the operation may fail
- Use tags to differentiate between component variants

## Troubleshooting

### Common Issues

1. **Component not found**
   - Verify the component reference format
   - Check if the component exists in the source workspace
   - Ensure the component is in a completed state

2. **Permission denied**
   - Verify authentication is properly configured
   - Check that the service principal has required permissions
   - Ensure the registry and workspace are in the correct subscription

3. **Invalid tags**
   - Use the format `key1=value1,key2=value2`
   - Avoid special characters in tag keys
   - Ensure no spaces around the equals sign

4. **Registry not accessible**
   - Verify the registry name is correct
   - Check if the registry exists in the specified subscription
   - Ensure network connectivity if using private registries
