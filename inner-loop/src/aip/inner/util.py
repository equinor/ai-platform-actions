"""
Utility functions for Inner Loop Action
"""

import datetime
import os
import re
import secrets
from collections import namedtuple
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional, Union

import yaml
from azure.ai.ml import MLClient
from azure.core.credentials import AccessToken
from azure.identity import DefaultAzureCredential

AML_SCOPE = "https://ml.azure.com/.default"
STORAGE_SCOPE = "https://storage.azure.com/.default"


def _resource(scope: str) -> str:
    """Reduce an OAuth scope to its bare resource, e.g. https://storage.azure.com"""
    return scope.split("/.default", 1)[0].rstrip("/").lower()


_AML_RESOURCE = _resource(AML_SCOPE)
_STORAGE_RESOURCE = _resource(STORAGE_SCOPE)
# Blob/ADLS clients sometimes request a per-account audience instead of the shared resource.
_STORAGE_HOST_SUFFIXES = (".blob.core.windows.net", ".dfs.core.windows.net")


def _is_storage_resource(resource: str) -> bool:
    return resource == _STORAGE_RESOURCE or resource.endswith(_STORAGE_HOST_SUFFIXES)


class Credential:
    """
    Credential wrapper for Azure SDK that handles Azure ML's scope requirements.

    Azure ML operations (especially job submission) require tokens with the
    https://ml.azure.com/.default scope, and artifact upload to a storage account
    with shared key access disabled requires https://storage.azure.com/.default.
    Scope-specific tokens are returned when supplied; any other scope falls back
    to the ARM access token.
    """
    def __init__(self, access_token: str, expires_on: int, aml_token: Optional[str] = None,
                 storage_token: Optional[str] = None):
        self._access_token = AccessToken(token=access_token, expires_on=expires_on)
        self._aml_token = AccessToken(token=aml_token, expires_on=expires_on) if aml_token else None
        self._storage_token = (
            AccessToken(token=storage_token, expires_on=expires_on) if storage_token else None
        )

    def get_token(self, *scopes: str, claims: str | None = None, 
                   tenant_id: str | None = None, enable_cae: bool = False, 
                   **kwargs) -> AccessToken:
        for scope in scopes:
            resource = _resource(scope)
            if self._aml_token and resource == _AML_RESOURCE:
                return self._aml_token
            if self._storage_token and _is_storage_resource(resource):
                return self._storage_token
        return self._access_token


def get_workspace_client(subscription_id: str, resource_group: str, 
                         workspace_name: str, token: Optional[str] = None, 
                         expires_on: Optional[int] = None,
                         aml_token: Optional[str] = None,
                         storage_token: Optional[str] = None) -> MLClient:
    """Create MLClient for workspace"""
    if token and expires_on:
        credential = Credential(token, expires_on, aml_token, storage_token)
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
        expires_on: Optional[int] = None,
        aml_token: Optional[str] = None,
        storage_token: Optional[str] = None
    ) -> MLClient:
    """Create MLClient for registry"""
    if token and expires_on:
        credential = Credential(token, expires_on, aml_token, storage_token)
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
    if tags and tags.strip():
        res :dict[str,str] = dict()
        tl = re.split(r",\s*",tags)
        for t in tl:
            kv = re.split(r"\s*=\s*",t,maxsplit=1)
            if type(kv)==str:
                key=kv
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
    return None


def empty_string_to_none(value: Optional[str]) -> Optional[str]:
    """Convert empty strings to None for optional parameters"""
    if value is None or (isinstance(value, str) and value.strip() == ""):
        return None
    return value


# Storage errors that can only mean the caller was refused at the blob endpoint.
_STORAGE_AUTH_MARKERS = (
    "keybasedauthenticationnotpermitted",
    "authorizationpermissionmismatch",
    "authorizationfailure",
)
# Generic auth errors that only point at storage when raised in a storage context.
_AMBIGUOUS_AUTH_MARKERS = ("authenticationfailed", "invalidauthenticationinfo")
_STORAGE_CONTEXT_MARKERS = ("blob", "storage", "datastore")

