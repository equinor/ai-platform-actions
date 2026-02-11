"""
Deploy operations for Inner Loop Action
"""
from datetime import datetime

from azure.ai.ml import (
    load_data,
    load_environment,
    load_component,
    load_model,
    load_job,
    load_online_endpoint,
    load_online_deployment,
)
from azure.ai.ml.entities import (
    CommandComponent,
    Component,
    CronTrigger,
    Data,
    Environment,
    BuildContext,
    JobSchedule,
    Model,
    ManagedOnlineEndpoint,
    ManagedOnlineDeployment,
    KubernetesOnlineEndpoint,
    KubernetesOnlineDeployment,
)
from azure.core.polling import LROPoller
import typer
from typing import Annotated, Any, Optional
from .util import (
    get_workspace_client, 
    github_output, 
    load_safe_tags,
    empty_string_to_none,
    empty_string_to_none_int,
    load_online_endpoint_safe,
    load_online_deployment_safe,
)
import yaml
from pathlib import Path
from .getasset import (
    getcomponent,
    getdata,
    getenvironment,
    getmodel
)
import re

app = typer.Typer()

@app.command()
def data(
        subscription_id: Annotated[str, typer.Option("--subscription","-s")],
        resource_group: Annotated[str, typer.Option("--resource-group","-g")],
        workspace_name: Annotated[str, typer.Option("--workspace-name","-w")],
        filepath: str,
        token: Optional[str] = None,
        expires_on: Optional[int] = None,
        tags: Annotated[
            Optional[str],
            typer.Option(help="Tags in the config file to use", callback=load_safe_tags),
        ]=None,
        # The following 4 arguments are not used. They ar required to satisfy gihthub actions interface
        registry_name: Annotated[Optional[str], typer.Option("--registry-name", callback=empty_string_to_none)] = None,
        promote_stage: Annotated[Optional[str], typer.Option("--promote-stage", callback=empty_string_to_none)] = None,
        image_build_compute: Annotated[Optional[str], typer.Option("--image-build-compute", callback=empty_string_to_none)] = None,
        aml_token: Annotated[Optional[str], typer.Option("--aml-token", callback=empty_string_to_none)] = None,
        traffic_allocation: Annotated[Optional[str], typer.Option("--traffic-allocation", callback=empty_string_to_none)] = None,
        schedule_name: Annotated[Optional[str], typer.Option("--schedule-name")] = None,
        cron_expression: Annotated[Optional[str], typer.Option("--cron-expression")] = None,
        time_zone: Annotated[Optional[str], typer.Option("--time-zone", )] = None,
    ):
    """Deploy data asset to Azure ML workspace"""
    print(f"[deploy data] Deploying data asset")
    print(f"  Workspace: {workspace_name}")
    print(f"  Resource Group: {resource_group}")
    print(f"  Filepath: {filepath}")

    print("[deploy data] Creating workspace client")
    client = get_workspace_client(
        subscription_id=subscription_id,
        resource_group=resource_group,
        workspace_name=workspace_name,
        token=token,
        expires_on=expires_on
    )

    print("[deploy data] Loading data configuration from file")
    data_asset: Data = load_data(source=filepath)
    if tags:
        if data_asset.tags:
            data_asset.tags.update(tags)
        else:
            data_asset.tags = tags
    
    print("[deploy data] Creating or updating data asset")
    data_result = client.data.create_or_update(data_asset)

    print(f"[deploy data] ✅ Data asset deployed successfully")
    print(f"  Name: {data_result.name}")
    print(f"  Version: {data_result.version}")
    print(f"  Resource ID: {data_result.id}")
    github_output({
        "reference":f"azureml:{data_result.name}:{data_result.version}",
        "version":data_result.version,
        "resource-id":data_result.id
    })

