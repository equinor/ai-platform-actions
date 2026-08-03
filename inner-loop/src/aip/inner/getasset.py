"""

Get asset methods.
These are helper methods

"""
from azure.ai.ml.entities import Job
from azure.ai.ml import MLClient
import typer
from .arm import LIST_VIEW_ACTIVE, LIST_VIEW_ALL, AssetClient, AssetVersion
import re
import datetime

app = typer.Typer()

_INT_VERSION_PATTERN = re.compile(r"^\d+$")


def parse_int_version(version) -> None|int:
    """
    Returns the version as an int, or None when it is not a plain positive integer.

    AzureML accepts any string as a version, but only integer versions can be
    incremented, so everything else has to be ignored rather than crash the caller.
    """
    if version is None or isinstance(version, bool):
        return None
    if isinstance(version, int):
        return version if version >= 0 else None
    if not isinstance(version, str):
        return None
    candidate = version.strip()
    if not _INT_VERSION_PATTERN.match(candidate):
        return None
    return int(candidate)


def filter_assets_by_version(assets: list[AssetVersion], version:str)-> list[AssetVersion]:
    return [a for a in assets if str(a.version)==str(version)]

def filter_assets_by_tag(assets: list, tag:str|dict[str,None|str]) -> list:
    asset_list : list = list()
    for a in assets:
        tags = a.tags
        if not tags:
            continue
        if isinstance(tag, str):
            if tag in tags:
                asset_list.append(a)
            continue
        keys_match=True
        values_match=True
        for t in tag:
            keys_match = keys_match and t in tags
            values_match = values_match and keys_match and(tags[t]==tag[t] or not tag[t])
        if keys_match and values_match:
            asset_list.append(a)
    return asset_list


def report_archived_container(client: AssetClient, kind: str, name: str, subject: str) -> bool:
    """
    Handles a container whose `isArchived` flag hides otherwise healthy versions.

    Workspace containers are repaired, registry containers are only reported, because a
    registry is shared and its archival is more likely to have been deliberate.
    """
    if client.is_registry:
        print(f"[{subject}] ❌ The {kind} container '{name}' in {client.scope_label} is archived, which hides all its versions.")
        print(f"[{subject}]    Clear 'properties.isArchived' on {client.container_url(kind, name)} to restore it.")
        return False

    print(f"[{subject}] The {kind} container '{name}' in {client.scope_label} is archived, which hides all its versions. Restoring it.")
    if client.unarchive_container(kind, name):
        print(f"[{subject}] ✅ Restored the {kind} container '{name}'.")
        return True
    print(f"[{subject}] ❌ Could not restore the {kind} container '{name}'. Continuing with the versions that are readable.")
    return False


def _latest_version(container_latest: None|str, versions: list[AssetVersion], req_int_version: bool) -> None|str:
    if container_latest:
        return str(container_latest)
    # Registries leave latestVersion empty, so fall back to the newest creation timestamp.
    candidates = [v for v in versions if parse_int_version(v.version) is not None] if req_int_version else versions
    if not candidates:
        return None
    oldest = datetime.datetime.min.replace(tzinfo=datetime.timezone.utc)
    return max(candidates, key=lambda v: v.created_at or oldest).version


def _select_versions(
        client: AssetClient,
        kind: str,
        name: str,
        version: str|int|None,
        tags: None|str|dict[str,None|str],
        req_int_version: bool,
        include_archived: bool = False,
    ) -> list[AssetVersion]:
    container = client.get_container(kind, name)
    if container is None:
        return []
    if container.is_archived:
        report_archived_container(client, kind, name, subject=f"get {kind}")

    if version is not None:
        selected = client.get_version(kind, name, str(version))
        asset_list = [selected] if selected else []
    else:
        list_view = LIST_VIEW_ALL if include_archived else LIST_VIEW_ACTIVE
        versions = client.list_versions(kind, name, list_view_type=list_view)
        latest = _latest_version(container.latest_version, versions, req_int_version)
        if latest is None:
            return []
        asset_list = filter_assets_by_version(versions, latest)
        if not asset_list:
            selected = client.get_version(kind, name, latest)
            asset_list = [selected] if selected else []

    if not include_archived:
        asset_list = [a for a in asset_list if not a.is_archived]

    if tags:
        asset_list = filter_assets_by_tag(assets=asset_list,tag=tags)

    if req_int_version:
        asset_list = [a for a in asset_list if parse_int_version(a.version) is not None]

    return asset_list


def next_int_version(client: AssetClient, kind: str, name: str, subject: str) -> str:
    """
    Returns the version to deploy next: the highest integer version under the container,
    plus one.

    Archived versions are counted, because an archived version still occupies its version
    number and writing to it again would overwrite it.
    """
    container = client.get_container(kind, name)
    if container is None:
        print(f"[{subject}] No existing {kind} '{name}' in {client.scope_label}. Deploying version 1.")
        return "1"
    if container.is_archived:
        report_archived_container(client, kind, name, subject)

    versions = client.list_versions(kind, name, list_view_type=LIST_VIEW_ALL)
    numbers = [n for n in (parse_int_version(v.version) for v in versions) if n is not None]
    skipped = len(versions) - len(numbers)
    if skipped:
        print(f"[{subject}] Ignoring {skipped} non-integer version(s) of {kind} '{name}'.")
    latest = max(numbers) if numbers else 0
    print(f"[{subject}] Highest integer version of {kind} '{name}' is {latest or 'none'}. Deploying version {latest + 1}.")
    return str(latest + 1)


def getenvironment(
        client:AssetClient,
        name:str,
        version:str|int|None=None,
        tags:None|str|dict[str,None|str]=None,
        req_int_version:bool=True
    ) -> list[AssetVersion]:
    """
        Retrieves environment versions over the ARM REST API.

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
    return _select_versions(client, "environment", name, version, tags, req_int_version)


def getcomponent(
        client:AssetClient,
        name:str,
        version:str|int|None=None,
        tags:None|str|dict[str,None|str]=None,
        req_int_version:bool=True
    ) -> list[AssetVersion]:
    """Retrieves component versions over the ARM REST API. See getenvironment for the filter rules."""
    return _select_versions(client, "component", name, version, tags, req_int_version)


def getmodel(
        client:AssetClient,
        name:str,
        version:str|int|None=None,
        tags:None|str|dict[str,None|str]=None,
        req_int_version=True
    ) -> list[AssetVersion]:
    """Retrieves model versions over the ARM REST API. See getenvironment for the filter rules."""
    return _select_versions(client, "model", name, version, tags, req_int_version)


def getdata(
        client:AssetClient,
        name:str,
        version:str|int|None=None,
        tags:None|str|dict[str,None|str]=None,
        req_int_version:bool=True
    ) -> list[AssetVersion]:
    """Retrieves data asset versions over the ARM REST API. See getenvironment for the filter rules."""
    return _select_versions(client, "data", name, version, tags, req_int_version)

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
        job_list = filter_assets_by_tag(assets=job_list, tag=tags)

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