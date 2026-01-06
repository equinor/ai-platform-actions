"""

Get asset methods.
These are helper methods

"""
from azure.ai.ml.entities import Component,Environment,BuildContext,Model,Data,Job
from azure.ai.ml import MLClient
from azure.core.polling import LROPoller
import typer
from typing import Optional,Iterable
from .util import get_workspace_client
import yaml
from pathlib import Path
import datetime

app = typer.Typer()

def filter_assets_by_property(assets: list[Component|Environment|Model], property:str|dict[str,None|str])-> None|list[Component|Environment|Model]:
    return assets

def filter_assets_by_version(assets: list[Component|Environment|Model], version:str)-> None|list[Component|Environment|Model]:   
    return [a for a in assets if a.version==version]

def filter_assets_by_tag(assets: list[Component|Environment|Model], tag:str|dict[str,None|str]) -> None|list[Component|Environment|Model]:
    asset_list : list[Component|Environment|Model] = list()
    tag_str = type(tag)==str
    #print(f"tag is a string? {tag_str}")
    #print(f"filter_assets_by_tag(assets, tag={tag})")
    for a in assets:
        #print(f"Filtering asset with name={a.name}")
        tags = a.tags
        if tags:
            if tag_str:
                if tag in tags:
                    asset_list.append(a)
            else:
                keys_match=True
                values_match=True
                for t in tag:
                    keys_match = keys_match and t in tags
                    values_match = values_match and keys_match and(tags[t]==tag[t] or not tag[t])
                if keys_match and values_match:
                    asset_list.append(a)
    if len(asset_list)>0:
        return asset_list
    else:
        return None


