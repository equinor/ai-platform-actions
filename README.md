# Reusable Actions Repository

Welcome to the ai-platform-actions repository! It contains a collection of reusable GitHub Actions that can be utilized in MLOps workflows.

## Prerequisites

### Azure Authentication

**Important:** All actions in this repository require Azure authentication to be configured before use. You must include the Azure login step in your workflow before calling any of these actions.

Add this step to your workflow:

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

This authentication step only needs to be called once per workflow job, even when using multiple actions from this repository.

## How to use

This repository provides a set of reusable GitHub Actions for Azure Machine Learning workflows. The actions are designed to work together to provide a complete MLOps solution.

### Quick Start

The most common pattern is to use the `changed-files` action to detect changes and then deploy affected assets using a matrix strategy with the `deploy-x` action.

```yaml
jobs:
  detect-changes:
    runs-on: ubuntu-latest
    outputs:
      changed-files: ${{ steps.changed-files.outputs.changed-files-json }}
      has-changes: ${{ steps.changed-files.outputs.has-changes }}
    steps:
      - uses: equinor/ai-platform-actions/changed-files@main
        id: changed-files

  deploy-assets:
    if: ${{ needs.detect-changes.outputs.has-changes == 'true' }}
    needs: detect-changes
    runs-on: ubuntu-latest
    strategy:
      matrix:
        asset: ${{ fromJson(needs.detect-changes.outputs.changed-files) }}
    steps:
      - name: Azure Login
        uses: azure/login@v2
        with:
          client-id: ${{ secrets.AZURE_CLIENT_ID }}
          tenant-id: ${{ secrets.AZURE_TENANT_ID }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
          enable-AzPSSession: true
          auth-type: SERVICE_PRINCIPAL

      - uses: equinor/ai-platform-actions/deploy-x@main
        with:
          tenant-id: ${{ secrets.AZURE_TENANT_ID }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
          resource-group: ${{ secrets.AZURE_RESOURCE_GROUP }}
          workspace-name: ${{ secrets.AZURE_ML_WORKSPACE_NAME }}
          client-id: ${{ secrets.AZURE_CLIENT_ID }}
          asset-type: ${{ matrix.asset.asset-type }}
          asset-path: ${{ matrix.asset.asset-path }}
```

### Actions Overview

#### changed-files
Detects changes to Azure ML assets by monitoring YAML definition files and their related source files (Python, Dockerfiles, etc.). Outputs a JSON array compatible with matrix strategies.

#### deploy-x
Universal deployment action that dispatches to specific asset deployment actions based on asset type. Designed to work with matrix strategies for parallel deployment.

#### deploy-environment
Deploys Azure ML environments from YAML definitions.

#### deploy-component
Deploys Azure ML components from YAML definitions.

#### deploy-data
Deploys Azure ML data assets from YAML definitions.

#### deploy-job
Submits Azure ML jobs from YAML definitions.

#### share-environment
Shares Azure ML environments from a workspace to a registry, with optional tagging support.

#### share-data
Shares Azure ML data assets from a workspace to a registry, with optional tagging support.

#### share-component
Shares Azure ML components from a workspace to a registry, with optional tagging support.

### Matrix Strategy Pattern

The recommended approach is to use the `changed-files` action output with a matrix strategy to deploy multiple assets in parallel:

#### Step 1: Detect Changes

```yaml
jobs:
  detect-changes:
    runs-on: ubuntu-latest
    outputs:
      changed-files: ${{ steps.changed-files.outputs.changed-files-json }}
      has-changes: ${{ steps.changed-files.outputs.has-changes }}
    steps:
      - uses: equinor/ai-platform-actions/changed-files@main
        id: changed-files
        with:
          # Optional: filter only specific patterns
          filter-pattern: "environments/**/*.yaml"
          # Optional: ignore test files
          ignore-pattern: "test/**"
```

#### Step 2: Deploy Using Matrix Strategy

