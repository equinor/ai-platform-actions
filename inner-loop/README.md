# Inner Loop Action

A unified GitHub Action for Azure ML operations using typer for clean command routing.

## Overview

The Inner Loop action consolidates various Azure ML operations (deploy, share) for different resource types (data, environment, component, model, job) into a single, flexible action. It uses typer to provide a clean, intuitive CLI-style interface.

## Implementation Status

**✅ FULLY IMPLEMENTED** - All deploy and share operations are complete and ready for production use.

### Deploy Operations
- ✅ **deploy data**: Deploy data assets to Azure ML workspace
- ✅ **deploy environment**: Deploy Azure ML environments with build support
- ✅ **deploy component**: Deploy Azure ML components with automatic versioning
- ✅ **deploy job**: Submit Azure ML jobs to workspace

### Share Operations
- ✅ **share data**: Share data assets from workspace to registry
- ✅ **share environment**: Share environments from workspace to registry with stage promotion
- ✅ **share component**: Share components from workspace to registry with environment replacement
- ✅ **share model**: Share models from workspace to registry with stage promotion

## Architecture

### Structure

The action is organized into modular Python files:

- **main.py**: Entry point that routes commands using typer
- **deploy.py**: All deploy operations with full Azure ML SDK integration
- **share.py**: All share operations with registry support and stage promotion
- **getasset.py**: Helper functions for retrieving and filtering Azure ML assets
- **util.py**: Utility functions for authentication, tagging, and GitHub output
- **action.yaml**: GitHub Action composite definition

Each module uses typer's `@app.command()` decorator for clean, self-documenting CLI interfaces.

### Key Features

- **Automatic Version Management**: Components automatically increment to next integer version
- **Command Normalization**: Multiline component commands are automatically cleaned (backslashes and line breaks removed)
- **Tag Merging**: Tags from YAML configs and command-line inputs are intelligently merged
- **Stage Promotion**: Share operations support promoting assets to specific stages (e.g., "Production")
- **Environment Replacement**: Component sharing automatically replaces workspace environments with registry equivalents
- **Flexible Authentication**: Supports both token-based (federated credentials) and DefaultAzureCredential

### Authentication

The action supports two authentication methods:

1. **Token-based authentication** (Recommended for GitHub Actions)
   - Requires: `client-id` and `tenant-id`
   - Uses `az account get-access-token` to obtain access token
   - Works with Azure federated credentials

2. **DefaultAzureCredential** (For local development)
   - No credentials required in inputs
   - Supports: Environment variables, Managed identity, Azure CLI, VS Code, Azure PowerShell, and more
   - Perfect for local testing and development

## Usage

### Deploy Data Asset

```yaml
- uses: ./inner-loop
  with:
    verb: deploy
    subject: data
    subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
    resource-group: my-resource-group
    workspace-name: my-workspace
    filepath: ./data/my-data.yaml
    tags: "env=prod,team=ml"
```

### Deploy Environment

```yaml
- uses: ./inner-loop
  with:
    verb: deploy
    subject: environment
    subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
    resource-group: my-resource-group
    workspace-name: my-workspace
    filepath: ./environments/my-env.yaml
    tags: "version=1.0"
```

### Deploy Component

```yaml
- uses: ./inner-loop
  with:
    verb: deploy
    subject: component
    subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
    resource-group: my-resource-group
    workspace-name: my-workspace
    filepath: ./components/my-component.yaml
    tags: "type=training,framework=pytorch"
```