@app.command()
def environment(
        subscription_id: Annotated[str, typer.Option("--subscription","-s")],
        resource_group: Annotated[str, typer.Option("--resource-group","-g")],
        workspace_name: Annotated[str, typer.Option("--workspace-name","-w")],
        filepath: str,
        token: Optional[str] = None,
        expires_on: Optional[int] = None,
        tags: Annotated[
            Optional[str],
            typer.Option(help="Tags in the config file to use", callback=load_safe_tags),
        ]=None,
        # The following 4 arguments are not used. They are required to satisfy gihthub actions interface
        registry_name: Annotated[Optional[str], typer.Option("--registry-name", callback=empty_string_to_none)] = None,
        promote_stage: Annotated[Optional[str], typer.Option("--promote-stage", callback=empty_string_to_none)] = None,
        image_build_compute: Annotated[Optional[str], typer.Option("--image-build-compute", callback=empty_string_to_none)] = None,
        aml_token: Annotated[Optional[str], typer.Option("--aml-token", callback=empty_string_to_none)] = None,
        traffic_allocation: Annotated[Optional[str], typer.Option("--traffic-allocation", callback=empty_string_to_none)] = None,
        schedule_name: Annotated[Optional[str], typer.Option("--schedule-name")] = None,
        cron_expression: Annotated[Optional[str], typer.Option("--cron-expression")] = None,
        time_zone: Annotated[Optional[str], typer.Option("--time-zone", )] = None,
    ):
    """Deploy environment to Azure ML workspace"""
    print(f"[deploy environment] Deploying environment")
    print(f"  Workspace: {workspace_name}")
    print(f"  Resource Group: {resource_group}")
    print(f"  Filepath: {filepath}")
    
    print("[deploy environment] Loading environment configuration from file")
    environment = load_environment(source=filepath)
    if tags:
        if environment.tags:
            environment.tags.update(tags)
        else:
            environment.tags = tags  
    
    print("[deploy environment] Creating workspace client")
    client = get_workspace_client(
        subscription_id=subscription_id,
        resource_group=resource_group,
        workspace_name=workspace_name,
        token=token,
        expires_on=expires_on
    )
   
    print("[deploy environment] Creating or updating environment")
    environment_result = client.environments.create_or_update(environment)
    
    print(f"[deploy environment] ✅ Environment deployed successfully")
    print(f"  Name: {environment_result.name}")
    print(f"  Version: {environment_result.version}")
    print(f"  Resource ID: {environment_result.id}")
    github_output({
        "reference":f"azureml:{environment_result.name}:{environment_result.version}",
        "version":environment_result.version,
        "resource-id":environment_result.id
    })


@app.command()
def component(
        subscription_id: Annotated[str, typer.Option("--subscription","-s")],
        resource_group: Annotated[str, typer.Option("--resource-group","-g")],
        workspace_name: Annotated[str, typer.Option("--workspace-name","-w")],
        filepath: str,
        token: Optional[str] = None,
        expires_on: Optional[int] = None,
        tags: Annotated[
            Optional[str],
            typer.Option(help="Tags in the config file to use", callback=load_safe_tags),
        ]=None,
        # The following 4 arguments are not used. They are required to satisfy gihthub actions interface
        registry_name: Annotated[Optional[str], typer.Option("--registry-name", callback=empty_string_to_none)] = None,
        promote_stage: Annotated[Optional[str], typer.Option("--promote-stage", callback=empty_string_to_none)] = None,
        image_build_compute: Annotated[Optional[str], typer.Option("--image-build-compute", callback=empty_string_to_none)] = None,
        aml_token: Annotated[Optional[str], typer.Option("--aml-token", callback=empty_string_to_none)] = None,
        traffic_allocation: Annotated[Optional[str], typer.Option("--traffic-allocation", callback=empty_string_to_none)] = None,
        schedule_name: Annotated[Optional[str], typer.Option("--schedule-name")] = None,
        cron_expression: Annotated[Optional[str], typer.Option("--cron-expression")] = None,
        time_zone: Annotated[Optional[str], typer.Option("--time-zone", )] = None,
    ):
    """Deploy component to Azure ML workspace"""
    print(f"[deploy component] Deploying component")
    print(f"  Workspace: {workspace_name}")
    print(f"  Resource Group: {resource_group}")
    print(f"  Filepath: {filepath}")
    
    print("[deploy component] Loading component configuration from file")
    component = load_component(source=filepath)
    if tags:
        if component.tags:
            component.tags.update(tags)
        else:
            component.tags = tags

    cmd = component.command
    cmd = re.sub(r'\s*[\\]+\s*',' ', cmd)
    cmd = re.sub(r'\s*[\n]\s*', ' ', cmd)
    cmd = re.sub(r'\s+', ' ', cmd)
    cmd = cmd.strip()
    component.command = cmd

    print("[deploy component] Creating workspace client")
    client = get_workspace_client(
        subscription_id=subscription_id,
        resource_group=resource_group,
        workspace_name=workspace_name,
        token=token,
        expires_on=expires_on
    )

    # Due to components being deployed has a "non-standard" version by default,
    # we need to get any existing ones, and update the version ourselves
    list_comp_ws = getcomponent(
        client=client,
        name=component.name
    )

    latest_ws_version=0
    if list_comp_ws:
        for c in list_comp_ws:
            try:
                lrv = int(c.version)
                if lrv>latest_ws_version:
                    latest_ws_version=lrv
            except:
                pass # Ignore non-int versions
    latest_ws_version=str(latest_ws_version+1)

    env_in_component = component.environment

    component.version = latest_ws_version
    component_result = client.components.create_or_update(
        component=component,
        version=latest_ws_version
    )
    
    print(f"[deploy component] ✅ Component deployed successfully")
    print(f"  Name: {component_result.name}")
    print(f"  Version: {component_result.version}")
    print(f"  Resource ID: {component_result.id}")
    github_output({
       "reference":f"azureml:{component_result.name}:{component_result.version}",
       "version":component_result.version,
       "resource-id":component_result.id
    })

