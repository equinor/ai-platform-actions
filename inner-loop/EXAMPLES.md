# Inner Loop Action - Usage Examples

## Command Structure

The action uses typer routing with the following structure:

```
main.py <verb> <subject> [options...]
```

Where:
- **verb**: `deploy` or `share`
- **subject**: `data`, `environment`, `component`, `model`, or `job` (deploy only)
- **options**: Command-specific options (use `--help` for details)

## Deploy Operations

All deploy operations are **fully implemented** and ready for use.

### Deploy Data Asset

```bash
python main.py deploy data \
  --subscription "$SUBSCRIPTION_ID" \
  --resource-group "$RESOURCE_GROUP" \
  --workspace-name "$WORKSPACE_NAME" \
  --filepath "./data/my-data.yaml" \
  --token "$TOKEN" \
  --expires-on "$EXPIRES_ON" \
  --tags "env=prod,team=ml"
```

**GitHub Action Usage:**
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

```bash
python main.py deploy environment \
  --subscription "$SUBSCRIPTION_ID" \
  --resource-group "$RESOURCE_GROUP" \
  --workspace-name "$WORKSPACE_NAME" \
  --filepath "./environments/my-env.yaml" \
  --token "$TOKEN" \
  --expires-on "$EXPIRES_ON" \
  --tags "version=1.0,env=prod"
```

**GitHub Action Usage:**
```yaml
- uses: ./inner-loop
  with:
    verb: deploy
    subject: environment
    subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
    resource-group: my-resource-group
    workspace-name: my-workspace
    filepath: ./environments/my-env.yaml
    tags: "version=1.0,env=prod"
```

### Deploy Component

```bash
python main.py deploy component \
  --subscription "$SUBSCRIPTION_ID" \
  --resource-group "$RESOURCE_GROUP" \
  --workspace-name "$WORKSPACE_NAME" \
  --filepath "./components/my-component.yaml" \
  --token "$TOKEN" \
  --expires-on "$EXPIRES_ON" \
  --tags "type=training,framework=pytorch"
```

**Features:**
- Automatically handles version management (increments to next integer version)
- Cleans multiline commands (removes backslashes and line breaks)
- Merges tags from YAML and command line

**GitHub Action Usage:**
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

### Deploy Job

```bash
python main.py deploy job \
  --subscription "$SUBSCRIPTION_ID" \
  --resource-group "$RESOURCE_GROUP" \
  --workspace-name "$WORKSPACE_NAME" \
  --filepath "./jobs/my-job.yaml" \
  --token "$TOKEN" \
  --expires-on "$EXPIRES_ON"
```

**GitHub Action Usage:**
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

## Share Operations

All share operations are **fully implemented** with stage promotion support.

### Share Data Asset

```bash
python main.py share data \
  --subscription "$SUBSCRIPTION_ID" \
  --resource-group "$RESOURCE_GROUP" \
  --workspace-name "$WORKSPACE_NAME" \
  --registry-name "$REGISTRY_NAME" \
  "my-data-asset" \
  --token "$TOKEN" \
  --expires-on "$EXPIRES_ON" \
  --tags "env=prod,team=ml" \
  --promote-stage "Production"
```

**GitHub Action Usage:**
```yaml
- uses: ./inner-loop
  with:
    verb: share
    subject: data
    subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
    resource-group: my-resource-group
    workspace-name: my-workspace
    registry-name: my-registry
    data-ref: my-data-asset
    tags: "env=prod,team=ml"
    promote-stage: "Production"
```

### Share Environment

```bash
python main.py share environment \
  --subscription "$SUBSCRIPTION_ID" \
  --resource-group "$RESOURCE_GROUP" \
  --workspace-name "$WORKSPACE_NAME" \
  --registry-name "$REGISTRY_NAME" \
  "my-environment" \
  --token "$TOKEN" \
  --expires-on "$EXPIRES_ON" \
  --tags "env=prod" \
  --promote-stage "Production"
```

**GitHub Action Usage:**
```yaml
- uses: ./inner-loop
  with:
    verb: share
    subject: environment
    subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
    resource-group: my-resource-group
    workspace-name: my-workspace
    registry-name: my-registry
    env-ref: my-environment
    tags: "env=prod"
    promote-stage: "Production"
```

### Share Component

```bash
python main.py share component \
  --subscription "$SUBSCRIPTION_ID" \
  --resource-group "$RESOURCE_GROUP" \
  --workspace-name "$WORKSPACE_NAME" \
  --registry-name "$REGISTRY_NAME" \
  "my-component" \
  --token "$TOKEN" \
  --expires-on "$EXPIRES_ON" \
  --tags "type=training" \
  --promote-stage "Production"
```

**Features:**
- Downloads component from workspace
- Replaces environment references with registry equivalents
- Automatically increments version in registry
- Supports stage promotion via tags