**Component Features:**
- Automatically finds and increments to next integer version
- Cleans multiline commands (removes `\` and line breaks)
- Merges tags from YAML and command line

### Deploy Job

```yaml
- uses: ./inner-loop
  with:
    verb: deploy
    subject: job
    subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
    resource-group: my-resource-group
    workspace-name: my-workspace
    filepath: ./jobs/my-job.yaml
```

### Share to Registry with Stage Promotion

```yaml
- name: Deploy Component to Workspace
  id: deploy
  uses: ./inner-loop
  with:
    verb: deploy
    subject: component
    subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
    resource-group: my-resource-group
    workspace-name: my-workspace
    filepath: ./components/my-component.yaml

- name: Share Component to Registry
  uses: ./inner-loop
  with:
    verb: share
    subject: component
    subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
    resource-group: my-resource-group
    workspace-name: my-workspace
    registry-name: my-registry
    component-ref: my-component
    promote-stage: "Production"
    tags: "env=prod"
```

**Share Features:**
- Automatically increments version in registry
- Replaces workspace environment references with registry equivalents (for components)
- Supports stage promotion via tags
- Works for data, environment, component, and model assets

## Inputs

| Input | Required | Description |
|-------|----------|-------------|
| `verb` | Yes | Action verb: `deploy` or `share` |
| `subject` | Yes | Target subject: `data`, `environment`, `component`, `model`, or `job` |
| `tenant-id` | No | Azure tenant ID (required for token-based auth) |
| `subscription-id` | Yes | Azure subscription ID |
| `resource-group` | Yes | Azure resource group name |
| `workspace-name` | No* | Azure ML workspace name (*required for most operations) |
| `registry-name` | No* | Azure ML registry name (*required for share operations) |
| `client-id` | No | Client ID for federated credentials (required for token-based auth) |
| `filepath` | No* | Path to configuration YAML file (*required for deploy operations) |
| `component-ref` | No* | Component name (*for share component) |
| `data-ref` | No* | Data asset name (*for share data) |
| `env-ref` | No* | Environment name (*for share environment) |
| `model-ref` | No* | Model name (*for share model) |
| `tags` | No | Tags in format: `key1=value1,key2=value2` |
| `promote-stage` | No | Stage to promote asset to (e.g., "Production") |
| `image-build-compute` | No | Compute cluster name for environment builds (instead of serverless) |

## Outputs

| Output | Description |
|--------|-------------|
| `resource-id` | Full Azure resource ID of the created/shared resource |
| `reference` | Azure ML reference string (e.g., `azureml:name:version`) |
| `version` | Version number of the resource (or job name for jobs) |

## Complete Example Pipeline

```yaml
name: Deploy and Share Azure ML Assets

on:
  push:
    branches: [main]

jobs:
  deploy-and-share:
    runs-on: ubuntu-latest
    permissions:
      id-token: write
      contents: read
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Azure Login
        uses: azure/login@v1
        with:
          client-id: ${{ secrets.AZURE_CLIENT_ID }}
          tenant-id: ${{ secrets.AZURE_TENANT_ID }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
      
      - name: Deploy Environment
        id: deploy-env
        uses: ./inner-loop
        with:
          verb: deploy
          subject: environment
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
          resource-group: my-resource-group
          workspace-name: my-workspace
          filepath: ./environments/training-env.yaml
          tags: "version=1.0,env=prod"
      
      - name: Deploy Component
        id: deploy-comp
        uses: ./inner-loop
        with:
          verb: deploy
          subject: component
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
          resource-group: my-resource-group
          workspace-name: my-workspace
          filepath: ./components/training-component.yaml
          tags: "type=training"
      
      - name: Share Environment to Registry
        uses: ./inner-loop
        with:
          verb: share
          subject: environment
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
          resource-group: my-resource-group
          workspace-name: my-workspace
          registry-name: my-registry
          env-ref: training-env
          promote-stage: "Production"
      
      - name: Share Component to Registry
        uses: ./inner-loop
        with:
          verb: share
          subject: component
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
          resource-group: my-resource-group
          workspace-name: my-workspace
          registry-name: my-registry
          component-ref: training-component
          promote-stage: "Production"
      
      - name: Deploy Job
        uses: ./inner-loop
        with:
          verb: deploy
          subject: job
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
          resource-group: my-resource-group
          workspace-name: my-workspace
          filepath: ./jobs/training-job.yaml
```

## Local Development

### Building the Docker Image

```bash
cd inner-loop
docker build -t inner-loop:latest .
```

### Local Testing with Azure CLI

```bash
# Authenticate with Azure CLI
az login

# Run deploy command
python main.py deploy component \
  --subscription "$SUBSCRIPTION_ID" \
  --resource-group "$RESOURCE_GROUP" \
  --workspace-name "$WORKSPACE_NAME" \
  --filepath "./components/my-component.yaml" \
  --tags "env=dev"

# Run share command
python main.py share component \
  --subscription "$SUBSCRIPTION_ID" \
  --resource-group "$RESOURCE_GROUP" \
  --workspace-name "$WORKSPACE_NAME" \
  --registry-name "$REGISTRY_NAME" \
  "my-component" \
  --promote-stage "Development"
```

## Extending the Action

### Adding a New Deploy Operation

Add a new command function in `deploy.py`:

```python
@app.command()
def my_new_asset(
    subscription_id: Annotated[str, typer.Option("--subscription","-s")],
    resource_group: Annotated[str, typer.Option("--resource-group","-g")],
    workspace_name: Annotated[str, typer.Option("--workspace-name","-w")],
    filepath: str,
    token: Optional[str] = None,
    expires_on: Optional[int] = None,
    tags: Annotated[Optional[str], typer.Option(callback=load_safe_tags)]=None
):
    """Deploy my new asset to Azure ML workspace"""
    print(f"[deploy my_new_asset] Deploying asset")
    
    client = get_workspace_client(
        subscription_id, resource_group, workspace_name, token, expires_on
    )
    
    # Load and deploy your asset
    asset = load_my_asset(source=filepath)
    result = client.my_assets.create_or_update(asset)
    
    print(f"[deploy my_new_asset] ✅ Asset deployed successfully")
    print(f"  Name: {result.name}")
    print(f"  Version: {result.version}")
    
    github_output({
        "reference": f"azureml:{result.name}:{result.version}",
        "version": result.version,
        "resource-id": result.id
    })
```

### Adding a New Share Operation

Add a new command function in `share.py` following the same pattern as existing share operations.

## Design Benefits

- ✅ **Simplicity**: Clean CLI routing with typer
- ✅ **Modularity**: Each operation is isolated and testable
- ✅ **Maintainability**: Easy to read, understand, and extend
- ✅ **Consistency**: All operations follow the same pattern
- ✅ **Robustness**: Proper error handling and version management
- ✅ **Flexibility**: Works with both CI/CD and local development
- ✅ **Compliance**: Follows AI-CONTRACT.md guidelines

## Dependencies

- Python 3.12+
- azure-ai-ml >= 1.28.1
- azure-core >= 1.35.0
- azure-identity >= 1.23.1
- typer >= 0.16.0

See [pyproject.toml](./pyproject.toml) for complete dependency list.

## Documentation

- [EXAMPLES.md](./EXAMPLES.md) - Detailed usage examples and patterns
- [AI-CONTRACT.md](../AI-CONTRACT.md) - Development principles and guidelines

## License

See the [LICENSE](../LICENSE) file in the repository root.