@app.command()
def model(
        subscription_id: Annotated[str, typer.Option("--subscription","-s")],
        resource_group: Annotated[str, typer.Option("--resource-group","-g")],
        workspace_name: Annotated[str, typer.Option("--workspace-name","-w")],
        filepath: str,
        token: Optional[str] = None,
        expires_on: Optional[int] = None,
        tags: Annotated[
            Optional[str],
            typer.Option(help="Tags in the config file to use", callback=load_safe_tags),
        ]=None,
        # The following 4 arguments are not used. They are required to satisfy gihthub actions interface
        registry_name: Annotated[Optional[str], typer.Option("--registry-name", callback=empty_string_to_none)] = None,
        promote_stage: Annotated[Optional[str], typer.Option("--promote-stage", callback=empty_string_to_none)] = None,
        image_build_compute: Annotated[Optional[str], typer.Option("--image-build-compute", callback=empty_string_to_none)] = None,
        aml_token: Annotated[Optional[str], typer.Option("--aml-token", callback=empty_string_to_none)] = None,
        traffic_allocation: Annotated[Optional[str], typer.Option("--traffic-allocation", callback=empty_string_to_none)] = None,
        schedule_name: Annotated[Optional[str], typer.Option("--schedule-name")] = None,
        cron_expression: Annotated[Optional[str], typer.Option("--cron-expression")] = None,
        time_zone: Annotated[Optional[str], typer.Option("--time-zone", )] = None,
    ):
    """Deploy model to Azure ML workspace"""
    print(f"[deploy model] Deploying model")
    print(f"  Workspace: {workspace_name}")
    print(f"  Resource Group: {resource_group}")
    print(f"  Filepath: {filepath}")

    print("[deploy model] Creating workspace client")
    client = get_workspace_client(
        subscription_id=subscription_id,
        resource_group=resource_group,
        workspace_name=workspace_name,
        token=token,
        expires_on=expires_on
    )

    print("[deploy model] Loading model configuration from file")
    model = load_model(source=filepath)
    if tags:
        if model.tags:
            model.tags.update(tags)
        else:
            model.tags = tags

    print("[deploy model] Creating or updating model")
    model_result = client.models.create_or_update(model)

    print(f"[deploy model] ✅ Model deployed successfully")
    print(f"  Name: {model_result.name}")
    print(f"  Version: {model_result.version}")
    print(f"  Resource ID: {model_result.id}")
    github_output({
        "reference":f"azureml:{model_result.name}:{model_result.version}",
        "version":model_result.version,
        "resource-id":model_result.id
    })