STORAGE_AUTH_HINT = (
    "[storage] Access to the workspace storage account was denied.\n"
    "  If the account has shared key access disabled, this action needs a storage-scoped token:\n"
    "    az account get-access-token --resource https://storage.azure.com --query accessToken -o tsv\n"
    "  Pass it as the 'storage-token' action input (CLI: --storage-token), and grant the identity\n"
    "  'Storage Blob Data Contributor' on the workspace storage account."
)


def storage_auth_hint(error: BaseException) -> Optional[str]:
    """Return an actionable hint when an error chain looks like a denied blob request."""
    seen: set[int] = set()
    current: Optional[BaseException] = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        text = str(current).lower()
        if any(marker in text for marker in _STORAGE_AUTH_MARKERS):
            return STORAGE_AUTH_HINT
        if any(marker in text for marker in _AMBIGUOUS_AUTH_MARKERS) and any(
            marker in text for marker in _STORAGE_CONTEXT_MARKERS
        ):
            return STORAGE_AUTH_HINT
        current = current.__cause__ or current.__context__
    return None


def empty_string_to_none_int(value: Optional[str]) -> Optional[int]:
    """Convert empty strings to None, or parse as int for optional int parameters"""
    if value is None or (isinstance(value, str) and value.strip() == ""):
        return None
    return int(value)


AMLIGNORE_FILENAME = ".amlignore"
AMLIGNORE_SDK_RULES = "'.*', '*.amltmp', '*.amltemp'"


@contextmanager
def amlignore_preserved(folder: Optional[Path], subject: str) -> Iterator[None]:
    """Restore the folder's .amlignore, which azure-ai-ml overwrites while uploading a spec folder."""
    if folder is None or not Path(folder).is_dir():
        yield
        return
    target = Path(folder) / AMLIGNORE_FILENAME
    original = target.read_bytes() if target.is_file() else None
    if original is not None:
        print(f"[{subject}] Warning: '{target}' is overwritten by Azure ML during upload, so its rules were not applied.")
        print(f"[{subject}]   The spec folder was uploaded ignoring {AMLIGNORE_SDK_RULES} instead.")
        print(f"[{subject}]   The original file is restored once the upload completes.")
    try:
        yield
    finally:
        if original is None:
            target.unlink(missing_ok=True)
        else:
            target.write_bytes(original)


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
    

