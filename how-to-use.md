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
- Your workflow grants `id-token: write` permission so `azure/login` can use OpenID Connect.
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

permissions:
  id-token: write
  contents: read

jobs:
  detect-assets:
    runs-on: ubuntu-latest
    environment: dev
    outputs:
      assets: ${{ steps.changed.outputs.changed-files-json }}
      has-changes: ${{ steps.changed.outputs.has-changes }}
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Detect changed files
        id: changed
        uses: equinor/ai-platform-actions/changed-files@main
        with:
          filter-pattern: 'asset/**/*.yaml'
          output-format: json

  deploy-assets:
    needs: detect-assets
    if: needs.detect-assets.outputs.has-changes == 'true'
    runs-on: ubuntu-latest
    environment: dev
    strategy:
      fail-fast: false
      matrix:
        asset: ${{ fromJson(needs.detect-assets.outputs.assets) }}
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

      - name: Get access tokens
        id: get-token
        shell: bash
        run: |
          TOKEN=$(az account get-access-token --query accessToken --output tsv)
          AML_TOKEN=$(az account get-access-token --resource https://ml.azure.com --query accessToken --output tsv)
          EXPIRES_ON=$(az account get-access-token --query expires_on --output tsv)
          echo "::add-mask::$TOKEN"
          echo "::add-mask::$AML_TOKEN"
          echo "token=$TOKEN" >> "$GITHUB_OUTPUT"
          echo "aml-token=$AML_TOKEN" >> "$GITHUB_OUTPUT"
          echo "expires-on=$EXPIRES_ON" >> "$GITHUB_OUTPUT"

      - name: Deploy changed asset
        uses: equinor/ai-platform-actions/inner-loop@main
        with:
          token: ${{ steps.get-token.outputs.token }}
          aml-token: ${{ steps.get-token.outputs.aml-token }}
          expires-on: ${{ steps.get-token.outputs.expires-on }}
          verb: deploy
          subject: ${{ matrix.asset.subject }}
          filepath: ${{ matrix.asset.filepath }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
          resource-group: ${{ secrets.AZURE_RESOURCE_GROUP }}
          workspace-name: ${{ secrets.AZURE_ML_WORKSPACE_NAME }}
```

## How It Works

1. **Trigger**: The workflow runs on every push or pull request that changes any YAML file under the `asset/` folder.
2. **Detect Changed Files**: A first job checks out the repository and uses the `changed-files` action to find all changed asset YAML files.
3. **Create Deployment Matrix**: The detected assets are exposed as job outputs and converted into a matrix for parallel deployment.
4. **Azure Login**: Each deployment job authenticates to Azure using federated credentials or a service principal.
5. **Get Tokens**: Each deployment job fetches the ARM token, the Azure ML token, and the token expiry timestamp used by `inner-loop`.
6. **Deploy Assets**: The `inner-loop` action deploys each changed asset to the AzureML workspace using the detected `subject` and `filepath` values.

The `aml-token` input is only required for job operations, but it is safe to pass it for all subjects in a shared matrix workflow.

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