@app.command()
def job(
        subscription_id: Annotated[str, typer.Option("--subscription","-s")],
        resource_group: Annotated[str, typer.Option("--resource-group","-g")],
        workspace_name: Annotated[str, typer.Option("--workspace-name","-w")],
        filepath: str,
        token: Optional[str] = None,
        expires_on: Optional[int] = None,
        aml_token: Annotated[Optional[str], typer.Option("--aml-token", callback=empty_string_to_none)] = None,
        tags: Annotated[
            Optional[str],
            typer.Option(help="Tags in the config file to use", callback=load_safe_tags),
        ]=None,
        # The following 3 arguments are not used. They are required to satisfy gihthub actions interface
        registry_name: Annotated[Optional[str], typer.Option("--registry-name", callback=empty_string_to_none)] = None,
        promote_stage: Annotated[Optional[str], typer.Option("--promote-stage", callback=empty_string_to_none)] = None,
        image_build_compute: Annotated[Optional[str], typer.Option("--image-build-compute", callback=empty_string_to_none)] = None,
        traffic_allocation: Annotated[Optional[str], typer.Option("--traffic-allocation", callback=empty_string_to_none)] = None,
        schedule_name: Annotated[Optional[str], typer.Option("--schedule-name")] = None,
        cron_expression: Annotated[Optional[str], typer.Option("--cron-expression")] = None,
        time_zone: Annotated[Optional[str], typer.Option("--time-zone", )] = None,
    ):
    """Submit job to Azure ML workspace.
    https://learn.microsoft.com/en-us/azure/machine-learning/reference-yaml-job-pipeline?view=azureml-api-2
    https://learn.microsoft.com/en-us/azure/machine-learning/reference-yaml-job-command?view=azureml-api-2
    https://learn.microsoft.com/en-us/azure/machine-learning/reference-yaml-job-sweep?view=azureml-api-2
    https://learn.microsoft.com/en-us/azure/machine-learning/reference-yaml-job-parallel?view=azureml-api-2
    """
    print(f"[deploy job] Submitting job")
    print(f"  Workspace: {workspace_name}")
    print(f"  Resource Group: {resource_group}")
    print(f"  Filepath: {filepath}")
    
    print("[deploy job] Creating workspace client")
    client = get_workspace_client(
        subscription_id=subscription_id,
        resource_group=resource_group,
        workspace_name=workspace_name,
        token=token,
        expires_on=expires_on,
        aml_token=aml_token
    )

    print("[deploy job] Loading job configuration from file")
    #with open(filepath, "r") as file:
    #    job_config = yaml.safe_load(file)
    job_config = load_job(source=filepath)
    if tags:
        if job_config.tags:
            job_config.tags.update(tags)
        else:
            job_config.tags = tags
    
    print("[deploy job] Submitting job to workspace")
    job_result = client.jobs.create_or_update(job_config)
    
    print(f"[deploy job] ✅ Job submitted successfully")
    print(f"  Name: {job_result.name}")
    print(f"  Status: {job_result.status}")
    print(f"  Resource ID: {job_result.id}")
    github_output({
        "reference":f"azureml:{job_result.name}",
        "version":job_result.name,
        "resource-id":job_result.id
    })