def get_ref_properties(reference: str) -> namedtuple:
    """
    Parse Azure ML asset reference strings and extract their components.
    
    Supports multiple patterns (version is optional for all):
    1. azureml:<asset_name> or <asset_name> (version will be None)
    2. azureml:<asset_name>:<version> or <asset_name>:<version>
    3. azureml:/subscriptions/<subscription-id>/resourceGroups/<resource-group-name>/providers/Microsoft.MachineLearningServices/workspaces/<workspace-name>/<asset-type-plural>/<asset-name>[/versions/<asset-version>]
    4. azureml://registries/<registry_name>/<asset-type-plural>/<asset-name>[/versions/<version>]
    
    Returns:
        namedtuple subclass with name and version attributes (version may be None)
    """
    
    # Pattern 0: [azureml:]<asset_name> (no version)
    pattern0 = re.compile(r'^(?:azureml:)?(?P<asset_name>[^:/]+)$')
    
    # Pattern 1: [azureml:]<asset_name>:<version>
    pattern1 = re.compile(r'^(?:azureml:)?(?P<asset_name>[^:]+):(?P<version>[^:]+)$')
    
    # Pattern 2a: [azureml:]/subscriptions/.../workspaces/.../<asset_name>/versions/<version>
    pattern2a = re.compile(
        r'^(?:azureml:)?/subscriptions/(?P<subscription_id>[^/]+)'
        r'/resourceGroups/(?P<resource_group>[^/]+)'
        r'/providers/Microsoft\.MachineLearningServices'
        r'/workspaces/(?P<workspace_name>[^/]+)'
        r'/(?P<asset_type_plural>[^/]+)'
        r'/(?P<asset_name>[^/]+)'
        r'/versions/(?P<version>[^/]+)$'
    )
    
    # Pattern 2b: [azureml:]/subscriptions/.../workspaces/.../<asset_name> (no version)
    pattern2b = re.compile(
        r'^(?:azureml:)?/subscriptions/(?P<subscription_id>[^/]+)'
        r'/resourceGroups/(?P<resource_group>[^/]+)'
        r'/providers/Microsoft\.MachineLearningServices'
        r'/workspaces/(?P<workspace_name>[^/]+)'
        r'/(?P<asset_type_plural>[^/]+)'
        r'/(?P<asset_name>[^/]+)$'
    )
    
    # Pattern 3a: [azureml:]//registries/<registry_name>/.../<asset_name>/versions/<version>
    pattern3a = re.compile(
        r'^(?:azureml:)?//registries/(?P<registry_name>[^/]+)'
        r'/(?P<asset_type_plural>[^/]+)'
        r'/(?P<asset_name>[^/]+)'
        r'/versions/(?P<version>[^/]+)$'
    )
    
    # Pattern 3b: [azureml:]//registries/<registry_name>/.../<asset_name> (no version)
    pattern3b = re.compile(
        r'^(?:azureml:)?//registries/(?P<registry_name>[^/]+)'
        r'/(?P<asset_type_plural>[^/]+)'
        r'/(?P<asset_name>[^/]+)$'
    )
    
    # Try matching each pattern
    match0 = pattern0.match(reference)
    if match0:
        d = {
            'pattern': 'name_only',
            'name': match0.group('asset_name'),
            'version': None
        }
    else:
        match1 = pattern1.match(reference)
        if match1:
            d = {
                'pattern': 'simple',
                'name': match1.group('asset_name'),
                'version': match1.group('version')
            }
        else:
            match2a = pattern2a.match(reference)
            match2b = pattern2b.match(reference)
            match3a = pattern3a.match(reference)
            match3b = pattern3b.match(reference)
            
            if match2a:
                d = {
                    'pattern': 'workspace',
                    'subscription_id': match2a.group('subscription_id'),
                    'resource_group': match2a.group('resource_group'),
                    'workspace_name': match2a.group('workspace_name'),
                    'asset_type': match2a.group('asset_type_plural')[:-1],
                    'name': match2a.group('asset_name'),
                    'version': match2a.group('version')
                }
            elif match2b:
                d = {
                    'pattern': 'workspace',
                    'subscription_id': match2b.group('subscription_id'),
                    'resource_group': match2b.group('resource_group'),
                    'workspace_name': match2b.group('workspace_name'),
                    'asset_type': match2b.group('asset_type_plural')[:-1],
                    'name': match2b.group('asset_name'),
                    'version': None
                }
            elif match3a:
                d = {
                    'pattern': 'registry',
                    'registry_name': match3a.group('registry_name'),
                    'asset_type': match3a.group('asset_type_plural')[:-1],
                    'name': match3a.group('asset_name'),
                    'version': match3a.group('version')
                }
            elif match3b:
                d = {
                    'pattern': 'registry',
                    'registry_name': match3b.group('registry_name'),
                    'asset_type': match3b.group('asset_type_plural')[:-1],
                    'name': match3b.group('asset_name'),
                    'version': None
                }
            else:
                # No pattern matched
                raise ValueError(f"Reference string '{reference}' does not match any supported Azure ML reference pattern")
    
    # For ref with all retrieved attributes
    # ref = namedtuple('Ref',d.keys())
    # return ref(*d)
    ref = namedtuple('Ref',['name','version'])
    return ref(name=d['name'],version=d['version'])


def get_deployment_ref_properties(resource_id: str) -> namedtuple:
    """
    Parse Azure ML online deployment resource ID and extract endpoint and deployment names.
    
    Expected format:
    /subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.MachineLearningServices/workspaces/<ws>/onlineEndpoints/<endpoint>/deployments/<deployment>
    
    Returns:
        namedtuple with endpoint_name and deployment_name attributes
    """
    pattern = re.compile(
        r'^(?:azureml:)?/subscriptions/[^/]+'
        r'/resourceGroups/[^/]+'
        r'/providers/Microsoft\.MachineLearningServices'
        r'/workspaces/[^/]+'
        r'/onlineEndpoints/(?P<endpoint_name>[^/]+)'
        r'/deployments/(?P<deployment_name>[^/]+)$'
    )
    
    match = pattern.match(resource_id)
    if not match:
        raise ValueError(
            f"Resource ID '{resource_id}' does not match expected deployment format: "
            "/subscriptions/.../onlineEndpoints/<endpoint>/deployments/<deployment>"
        )
    
    DeploymentRef = namedtuple('DeploymentRef', ['endpoint_name', 'deployment_name'])
    return DeploymentRef(
        endpoint_name=match.group('endpoint_name'),
        deployment_name=match.group('deployment_name')
    )


