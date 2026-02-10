---
name: create-inner-loops
description: Guide for creating and updating inner-loop workflows. Use this when asked to create or update an inner-loop workflow.
---

# Create inner-loop workflow

This skill helps you create and update inner-loop workflows.

## When to use this skill

Use this skill when you need to:
- Create new inner-loop workflows
- Update existing inner-loop workflows
- Set up a new ML project

## Preparation

Ensure that the github repository has setup a named environment with these variables:
- TENANT_ID
- SUBSCRIPTION_ID
- RESOURCE_GROUP
- AML_WORKSPACE
- REGISTRY
- CLIENT_ID

The CLIENT_ID should be the "Client ID" of the User Assigned Managed Identity that
has been setup with Federated Credentials toward this repository and to the named environment.
The UAMI is expected to have the Contributor on the resource group with the AML workspace,
or at least "AI Developer" on the AML workspace, and at least "Registry User" on the Registry.

## Asset Dependencies

ML assets should always be deployed accroding to their dependencies.
Do actions in this order: Deploy -> Waitfor -> Share.
- Checkout
- Azure Login
- Get Token
- Deploy data
- Deploy environment (might use several minutes)
- Deploy component
- Waitfor environment
- Deploy job (might use a lot of time)
- Waitfor job
- Deploy model (only for some usecases)
- Waitfor model (only for some usecases)
- Deploy online endpoint (might use a bit of time)
- Waitfor online endpoint
- Deploy online endpoint
- Waitfor online endpoint
- Share data (only for some usecases)
- Share environment
- Share component
- Share model

For a particular project, some assets types might not apply.
The user is expected to provide the required assets as input.
The share data action should only be done if the data is used as a fairly stable resource meant for reusing multiple times,
as sharing data to a registry causes a copy to be made each time. Also the data will only be usable within jobs or pipelines.
Job in this context can both be a commandJob (a single use invocation of a command or a component),
or a pipeline comprised of one or more components.
In some projects, jobs may register a model as part of running (deploying) them, 
while other projects may deploy models based on yaml definitions.
Note that it matters for an endpoint or deployment whether or not it is a managed online-endpoint or a kubernetes online-endpoint.
They use different schemas, and the content differs somewhat. The same goes for online-deployments.
Unlike other assets, for endpoints and deployments there is a delete action.
For the online-deployments, they are special in that they need a resource-id as input instead of a reference.
This is because they need both the endpoint-name and the deployment name, and these can both be extracted from the resource-id.

## Creating the inner-loop yaml

1. Review the [inner-loop-example](./inner-loop-example.yaml) as a simple workflow,
and the [inner-loop-endpoint](./inner-loop-endpoint.yaml) as a bit more complex one, for how to set up the differnt types of steps.
2. Create a new inner-loop-<name>.yaml file in the `.github/workflows/` directory
3. Verify that paths to the assets are correct, and use those paths in the paths field within "on:", as well as in their respective deploy steps
4. Use outputs of the deploy steps in the waitfor and share steps
5. Verify that the required environment variables exist, and that the environment is used in the workflow
