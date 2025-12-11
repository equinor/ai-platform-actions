# How to Use: Example Inner-Loop CI/CD Workflow for AzureML Asset Deployment

This guide demonstrates how to use the public actions in this repository to create a simple, efficient CI/CD pipeline for deploying AzureML assets from a typical MLOps repository structure.

## Example Repository Structure

Suppose your repository is named `unified-structure` and has the following layout:

```
asset/
  components/
    my-component-1/
      component.yaml
    my-component-2/
      component.yaml
  data/
    my-data-1/
      data.yaml
  environments/
    my-env-1/
      environment.yaml
  jobs/
    my-job-1/
      job.yaml
```

## Prerequisites

- You have an AzureML workspace and the necessary permissions to deploy assets.
- You have set up federated credentials or a service principal for GitHub Actions to authenticate to Azure.
- You have configured the following secrets or variables in your repository or organization:
  - `AZURE_CLIENT_ID`
  - `AZURE_TENANT_ID`
  - `AZURE_SUBSCRIPTION_ID`
  - `AZURE_RESOURCE_GROUP`
  - `AZURE_ML_WORKSPACE_NAME`

## Example Workflow: `.github/workflows/aml-inner-loop.yml`

```yaml
name: AzureML Inner Loop CI/CD

on:
  push:
    paths:
      - 'asset/**'
  pull_request:
    paths:
      - 'asset/**'

jobs:
  deploy-assets:
    runs-on: ubuntu-latest
    environment: dev
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

      - name: Detect changed files
        id: changed
        uses: equinor/ai-platform-actions/changed-files@main
        with:
          filter-pattern: 'asset/**/*.yaml'
          output-format: json

      - name: Deploy Environments
        if: steps.changed.outputs.has-changes == 'true'
        uses: equinor/ai-platform-actions/deploy-x@main
        with:
          tenant-id: ${{ secrets.AZURE_TENANT_ID }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
          resource-group: ${{ secrets.AZURE_RESOURCE_GROUP }}
          workspace-name: ${{ secrets.AZURE_ML_WORKSPACE_NAME }}
          client-id: ${{ secrets.AZURE_CLIENT_ID }}
          config: ${{ steps.changed.outputs.changed-files-json }}
```

## How It Works

1. **Trigger**: The workflow runs on every push or pull request that changes any YAML file under the `asset/` folder.
2. **Checkout**: The repository is checked out.
3. **Azure Login**: Authenticates to Azure using federated credentials or a service principal.
4. **Detect Changed Files**: Uses the `changed-files` action to find all changed asset YAML files.
5. **Deploy Assets**: Uses the `deploy-x` action to deploy all changed assets to the AzureML workspace. The action will automatically route each asset to the correct deployment action based on its type.

## Customization

- You can add additional steps to deploy only specific asset types (e.g., only environments or only components) by filtering the changed files output.
- You can use matrix strategies for parallel deployment if needed.
- You can add test or validation steps before or after deployment.

## Best Practices

- Use branch protection and required status checks to ensure only valid assets are deployed.
- Use environments and approvals for production deployments.
- Keep your asset YAML files organized and use clear naming conventions.

---

For more advanced usage, see the documentation in each action's README or open an issue in this repository for help!