```yaml
  deploy-assets:
    if: ${{ needs.detect-changes.outputs.has-changes == 'true' }}
    needs: detect-changes
    runs-on: ubuntu-latest
    strategy:
      matrix:
        asset: ${{ fromJson(needs.detect-changes.outputs.changed-files) }}
      # Optional: limit parallel jobs
      max-parallel: 5
      # Optional: continue on failure for some assets
      fail-fast: false
    steps:
      - name: Azure Login
        uses: azure/login@v2
        with:
          client-id: ${{ secrets.AZURE_CLIENT_ID }}
          tenant-id: ${{ secrets.AZURE_TENANT_ID }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
          enable-AzPSSession: true
          auth-type: SERVICE_PRINCIPAL

      - uses: equinor/ai-platform-actions/deploy-x@main
        with:
          tenant-id: ${{ secrets.AZURE_TENANT_ID }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
          resource-group: ${{ secrets.AZURE_RESOURCE_GROUP }}
          workspace-name: ${{ secrets.AZURE_ML_WORKSPACE_NAME }}
          client-id: ${{ secrets.AZURE_CLIENT_ID }}
          asset-type: ${{ matrix.asset.asset-type }}
          asset-path: ${{ matrix.asset.asset-path }}
          # Optional parameters for specific asset types
          type: ${{ matrix.asset.type }}        # For data assets
          compute: ${{ matrix.asset.compute }}  # For job assets
```

### Advanced Configuration

#### Environment Variables for Default Values

**Note**: As of the latest version, all Azure credentials are required as direct inputs. The deploy-x action no longer supports environment variable fallbacks for clearer, more explicit configuration.

```yaml
jobs:
  deploy:
    steps:
      - uses: equinor/ai-platform-actions/deploy-x@main
        with:
          tenant-id: ${{ secrets.AZURE_TENANT_ID }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
          resource-group: ${{ secrets.AZURE_RESOURCE_GROUP }}
          workspace-name: ${{ secrets.AZURE_ML_WORKSPACE_NAME }}
          client-id: ${{ secrets.AZURE_CLIENT_ID }}
          asset-type: environment
          asset-path: environments/training/environment.yaml
```

#### Conditional Deployment by Asset Type

You can use conditions to deploy only specific asset types:

```yaml
  deploy-environments-only:
    if: ${{ needs.detect-changes.outputs.has-changes == 'true' }}
    needs: detect-changes
    runs-on: ubuntu-latest
    strategy:
      matrix:
        asset: ${{ fromJson(needs.detect-changes.outputs.changed-files) }}
    steps:
      - name: Deploy Environment
        if: ${{ matrix.asset.asset-type == 'environment' }}
        uses: equinor/ai-platform-actions/deploy-x@main
        with:
          tenant-id: ${{ secrets.AZURE_TENANT_ID }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
          resource-group: ${{ secrets.AZURE_RESOURCE_GROUP }}
          workspace-name: ${{ secrets.AZURE_ML_WORKSPACE_NAME }}
          client-id: ${{ secrets.AZURE_CLIENT_ID }}
          asset-type: ${{ matrix.asset.asset-type }}
          asset-path: ${{ matrix.asset.asset-path }}
```

#### Complete Example Workflow

```yaml
name: Deploy Changed Assets

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  detect-changes:
    runs-on: ubuntu-latest
    outputs:
      changed-files: ${{ steps.changed-files.outputs.changed-files-json }}
      has-changes: ${{ steps.changed-files.outputs.has-changes }}
    steps:
      - uses: equinor/ai-platform-actions/changed-files@main
        id: changed-files
        with:
          filter-pattern: "assets/**/*.yaml"
          ignore-pattern: "test/**"

  deploy-assets:
    if: ${{ needs.detect-changes.outputs.has-changes == 'true' }}
    needs: detect-changes
    runs-on: ubuntu-latest
    strategy:
      matrix:
        asset: ${{ fromJson(needs.detect-changes.outputs.changed-files) }}
      max-parallel: 3
      fail-fast: false
    steps:
      - name: Azure Login
        uses: azure/login@v2
        with:
          client-id: ${{ secrets.AZURE_CLIENT_ID }}
          tenant-id: ${{ secrets.AZURE_TENANT_ID }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
          enable-AzPSSession: true
          auth-type: SERVICE_PRINCIPAL

      - uses: equinor/ai-platform-actions/deploy-x@main
        id: deploy
        with:
          tenant-id: ${{ secrets.AZURE_TENANT_ID }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
          resource-group: ${{ secrets.AZURE_RESOURCE_GROUP }}
          workspace-name: ${{ secrets.AZURE_ML_WORKSPACE_NAME }}
          client-id: ${{ secrets.AZURE_CLIENT_ID }}
          asset-type: ${{ matrix.asset.asset-type }}
          asset-path: ${{ matrix.asset.asset-path }}

      - name: Output deployment results
        run: |
          echo "Deployed: ${{ matrix.asset.asset-type }} at ${{ matrix.asset.asset-path }}"
          echo "Resource ID: ${{ steps.deploy.outputs.resource-id }}"
          echo "Asset Reference: ${{ steps.deploy.outputs.asset-ref }}"
```