def getenvironment(
        client:MLClient,
        name:str,
        version:str|None=None,
        tags:None|str|dict[str,None|str]=None,
        req_int_version:bool=True
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
        If tags is specified, and it is a string, the tag value MUST exist.
        If tags is specified, and it is a dict, every key in the dict MUST exist,
          AND if a key's corresponding value is specified the value MUST also match.
          However, it is ok if the environment has extra tags.
        if req_int_version is True, then the version of the environment MUST be a positive integer.
          This argument is there due to AzureML's need to have integer version fields 
          in order to update their information. If not integers, the environment can't be updated.
    """

    # the only way to get the latest version
    # HOWEVER, it populates neither the version NOR the tags. sigh...
    env_list = list(client.environments.list())
    env_list = [e for e in env_list if e.name==name]
    if env_list:
        latest_version=env_list[0].latest_version
    else:
        return None
    
    # This time, get a list that contains both version and tags.
    env_list =list(client.environments.list(name=name))

    if version:
        env_list = filter_assets_by_version(assets=env_list,version=version)
    else:
        env_list=[client.environments.get(name=name,version=latest_version)]

    if tags:
        env_list = filter_assets_by_tag(env_list,tags)

    if req_int_version:
        env_list = [e for e in env_list if e.version.isdigit()]

    return env_list

def getcomponent(
    client:MLClient,
        name:str,
        version:str|None=None,
        tags:None|str|dict[str,None|str]=None,
        req_int_version:bool=True
    ) -> None|list[Component]:

    comp_list = list(client.components.list())
    #print(f"GC [1]: {comp_list}")
    comp_list = [c for c in comp_list if c.name==name]
    if comp_list:
        latest_version = comp_list[0].latest_version
    # Beware: If this is a workspace, AND there exists a version that is non-standard,
    # then latest_version may be None.
    #print(f"GC [2]: {latest_version}")

    comp_list = list(client.components.list(name=name))
    #print(f"GC [3]: {comp_list}")

    if version:
        comp_list = filter_assets_by_version(assets=comp_list,version=version)
    else:
        comp_list = [client.components.get(name=name,version=latest_version)]
    #print(f"GC [4]: {comp_list}")

    if tags:
        comp_list = filter_assets_by_tag(comp_list,tags)
    #print(f"GC [5]: {comp_list}")
    
    if req_int_version:
        comp_list = [c for c in comp_list if c.version.isdigit()]
    #print(f"GC [6]: {comp_list}")
    
    return comp_list
    # A component may not have version set (at least in registry).
    # However, in that case the creation_context will take precedence,
    # and have the value of str(component.creation_context.created_at.timestamp())
    # (created_at is a datetime)
    #
    # Components in a workspace seems to have version property
    # Notice that while the components in a workspace have a string representing the datetime of creation,
    # the times does not correspond exactly to the created_at or last_modified_at.
    # There are small delays, pointing to separate process actually being responsible for the different timestamps.
    #
    # NB: If the component version is NOT convertible to an int, it cannot be updated.


def getmodel(
        client:MLClient,
        name:str,
        version:str|None=None,
        tags:None|str|dict[str,None|str]=None,
        req_int_version=True
    ) -> None|list[Model]:

    m_list = list(client.models.list())
    m_list = [m for m in m_list if m.name==name]
    if m_list:
        latest_version=m_list[0].latest_version
    else:
        return None

    m_list=list(client.models.list(name=name))

    if version:
        m_list = filter_assets_by_version(assets=m_list,version=version)
    else:
        m_list = filter_assets_by_version(m_list,version=latest_version)

    if tags:    
        m_list = filter_assets_by_tag(m_list,tag=tags)

    if req_int_version:
        m_list = [m for m in m_list if m.version.isdigit()]

    return m_list


def getdata(
        client:MLClient,
        name:str,
        version:str|None=None,
        tags:None|str|dict[str,None|str]=None,
        req_int_version:bool=True
    ) -> None|list[Data]:
    """
        Retrieves a data asset using the MLClient.
        
        Name is required.
        If version is specified, this MUST match.
        If tags is specified, and it is a string, the tag value MUST exist.
        If tags is specified, and it is a dict, every key in the dict MUST exist,
          AND if a key's corresponding value is specified the value MUST also match.
          However, it is ok if the data asset has extra tags.
        if req_int_version is True, then the version of the data asset MUST be a positive integer.
          This argument is there due to AzureML's need to have integer version fields 
          in order to update their information. If not integers, the data asset can't be updated.
    """

    # Get the list to find the latest version
    data_list = list(client.data.list())
    data_list = [d for d in data_list if d.name==name]
    if data_list:
        latest_version=data_list[0].latest_version
    else:
        return None
    
    # Get a list that contains both version and tags
    data_list = list(client.data.list(name=name))

    if version:
        data_list = filter_assets_by_version(assets=data_list,version=version)
    else:
        data_list = [client.data.get(name=name,version=latest_version)]

    if tags:
        data_list = filter_assets_by_tag(data_list,tags)

    if req_int_version:
        data_list = [d for d in data_list if d.version.isdigit()]

    return data_list

def getjob(
        client:MLClient,
        name:str,
        tags:None|str|dict[str,None|str]=None
    ) -> None|list[Job]:
    """
        Retrieves a job using the MLClient.
        
        Name is required.
        If tags is specified, and it is a string, the tag value MUST exist.
        If tags is specified, and it is a dict, every key in the dict MUST exist,
          AND if a key's corresponding value is specified the value MUST also match.
          However, it is ok if the job has extra tags.
        
        Note: Jobs don't have versions like other assets, so version filtering is not applicable.
    """

    # Get the specific job by name
    try:
        job = client.jobs.get(name=name)
        job_list = [job]
    except:
        return None

    if tags:
        job_list = filter_assets_by_tag(assets=job_list, tags)

    return job_list

def getcompute( 
        client:MLClient,
        name:str
    ):
    """
        Retrieves a compute target using the MLClient.
        
        Name is required.
    """

    try:
        compute = client.compute.get(name=name)
        return compute
    except:
        return None