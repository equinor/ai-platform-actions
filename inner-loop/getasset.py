"""

Get asset methods.
These are helper methods

"""
from azure.ai.ml.entities import Environment,BuildContext
from azure.ai.ml import MLClient
from azure.core.polling import LROPoller
import typer
from typing import Optional
from util import get_workspace_client
import yaml
from pathlib import Path

app = typer.Typer()

def filter_envs_by_tag(envs: list[Environment], tag:str|dict[str,None|str]) -> None|list[Environment]:
    e_list : list[Environment] = list()
    tag_str = type(tag)==str
    #print(f"tag is a string? {tag_str}")
    for e in envs:
        tags = e.tags
        if tags:
            if tag_str:
                if tag in tags:
                    e_list.append(e)
            else:
                keys_match=True
                values_match=True
                for t in tag:
                    keys_match = keys_match and t in tags
                    values_match = values_match and keys_match and(tags[t]==tag[t] or not tag[t])
                if keys_match and values_match:
                    e_list.append(e)
    if len(e_list)>0:
        return e_list
    else:
        return None


def getenvironment(
        client:MLClient,
        name:str,
        version:str|None=None,
        tag:None|str|dict[str,None|str]=None
    ) -> None|list[Environment]:
    """
        Retrieves an environment using the MLClient.
        This is slightly quirky, due to the implementation details of
          azure.ai.ml.operations.EnvironmentOperations.
        There is no way to retrieve both the latest_version and 
          a list containing the versions and tags in one go.
        This function hides that.

        Name is required.
        If version is specified, this MUST match.
        If tag is specified, and it is a string, the tag value MUST exist.
        If tag is specified, and it is a dict, every key in the dict MUST exist,
          AND if a key's corresponding value is specified the value MUST also match.
          However, it is ok if the environment has extra tags.
    """
    res = None

    # the only way to get the latest version
    # HOWEVER, it populates neither the version NOR the tags. sigh...
    env_list = list(client.environments.list())
    env_list = [e for e in env_list if e.name==name]
    if len(env_list)>0:
        res = [env_list[0]] #The environment with correct name and the latest version

    latest_version = res[0].latest_version
    if res and (version or tag): # If version or tag is required, we need to get the full list    

        env_list =list(client.environments.list(name=name))
        if version and tag:
            pruned_ver_list = [e for e in env_list if e.version==version]
            res = filter_envs_by_tag(pruned_ver_list,tag)
        elif tag:
            res = filter_envs_by_tag(env_list,tag)
        elif version:
            res = [e for e in env_list if e.version==version]

    else:
        res=client.environments.get(name=name,version=latest_version)
    
    if res and len(res)==0:
        res = None
    return res