@app.command()
def online_endpoint(
        subscription_id: Annotated[str, typer.Option("--subscription", "-s")],
        resource_group: Annotated[str, typer.Option("--resource-group", "-g")],
        workspace_name: Annotated[str, typer.Option("--workspace-name", "-w")],
        filepath: str,
        token: Optional[str] = None,
        expires_on: Optional[int] = None,
        tags: Annotated[
            Optional[str],
            typer.Option(help="Tags in the config file to use", callback=load_safe_tags),
        ] = None,
        registry_name: Annotated[Optional[str], typer.Option("--registry-name", callback=empty_string_to_none)] = None,
        promote_stage: Annotated[Optional[str], typer.Option("--promote-stage", callback=empty_string_to_none)] = None,
        image_build_compute: Annotated[Optional[str], typer.Option("--image-build-compute", callback=empty_string_to_none)] = None,
        aml_token: Annotated[Optional[str], typer.Option("--aml-token", callback=empty_string_to_none)] = None,
        traffic_allocation: Annotated[Optional[str], typer.Option("--traffic-allocation", callback=empty_string_to_none)] = None,
        schedule_name: Annotated[Optional[str], typer.Option("--schedule-name")] = None,
        cron_expression: Annotated[Optional[str], typer.Option("--cron-expression")] = None,
        time_zone: Annotated[Optional[str], typer.Option("--time-zone", )] = None,
    ):
    """Deploy online endpoint to Azure ML workspace.
    https://learn.microsoft.com/en-us/azure/machine-learning/reference-yaml-endpoint-online?view=azureml-api-2
    """
    print(f"[deploy online-endpoint] Deploying online endpoint")
    print(f"  Workspace: {workspace_name}")
    print(f"  Resource Group: {resource_group}")
    print(f"  Filepath: {filepath}")

    print("[deploy online-endpoint] Creating workspace client")
    client = get_workspace_client(
        subscription_id=subscription_id,
        resource_group=resource_group,
        workspace_name=workspace_name,
        token=token,
        expires_on=expires_on,
    )

    print("[deploy online-endpoint] Loading endpoint configuration from file")
    endpoint = load_online_endpoint_safe(source=filepath)
    is_kubernetes = isinstance(endpoint, KubernetesOnlineEndpoint)

    if is_kubernetes:
        print("  Type: KubernetesOnlineEndpoint")
        if not hasattr(endpoint, 'compute') or not endpoint.compute:
            raise typer.BadParameter("KubernetesOnlineEndpoint YAML must contain a 'compute' field")
        
        print(f"[deploy online-endpoint] Validating compute '{endpoint.compute}'")
        available_k8s_computes = [c.name for c in client.compute.list(compute_type="Kubernetes")]
        if endpoint.compute not in available_k8s_computes:
            raise typer.BadParameter(
                f"Compute '{endpoint.compute}' not found in available Kubernetes computes: {available_k8s_computes}"
            )
        print(f"  ✅ Compute '{endpoint.compute}' validated")
    else:
        print("  Type: ManagedOnlineEndpoint")

    if tags:
        if endpoint.tags:
            endpoint.tags.update(tags)
        else:
            endpoint.tags = tags

    print("[deploy online-endpoint] Creating or updating online endpoint")
    poller = client.online_endpoints.begin_create_or_update(endpoint)
    endpoint_result = poller.result()

    print(f"[deploy online-endpoint] ✅ Online endpoint deployed successfully")
    print(f"  Name: {endpoint_result.name}")
    print(f"  Provisioning State: {endpoint_result.provisioning_state}")
    print(f"  Scoring URI: {endpoint_result.scoring_uri}")
    print(f"  Resource ID: {endpoint_result.id}")
    github_output({
        "reference": f"azureml:{endpoint_result.name}",
        "version": endpoint_result.name,
        "resource-id": endpoint_result.id,
    })