def load_online_endpoint_safe(source: str):
    """
    Load an online endpoint from a YAML file, with workaround for KubernetesOnlineEndpoint.
    
    The azure.ai.ml.load_online_endpoint function has a bug where it fails to load
    KubernetesOnlineEndpoint YAML files. This function detects the schema and manually
    instantiates KubernetesOnlineEndpoint when needed.
    
    Args:
        source: Path to the YAML file
        
    Returns:
        ManagedOnlineEndpoint or KubernetesOnlineEndpoint instance
    """
    from azure.ai.ml import load_online_endpoint
    from azure.ai.ml.entities import KubernetesOnlineEndpoint, ManagedOnlineEndpoint
    
    with open(source, 'r') as f:
        config = yaml.safe_load(f)
    
    schema = config.get('$schema', '')
    is_kubernetes = 'kubernetesOnlineEndpoint' in schema.lower()
    
    if not is_kubernetes:
        return load_online_endpoint(source=source)
    
    return KubernetesOnlineEndpoint(
        name=config.get('name'),
        compute=config.get('compute'),
        description=config.get('description'),
        tags=config.get('tags'),
        properties=config.get('properties'),
        auth_mode=config.get('auth_mode', 'key'),
    )


def load_online_deployment_safe(source: str):
    """
    Load an online deployment from a YAML file, with workaround for KubernetesOnlineDeployment.
    
    The azure.ai.ml.load_online_deployment function has a bug where it fails to load
    KubernetesOnlineDeployment YAML files. This function detects the schema and manually
    instantiates KubernetesOnlineDeployment when needed.
    
    Args:
        source: Path to the YAML file
        
    Returns:
        ManagedOnlineDeployment or KubernetesOnlineDeployment instance
    """
    from azure.ai.ml import load_online_deployment
    from azure.ai.ml.entities import (
        CodeConfiguration,
        KubernetesOnlineDeployment,
        ResourceRequirementsSettings,
        ResourceSettings,
    )
    
    with open(source, 'r') as f:
        config = yaml.safe_load(f)
    
    schema = config.get('$schema', '')
    is_kubernetes = 'kubernetesonlinedeployment' in schema.lower()
    
    if not is_kubernetes:
        return load_online_deployment(source=source)
    
    base_path = Path(source).parent
    
    code_config = config.get('code_configuration',{})
    resources_config = config.get('resources', {})
    requests_config = resources_config.get('requests', {})
    limits_config = resources_config.get('limits', {})
    
    code_configuration = CodeConfiguration(
        code=code_config.get('code'),
        scoring_script=code_config.get('scoring_script')
    )

    resources = ResourceRequirementsSettings(
        requests=ResourceSettings(
            cpu=requests_config.get('cpu'),
            memory=requests_config.get('memory'),
            gpu=requests_config.get('gpu'),
        ),
        limits=ResourceSettings(
            cpu=limits_config.get('cpu'),
            memory=limits_config.get('memory'),
            gpu=limits_config.get('gpu'),
        ),
    )
    
    return KubernetesOnlineDeployment(
        name=config.get('name'),
        endpoint_name=config.get('endpoint_name'),
        model=config.get('model'),
        environment=config.get('environment'),
        code_configuration=code_configuration,
        scoring_script=config.get('scoring_script'),
        code_path=config.get('code_path'),
        instance_type=config.get('instance_type'),
        instance_count=config.get('instance_count', 1),
        app_insights_enabled=config.get('app_insights_enabled', False),
        resources=resources,
        description=config.get('description'),
        tags=config.get('tags'),
        properties=config.get('properties'),
        environment_variables=config.get('environment_variables'),
        base_path=str(base_path),
    )
