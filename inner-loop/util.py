"""
Utility functions for Inner Loop Action
"""

import os
from typing import Optional
from azure.core.credentials import AccessToken
from azure.identity import DefaultAzureCredential
from azure.ai.ml import MLClient


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

def get_registry_client(subscription_id: str, registry_name: str, 
                        token: Optional[str] = None, 
                        expires_on: Optional[int] = None) -> MLClient:
    """Create MLClient for registry"""
    if token and expires_on:
        credential = Credential(token, expires_on)
    else:
        credential = DefaultAzureCredential()
    return MLClient(
        credential=credential,
        subscription_id=subscription_id,
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