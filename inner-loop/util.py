"""
Utility functions for Inner Loop Action
"""

import os
import re
from typing import Optional
from azure.core.credentials import AccessToken
from azure.identity import DefaultAzureCredential
from azure.ai.ml import MLClient
import datetime
import secrets
from pathlib import Path
import yaml
from collections import namedtuple

class Credential:
    """Simple credential wrapper for Azure SDK"""
    def __init__(self, access_token: str, expires_on: int):
        self._access_token = AccessToken(token=access_token, expires_on=expires_on)
    
    def get_token(self, *scopes: str, claims: str | None = None, 
                   tenant_id: str | None = None, enable_cae: bool = False, 
                   **kwargs) -> AccessToken:
        return self._access_token


def get_workspace_client(subscription_id: str, resource_group: str, 
                         workspace_name: str, token: Optional[str] = None, 
                         expires_on: Optional[int] = None) -> MLClient:
    """Create MLClient for workspace"""
    if token and expires_on:
        credential = Credential(token, expires_on)
    else:
        credential = DefaultAzureCredential()
    return MLClient(
        credential=credential,
        subscription_id=subscription_id,
        resource_group_name=resource_group,
        workspace_name=workspace_name
    )

def get_registry_client(
        registry_name: str, 
        token: Optional[str] = None, 
        expires_on: Optional[int] = None
    ) -> MLClient:
    """Create MLClient for registry"""
    if token and expires_on:
        credential = Credential(token, expires_on)
    else:
        credential = DefaultAzureCredential()
    return MLClient(
        credential=credential,
        #subscription_id=subscription_id,
        registry_name=registry_name
    )

def github_output(output: dict[str,str])->None:
        # Set GitHub Action outputs
        if 'GITHUB_OUTPUT' in os.environ:
            with open(os.environ['GITHUB_OUTPUT'], 'a') as f:
                for key,value in output.items():
                    f.write(f"{key}={value}\n")
                    #f.write(f"resource-id={resource_id}\n")
                    #f.write(f"component-ref={component_ref_output}\n")
                    #f.write(f"component-version={shared_component.version}\n")

def get_new_asset_version():
    dt_now_str = datetime.datetime.now().isoformat().replace('T','-').replace(':','-').replace('.','-')
    return f"{dt_now_str}-{secrets.randbelow(9000)+1000}"


def load_safe_tags(tags: None|str) -> dict[str, str]:
    """
        This method splits a string into key=value pairs.
        Each pair is comma separated.
        This means that the "," should not be used in any key or value,
        and that the "=" should not be used in any key.
        Trailing and leading whitespace in keys and values are removed.
        Nonascii characters are removed from both keys and values
    """
    #print(f"Safe handling of tags: {tags}")
    nonascii = r'[^\x00-\x7F]+'
    if tags:
        res :dict[str,str] = dict()
        tl = re.split(r",\s*",tags)
        for t in tl:
            kv = re.split(r"\s*=\s*",t,1)
            if type(kv)==str:
                key=tag
                val=None
            else:
                key=kv[0]
                if len(kv)==2:
                    val=re.sub(nonascii,'',kv[1]).strip()
                else:
                    val=None
            #res.update({key.strip(): val})
            res.update({re.sub(nonascii,'',key).strip(): val})
        return res
    else:
        return {}

def check_and_replace_environment(ml_client_reg: MLClient, env: str) -> str:
    """
    Utility function to replace environment with its registry equivalent for custom environments

    If environment is on the form 'azureml:<env_name>:<version>' or 'azureml:<env_name>@latest', the function will
    replace it with the corresponding environment ID from the registry. If the environment is a curated environment,
    it will be left as is.
    """

    pattern_latest = re.compile(r"^([\w\-]+)@latest$")
    pattern_version = re.compile(r"^([\w\-]+):(\d+)$") # need to update this, or add another pattern
    pattern_azureml = re.compile(r"^azureml://registries/azureml/.+")

    match_latest = pattern_latest.match(env)
    match_version = pattern_version.match(env)
    match_azureml = pattern_azureml.match(env)

    # The latest registered version of the environment is used,
    # as the environment registration happens right before the component registration
    if match_latest:
        env_name = match_latest.group(1)
        return ml_client_reg.environments.get(name=env_name, label="latest").id
    elif match_version:
        env_name = match_version.group(1)
        return ml_client_reg.environments.get(name=env_name, label="latest").id
    elif match_azureml:
        return env
    else:
        raise ValueError(
            f"Environment string '{env}' does not match any expected pattern"
        )