@app.command()
def online_deployment(
        subscription_id: Annotated[str, typer.Option("--subscription", "-s")],
        resource_group: Annotated[str, typer.Option("--resource-group", "-g")],
        workspace_name: Annotated[str, typer.Option("--workspace-name", "-w")],
        filepath: str,
        traffic_allocation: Annotated[
            Optional[int],
            typer.Option("--traffic-allocation", "-t", help="Traffic percentage to allocate to this deployment (0-100)")
        ] = None,
        token: Optional[str] = None,
        expires_on: Optional[int] = None,
        tags: Annotated[
            Optional[str],
            typer.Option(help="Tags in the config file to use", callback=load_safe_tags),
        ] = None,
        registry_name: Annotated[Optional[str], typer.Option("--registry-name", callback=empty_string_to_none)] = None,
        promote_stage: Annotated[Optional[str], typer.Option("--promote-stage", callback=empty_string_to_none)] = None,
        image_build_compute: Annotated[Optional[str], typer.Option("--image-build-compute", callback=empty_string_to_none)] = None,
        aml_token: Annotated[Optional[str], typer.Option("--aml-token", callback=empty_string_to_none)] = None,
        schedule_name: Annotated[Optional[str], typer.Option("--schedule-name")] = None,
        cron_expression: Annotated[Optional[str], typer.Option("--cron-expression")] = None,
        time_zone: Annotated[Optional[str], typer.Option("--time-zone", )] = None,
    ):
    """Deploy online deployment to Azure ML workspace.
    https://learn.microsoft.com/en-us/azure/machine-learning/reference-yaml-deployment-managed-online?view=azureml-api-2
    """
    print("[deploy online-deployment] Loading deployment configuration from file")
    deployment = load_online_deployment_safe(source=filepath)
    endpoint_name = deployment.endpoint_name
    if not endpoint_name:
        raise typer.BadParameter("Deployment YAML must contain 'endpoint_name' field")

    is_kubernetes = isinstance(deployment, KubernetesOnlineDeployment)

    print(f"[deploy online-deployment] Deploying online deployment")
    print(f"  Workspace: {workspace_name}")
    print(f"  Resource Group: {resource_group}")
    print(f"  Endpoint: {endpoint_name}")
    print(f"  Deployment: {deployment.name}")
    print(f"  Filepath: {filepath}")
    print(f"  Type: {'KubernetesOnlineDeployment' if is_kubernetes else 'ManagedOnlineDeployment'}")
    if traffic_allocation is not None:
        print(f"  Traffic Allocation: {traffic_allocation}%")

    print("[deploy online-deployment] Creating workspace client")
    client = get_workspace_client(
        subscription_id=subscription_id,
        resource_group=resource_group,
        workspace_name=workspace_name,
        token=token,
        expires_on=expires_on,
    )

    if is_kubernetes:
        print(f"[deploy online-deployment] Validating Kubernetes deployment configuration")
        if not hasattr(deployment, 'resources') or not deployment.resources:
            raise typer.BadParameter(
                "KubernetesOnlineDeployment YAML must contain a 'resources' field with 'requests' and 'limits'"
            )
        resources = deployment.resources
        if not hasattr(resources, 'requests') or not resources.requests:
            raise typer.BadParameter("KubernetesOnlineDeployment 'resources' must contain 'requests'")
        if not hasattr(resources, 'limits') or not resources.limits:
            raise typer.BadParameter("KubernetesOnlineDeployment 'resources' must contain 'limits'")
        
        for section_name, section in [('requests', resources.requests), ('limits', resources.limits)]:
            if not hasattr(section, 'cpu') or not section.cpu:
                raise typer.BadParameter(f"KubernetesOnlineDeployment 'resources.{section_name}' must contain 'cpu'")
            if not hasattr(section, 'memory') or not section.memory:
                raise typer.BadParameter(f"KubernetesOnlineDeployment 'resources.{section_name}' must contain 'memory'")
        print(f"  ✅ Resources validated")

        print(f"[deploy online-deployment] Validating endpoint type for Kubernetes deployment")
        endpoint = client.online_endpoints.get(name=endpoint_name)
        if not isinstance(endpoint, KubernetesOnlineEndpoint):
            raise typer.BadParameter(
                f"KubernetesOnlineDeployment requires a KubernetesOnlineEndpoint, but endpoint '{endpoint_name}' is not a Kubernetes endpoint"
            )
        print(f"  ✅ Endpoint '{endpoint_name}' is a Kubernetes endpoint")

    if traffic_allocation is not None and (traffic_allocation < 0 or traffic_allocation > 100):
        raise typer.BadParameter(f"Traffic allocation must be between 0 and 100, got {traffic_allocation}")

    if tags:
        if deployment.tags:
            deployment.tags.update(tags)
        else:
            deployment.tags = tags

    print("[deploy online-deployment] Creating or updating online deployment")
    poller = client.online_deployments.begin_create_or_update(deployment)
    deployment_result = poller.result()

    if traffic_allocation is not None:
        endpoint = client.online_endpoints.get(name=endpoint_name)
        existing_deployments = list(client.online_deployments.list(endpoint_name=endpoint_name))
        other_deployments = [d for d in existing_deployments if d.name != deployment_result.name]

        if other_deployments:
            print(f"[deploy online-deployment] Updating endpoint traffic allocation")
            remainder = 100 - traffic_allocation
            current_traffic = endpoint.traffic or {}
            other_total = sum(current_traffic.get(d.name, 0) for d in other_deployments)

            new_traffic = {deployment_result.name: traffic_allocation}
            if other_total > 0:
                for d in other_deployments:
                    old_share = current_traffic.get(d.name, 0)
                    new_traffic[d.name] = round(old_share * remainder / other_total)
            else:
                share_per_deployment = remainder // len(other_deployments)
                leftover = remainder - share_per_deployment * len(other_deployments)
                for i, d in enumerate(other_deployments):
                    new_traffic[d.name] = share_per_deployment + (1 if i < leftover else 0)

            endpoint.traffic = new_traffic
            poller = client.online_endpoints.begin_create_or_update(endpoint)
            poller.result()
            print(f"  Traffic updated: {endpoint.traffic}")

    print(f"[deploy online-deployment] ✅ Online deployment deployed successfully")
    print(f"  Name: {deployment_result.name}")
    print(f"  Endpoint: {deployment_result.endpoint_name}")
    print(f"  Provisioning State: {deployment_result.provisioning_state}")
    print(f"  Resource ID: {deployment_result.id}")
    github_output({
        "reference": f"azureml:{endpoint_name}/deployments/{deployment_result.name}",
        "version": deployment_result.name,
        "resource-id": deployment_result.id,
    })