**GitHub Action Usage:**
```yaml
- uses: ./inner-loop
  with:
    verb: share
    subject: component
    subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
    resource-group: my-resource-group
    workspace-name: my-workspace
    registry-name: my-registry
    component-ref: my-component
    tags: "type=training"
    promote-stage: "Production"
```

### Share Model

```bash
python main.py share model \
  --subscription "$SUBSCRIPTION_ID" \
  --resource-group "$RESOURCE_GROUP" \
  --workspace-name "$WORKSPACE_NAME" \
  --registry-name "$REGISTRY_NAME" \
  "my-model" \
  --token "$TOKEN" \
  --expires-on "$EXPIRES_ON" \
  --tags "framework=pytorch" \
  --promote-stage "Production"
```

**GitHub Action Usage:**
```yaml
- uses: ./inner-loop
  with:
    verb: share
    subject: model
    subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
    resource-group: my-resource-group
    workspace-name: my-workspace
    registry-name: my-registry
    model-ref: my-model
    tags: "framework=pytorch"
    promote-stage: "Production"
```

## Authentication Methods

### Token-Based (GitHub Actions with Federated Credentials)

```yaml
- name: Azure Login
  uses: azure/login@v1
  with:
    client-id: ${{ secrets.AZURE_CLIENT_ID }}
    tenant-id: ${{ secrets.AZURE_TENANT_ID }}
    subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}

- uses: ./inner-loop
  with:
    verb: deploy
    subject: component
    tenant-id: ${{ secrets.AZURE_TENANT_ID }}
    subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
    client-id: ${{ secrets.AZURE_CLIENT_ID }}
    # ... other parameters
```

### DefaultAzureCredential (Local Development)

```bash
# Authenticate with Azure CLI first
az login

# Run commands without token/expires_on
python main.py deploy component \
  --subscription "$SUBSCRIPTION_ID" \
  --resource-group "$RESOURCE_GROUP" \
  --workspace-name "$WORKSPACE_NAME" \
  --filepath "./components/my-component.yaml"
```

### Storage Account Without Shared Key Access

Only needed when the workspace storage account has `allowSharedKeyAccess: false`.
The identity also needs the `Storage Blob Data Contributor` role on that account.

```yaml
- name: Get access tokens
  id: get-token
  shell: bash
  run: |
    TOKEN=$(az account get-access-token --query accessToken --output tsv)
    STORAGE_TOKEN=$(az account get-access-token --resource https://storage.azure.com --query accessToken --output tsv)
    EXPIRES_ON=$(az account get-access-token --query expires_on --output tsv)
    echo "::add-mask::$TOKEN"
    echo "::add-mask::$STORAGE_TOKEN"
    echo "token=$TOKEN" >> "$GITHUB_OUTPUT"
    echo "storage-token=$STORAGE_TOKEN" >> "$GITHUB_OUTPUT"
    echo "expires-on=$EXPIRES_ON" >> "$GITHUB_OUTPUT"

- uses: ./inner-loop
  with:
    verb: deploy
    subject: component
    token: ${{ steps.get-token.outputs.token }}
    expires-on: ${{ steps.get-token.outputs.expires-on }}
    storage-token: ${{ steps.get-token.outputs.storage-token }}
    # ... other parameters
```

## File Structure

```
inner-loop/
├── main.py              # Entry point with typer routing
├── deploy.py            # Deploy commands (fully implemented)
├── share.py             # Share commands (fully implemented)
├── getasset.py          # Helper functions for retrieving assets
├── util.py              # Utility functions (clients, tags, etc.)
├── action.yaml          # GitHub Action definition
├── Dockerfile           # Container definition
├── pyproject.toml       # Python dependencies
├── README.md            # Documentation
└── EXAMPLES.md          # This file
```

## Output Format

All operations return:
- **resource-id**: Full Azure resource ID
- **reference**: Azure ML reference string (e.g., `azureml:name:version`)
- **version**: Version number or job name

Example output:
```
[deploy component] ✅ Component deployed successfully
  Name: my-component
  Version: 5
  Resource ID: /subscriptions/.../components/my-component/versions/5
```

## Tags Format

Tags should be provided as comma-separated key=value pairs:
```
--tags "key1=value1,key2=value2,key3=value3"
```

- Non-ASCII characters are automatically removed
- Leading/trailing whitespace is trimmed
- Tags from YAML config and command line are merged

## Common Patterns

### Deploy and Share Pipeline

```yaml
- name: Deploy Component
  id: deploy
  uses: ./inner-loop
  with:
    verb: deploy
    subject: component
    subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
    resource-group: my-resource-group
    workspace-name: my-workspace
    filepath: ./components/my-component.yaml

- name: Share to Registry
  uses: ./inner-loop
  with:
    verb: share
    subject: component
    subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
    resource-group: my-resource-group
    workspace-name: my-workspace
    registry-name: my-registry
    component-ref: ${{ steps.deploy.outputs.reference }}
    promote-stage: "Production"
```