def get_yaml_from_folder(asset_type:str, folder_path:Path)->Path|None:
    asset_map = {
        'data':'https://azuremlschemas.azureedge.net/latest/data.schema.json',
        'component':'https://azuremlschemas.azureedge.net/latest/commandComponent.schema.json',
        #'environment':'',
        #'model':'',
        #'data': '',
        #'onlineendpoint' :''
    }
    if asset_type in asset_map:
        schema = asset_map[asset_type]
    else:
        raise NotImplementedError("That asset_type hasn't been implemented yet")

    yaml_files = [os.path.join(root, file) for root, dirs, files in os.walk(folder_path) for file in files if file.endswith('.yaml')]
    matching_files = []
    for file in yaml_files:
        schema_verified = False
        with open(file,'r') as yf:
            yaml_file = yaml.safe_load(yf)
            if '$schema' in yaml_file:
                yf_schema = yaml_file['$schema']
                schema_verified = yf_schema == schema
        if schema_verified:
            matching_files.append(file)
    
    if len(matching_files)>1:
        raise ValueError("More than one component yaml file found")
    if len(matching_files)<1:
        raise ValueError("No yaml file found")

    return matching_files[0]

def reference_registry_asset(
        ml_client_reg: MLClient,
        asset_type: str,
        name: str,
        version: str|None=None
    ) -> str:
    """
    Utility function to create a reference string for an asset in a registry

    The reference string is of the form:
    'azureml://registries/<registry_name>/<asset_type>s/<asset_name>/versions/<version>'
    If version is None, 'latest' is used.
    """

    if version is None:
        version = "latest"
    
    asset_type_plural = asset_type + "s"
    registry_name = ml_client_reg._operation_scope.registry_name
    reference_string = f"azureml://registries/{registry_name}/{asset_type_plural}/{name}/versions/{version}"

    return reference_string

def get_ref_properties(reference: str) -> namedtuple:
    """
    Parse Azure ML asset reference strings and extract their components.
    
    Supports three patterns:
    1. azureml:<asset_name>:<version>
    2. azureml:/subscriptions/<subscription-id>/resourceGroups/<resource-group-name>/providers/Microsoft.MachineLearningServices/workspaces/<workspace-name>/<asset-type-plural>/<asset-name>/versions/<asset-version>
    3. azureml://registries/<registry_name>/<asset-type-plural>/<asset-name>/versions/<version>
    
    Returns:
        namedtuple subclass with name and version attributes
    """
    
    # Pattern 1: azureml:<asset_name>:<version>
    pattern1 = re.compile(r'^azureml:(?P<asset_name>[^:]+):(?P<version>[^:]+)$')
    
    # Pattern 2: azureml:/subscriptions/.../workspaces/...
    pattern2 = re.compile(
        r'^azureml:/subscriptions/(?P<subscription_id>[^/]+)'
        r'/resourceGroups/(?P<resource_group>[^/]+)'
        r'/providers/Microsoft\.MachineLearningServices'
        r'/workspaces/(?P<workspace_name>[^/]+)'
        r'/(?P<asset_type_plural>[^/]+)'
        r'/(?P<asset_name>[^/]+)'
        r'/versions/(?P<version>[^/]+)$'
    )
    
    # Pattern 3: azureml://registries/<registry_name>/...
    pattern3 = re.compile(
        r'^azureml://registries/(?P<registry_name>[^/]+)'
        r'/(?P<asset_type_plural>[^/]+)'
        r'/(?P<asset_name>[^/]+)'
        r'/versions/(?P<version>[^/]+)$'
    )
    
    # Try matching each pattern
    match1 = pattern1.match(reference)
    if match1:
        d = {
            'pattern': 'simple',
            'asset_name': match1.group('asset_name'),
            'version': match1.group('version')
        }
    else:
        match2 = pattern2.match(reference)
        match3 = pattern3.match(reference)
        if match2:
            d = {
                'pattern': 'workspace',
                'subscription_id': match2.group('subscription_id'),
                'resource_group': match2.group('resource_group'),
                'workspace_name': match2.group('workspace_name'),
                'asset_type': match2.group('asset_type_plural')[:-1],
                'name': match2.group('asset_name'),
                'version': match2.group('version')
            }
        elif match3:
            d = {
                'pattern': 'registry',
                'registry_name': match3.group('registry_name'),
                'asset_type': match3.group('asset_type_plural')[:-1],
                'name': match3.group('asset_name'),
                'version': match3.group('version')
            }
        else:
            # No pattern matched
            raise ValueError(f"Reference string '{reference}' does not match any supported Azure ML reference pattern")
    
    # For ref with all retrieved attributes
    # ref = namedtuple('Ref',d.keys())
    # return ref(*d)
    ref = namedtuple('Ref',['name','version'])
    return ref(name=d['name'],version=d['version'])