@app.command()
def schedule(
        subscription_id: Annotated[str, typer.Option("--subscription", "-s")],
        resource_group: Annotated[str, typer.Option("--resource-group", "-g")],
        workspace_name: Annotated[str, typer.Option("--workspace-name", "-w")],
        job_name: str,
        schedule_name: Annotated[Optional[str], typer.Option("--schedule-name")],
        cron_expression: Annotated[Optional[str], typer.Option("--cron-expression")],
        time_zone: Annotated[Optional[str], typer.Option("--time-zone", )] = "UTC",
        token: Optional[str] = None,
        expires_on: Optional[int] = None,
        registry_name: Annotated[Optional[str], typer.Option("--registry-name", callback=empty_string_to_none)] = None,
        promote_stage: Annotated[Optional[str], typer.Option("--promote-stage", callback=empty_string_to_none)] = None,
        image_build_compute: Annotated[Optional[str], typer.Option("--image-build-compute", callback=empty_string_to_none)] = None,
        aml_token: Annotated[Optional[str], typer.Option("--aml-token", callback=empty_string_to_none)] = None,
        traffic_allocation: Annotated[Optional[str], typer.Option("--traffic-allocation", callback=empty_string_to_none)] = None,
        tags: Annotated[
            Optional[str],
            typer.Option(help="Tags in the config file to use", callback=load_safe_tags),
        ] = None,
):
    print(f"[deploy schedule] Deploying Schedule")
    print(f"  Workspace: {workspace_name}")
    print(f"  Resource Group: {resource_group}")
    print(f"  Job Reference: {job_name}")
    print(f"  Schedule Name: {schedule_name}")
    print(f"  CRON Expression: {cron_expression}")
    print(f"  Time Zone: {time_zone}")

    print("[deploy schedule] Creating workspace client")
    client = get_workspace_client(
        subscription_id=subscription_id,
        resource_group=resource_group,
        workspace_name=workspace_name,
        token=token,
        expires_on=expires_on,
    )

    print("[deploy schedule] Instantiating Schedule")

    cron_trigger = CronTrigger(
        expression=cron_expression,
        start_time=datetime.now(),
        time_zone=time_zone,
    )

    job_schedule = JobSchedule(
        name=schedule_name, trigger=cron_trigger, create_job=job_name
    )
    
    print("[deploy schedule] Submitting Schedule")

    result = client.schedules.begin_create_or_update(job_schedule).result()

    print(f"[deploy schedule] ✅ Schedule deployed successfully")
    print(f"  Name: {result.name}")
    print(f"  Resource ID: {result.id}")
    github_output({
        "reference": "",
        "version": result.name,
        "resource-id": result.id,
    })

if __name__ == "__main__":
    app()