### Output Format from changed-files

The `changed-files` action outputs a JSON array where each object contains:
- `asset-type`: The type of Azure ML asset (environment, component, data, job)
- `asset-path`: The path to the asset definition YAML file

Example output:
```json
[
  {
    "asset-type": "environment",
    "asset-path": "environments/training/environment.yaml"
  },
  {
    "asset-type": "component", 
    "asset-path": "components/preprocessing/component.yaml"
  }
]
```

This format is specifically designed to work seamlessly with GitHub Actions matrix strategies using `fromJson()`.

foo

### Branching Strategy

To maintain a clean and organized codebase, we follow a specific branching strategy. Below are the details of our branching rules:

#### 1. Main Branch
- **Branch Name:** `main`
- **Purpose:** This is the stable branch containing the latest production-ready code. All releases are tagged from this branch.
- **Protection Rules:**
  - Pull request reviews are required before merging.
  - Status checks (e.g., CI/CD tests) must pass before merging.
  - Direct pushes to this branch are restricted to admins only.

#### 2. Development Branch
- **Branch Name:** `develop`
- **Purpose:** This branch serves as an integration branch for features. All completed features are merged here before being promoted to `main`.
- **Protection Rules:**
  - Pull request reviews are required before merging.
  - CI/CD checks must pass to ensure stability.

#### 3. Feature Branches
- **Branch Naming Convention:** `feature/<feature-name>`
- **Purpose:** Each new feature or enhancement should be developed in its own branch off of `develop`.
- **Lifecycle:**
  - Create a new feature branch from `develop`.
  - Work on the feature and commit changes.
  - Once completed, create a pull request to merge back into `develop`.

#### 4. Bugfix Branches
- **Branch Naming Convention:** `bugfix/<bug-description>`
- **Purpose:** Similar to feature branches, but specifically for bug fixes.
- **Lifecycle:**
  - Create a new bugfix branch from `develop`.
  - Work on the bug fix and commit changes.
  - Once completed, create a pull request to merge back into `develop`.

#### 5. Release Branches
- **Branch Naming Convention:** `release/<version-number>`
- **Purpose:** When preparing for a new release, create a release branch from `develop`. This branch is for finalizing the release (e.g., documentation, versioning).
- **Lifecycle:**
  - Create a new release branch from `develop`.
  - Make any final changes or fixes.
  - Merge back into `main` and `develop` after the release is complete.

#### 6. Hotfix Branches
- **Branch Naming Convention:** `hotfix/<issue-description>`
- **Purpose:** For urgent fixes that need to be applied to the production code immediately.
- **Lifecycle:**
  - Create a hotfix branch from `main`.
  - Implement the fix and commit changes.
  - Merge back into both `main` and `develop` to ensure the fix is included in future releases.

### Additional Guidelines

- **Commit Messages:** Please use meaningful commit messages that describe the changes made.
- **Pull Requests:** Always use pull requests for merges to facilitate code review and discussion.
- **Documentation:** Keep the README and other documentation updated to reflect our branching strategy and guidelines.
- **Versioning:** We follow semantic versioning (e.g., v1.0.0) for releases to help users understand the impact of changes.

## Contributing

We welcome contributions! Please read our [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on how to contribute to this repository.

Thank you for being a part of our community!
