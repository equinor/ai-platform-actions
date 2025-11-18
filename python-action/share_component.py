import typer
from azure.core.credentials import AccessToken
from azure.identity import DefaultAzureCredential, AzureCliCredential,ChainedTokenCredential
from azure.ai.ml import MLClient
import os

class Credential:
    def __init__(self,access_token):
        self._access_token = access_token
    def get_token(self, *scopes: str, claims: str | None = None, tenant_id: str | None = None, enable_cae: bool = False, **kwargs: any)-> AccessToken:
        return self._access_token

def get_client(token:str,expires_on:int,subscription_id:str,resource_group_name:str,workspace_name:str)->MLClient:
    credential = Credential(AccessToken(token=token,expires_on=expires_on))
    print(credential)
    client = MLClient(
        credential=credential,
        subscription_id=subscription_id,
        resource_group_name=resource_group_name,
        workspace_name=workspace_name
    )
    return client

app = typer.Typer()

@app.command()
def environments(token:str,expires_on:int,subscription_id:str,resource_group_name:str,workspace_name:str):
    print(f"Environments in /SUBSCRIPTIONS/{subscription_id}/RESOURCEGROUPS/{resource_group_name}/PROVIDERS/Microsoft.MachineLearningServices/WORKSPACES/{workspace_name} :")
    client = get_client(token,expires_on,subscription_id,resource_group_name,workspace_name)
    e_list = list(client.environments.list())
    for e in e_list:
        print(f"Environment: {e.name}, {e.latest_version}")

@app.command()
def components(token:str,expires_on:int,subscription_id:str,resource_group_name:str,workspace_name:str):
    print(f"Components in /SUBSCRIPTIONS/{subscription_id}/RESOURCEGROUPS/{resource_group_name}/PROVIDERS/Microsoft.MachineLearningServices/WORKSPACES/{workspace_name} :")
    client = get_client(token,expires_on,subscription_id,resource_group_name,workspace_name)
    c_list = list(client.components.list())
    for c in c_list:
        print(f"Component: {c.name}, {c.latest_version}")

if __name__ == "__main__":
    app()