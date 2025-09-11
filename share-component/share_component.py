import sys
import os
import re
import tempfile
from azure.core.credentials import AccessToken
from azure.ai.ml import MLClient
from azure.ai.ml.entities import Component
from azure.ai.ml import load_component
import yaml


class Credential:
    def __init__(self, access_token):
        self._access_token = access_token
    
    def get_token(self, *scopes: str, claims: str | None = None, tenant_id: str | None = None, enable_cae: bool = False, **kwargs) -> AccessToken:
        return self._access_token


def parse_component_ref(component_ref: str):
    """Parse component reference to extract name and version"""
    # Handle different formats:
    # - azureml:component_name:version
    # - component_name:version  
    # - resource_id
    # - component_name (latest)
    
    if component_ref.startswith('azureml:'):
        # Format: azureml:component_name:version
        parts = component_ref.split(':')
        if len(parts) == 3:
            return parts[1], parts[2]
        elif len(parts) == 2:
            return parts[1], None
    elif ':' in component_ref and not component_ref.startswith('/'):
        # Format: component_name:version
        parts = component_ref.split(':')
        return parts[0], parts[1] if len(parts) > 1 else None
    elif component_ref.startswith('/subscriptions/'):
        # Resource ID format - extract from path
        # /subscriptions/{sub}/resourceGroups/{rg}/providers/Microsoft.MachineLearningServices/workspaces/{ws}/components/{name}/versions/{version}
        parts = component_ref.split('/')
        if len(parts) >= 11 and 'components' in parts:
            comp_idx = parts.index('components')
            name = parts[comp_idx + 1] if comp_idx + 1 < len(parts) else None
            version = parts[comp_idx + 3] if comp_idx + 3 < len(parts) and parts[comp_idx + 2] == 'versions' else None
            return name, version
    else:
        # Just component name
        return component_ref, None
    
    raise ValueError(f"Invalid component reference format: {component_ref}")


def parse_tags(tags_str: str) -> dict:
    """Parse comma-separated key=value tags into dictionary"""
    if not tags_str or tags_str.strip() == '':
        return {}
    
    tags = {}
    for tag_pair in tags_str.split(','):
        if '=' in tag_pair:
            key, value = tag_pair.split('=', 1)
            tags[key.strip()] = value.strip()
    return tags


def get_workspace_client(token: str, expires_on: int, subscription_id: str, resource_group_name: str, workspace_name: str) -> MLClient:
    """Create MLClient for workspace"""
    credential = Credential(AccessToken(token=token, expires_on=expires_on))
    return MLClient(
        credential=credential,
        subscription_id=subscription_id,
        resource_group_name=resource_group_name,
        workspace_name=workspace_name
    )


def get_registry_client(token: str, expires_on: int, subscription_id: str, registry_name: str) -> MLClient:
    """Create MLClient for registry"""
    credential = Credential(AccessToken(token=token, expires_on=expires_on))
    return MLClient(
        credential=credential,
        subscription_id=subscription_id,
        registry_name=registry_name
    )


def validate_inputs(token, expires_on, subscription_id, resource_group, workspace_name, registry_name, component_ref, tags_str):
    """Comprehensive input validation with detailed error reporting"""
    print("🔍 Validating inputs...")
    validation_errors = 0
    
    # Check required inputs
    required_inputs = {
        'token': token,
        'expires_on': expires_on,
        'subscription_id': subscription_id,
        'resource_group': resource_group,
        'workspace_name': workspace_name,
        'registry_name': registry_name,
        'component_ref': component_ref
    }
    
    for param_name, param_value in required_inputs.items():
        if not param_value or (isinstance(param_value, str) and param_value.strip() == ''):
            print(f"❌ Error: {param_name.replace('_', '-')} is required but not provided")
            validation_errors += 1
    
    # Validate subscription ID format (should be a GUID)
    if subscription_id and not re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', subscription_id, re.IGNORECASE):
        print(f"❌ Error: Invalid subscription-id format: {subscription_id}")
        print("   Subscription ID should be a GUID format (e.g., 12345678-1234-1234-1234-123456789012)")
        validation_errors += 1
    
    # Validate expires_on is a reasonable timestamp
    if expires_on:
        try:
            expires_on_int = int(expires_on)
            import time
            current_time = int(time.time())
            if expires_on_int <= current_time:
                print(f"❌ Error: Token appears to be expired (expires_on: {expires_on_int}, current: {current_time})")
                validation_errors += 1
        except (ValueError, TypeError):
            print(f"❌ Error: Invalid expires_on format: {expires_on}")
            print("   expires_on should be a Unix timestamp")
            validation_errors += 1
    
    # Validate component reference format
    if component_ref:
        try:
            parse_component_ref(component_ref)
        except ValueError as e:
            print(f"❌ Error: {str(e)}")
            print("   Valid formats:")
            print("   - azureml:component_name:version")
            print("   - component_name:version")
            print("   - component_name (uses latest version)")
            print("   - Full resource ID")
            validation_errors += 1
    
    # Validate tags format if provided
    if tags_str and tags_str.strip():
        if not re.match(r'^[a-zA-Z0-9_-]+=.+(?:,[a-zA-Z0-9_-]+=.+)*$', tags_str):
            print(f"❌ Error: Invalid tags format: {tags_str}")
            print("   Tags should be in format: 'key1=value1,key2=value2'")
            print("   Example: 'component=preprocessing,language=python,tested=true'")
            validation_errors += 1
        else:
            # Validate individual tag pairs
            for tag_pair in tags_str.split(','):
                if '=' not in tag_pair:
                    print(f"❌ Error: Invalid tag pair (missing =): {tag_pair}")
                    validation_errors += 1
                else:
                    key, value = tag_pair.split('=', 1)
                    if not key.strip() or not value.strip():
                        print(f"❌ Error: Empty tag key or value: {tag_pair}")
                        validation_errors += 1
    
    # Check for validation errors and exit if any found
    if validation_errors > 0:
        print(f"\n❌ Validation failed with {validation_errors} error(s). Please fix the above issues and try again.")
        return False
    
    print("✅ Input validation passed")
    return True


def print_action_summary(component_ref, workspace_name, resource_group, registry_name, tags_str):
    """Print comprehensive action summary before execution"""
    print("=" * 60)
    print("🔗 SHARE COMPONENT - Azure ML Component Sharing")
    print("=" * 60)
    print(f"📦 Component Reference: {component_ref}")
    print(f"🏢 Source Workspace:    {workspace_name}")
    print(f"📁 Resource Group:      {resource_group}")
    print(f"🏛️  Target Registry:     {registry_name}")
    if tags_str and tags_str.strip():
        print(f"🏷️  Tags to Apply:       {tags_str}")
    else:
        print("🏷️  Tags to Apply:       None")
    print("=" * 60)
    print("")


def print_execution_results(shared_component, resource_id, component_ref_output, registry_name):
    """Print comprehensive execution results"""
    print("")
    print("=" * 60)
    print("🎉 COMPONENT SHARING COMPLETED SUCCESSFULLY!")
    print("=" * 60)
    print(f"📦 Component Name:      {shared_component.name}")
    print(f"🔢 Component Version:   {shared_component.version}")
    print(f"🆔 Resource ID:         {resource_id}")
    print(f"🔗 Component Reference: {component_ref_output}")
    print(f"🏛️  Available in Registry: {registry_name}")
    if hasattr(shared_component, 'tags') and shared_component.tags:
        print(f"🏷️  Applied Tags:")
        for key, value in shared_component.tags.items():
            print(f"    • {key} = {value}")
    print("=" * 60)
    print("")
    print("✅ The component is now available for use in other workspaces!")
    print("💡 You can reference it using:")
    print(f"   - azureml:{shared_component.name}:{shared_component.version}")
    print(f"   - Registry: {registry_name}")


def main():
    if len(sys.argv) != 9:
        print("❌ Error: Expected 8 arguments")
        print("Usage: share_component.py <token> <expires_on> <subscription_id> <resource_group> <workspace_name> <registry_name> <component_ref> <tags>")
        sys.exit(1)
    
    # Parse command line arguments
    token = sys.argv[1]
    expires_on = sys.argv[2]
    subscription_id = sys.argv[3]
    resource_group = sys.argv[4]
    workspace_name = sys.argv[5]
    registry_name = sys.argv[6]
    component_ref = sys.argv[7]
    tags_str = sys.argv[8] if sys.argv[8] != '' else None
    
    try:
        # Print action summary
        print_action_summary(component_ref, workspace_name, resource_group, registry_name, tags_str)
        print(f"Token length: {len(token)}")
        print(f"Expires: {expires_on}")
        print("=" * 40)

        # Comprehensive input validation
        if not validate_inputs(token, expires_on, subscription_id, resource_group, workspace_name, registry_name, component_ref, tags_str):
            sys.exit(1)
        
        # Convert expires_on to int after validation
        expires_on = int(expires_on)
        
        # Parse component reference
        print("📋 Parsing component reference...")
        component_name, component_version = parse_component_ref(component_ref)
        print(f"   • Component Name: {component_name}")
        print(f"   • Component Version: {component_version or 'latest'}")
        print("")
        
        # Get workspace client and retrieve component
        print("🔍 Connecting to source workspace...")
        print(f"   • Workspace: {workspace_name}")
        print(f"   • Resource Group: {resource_group}")
        print(f"   • Subscription: {subscription_id}")
        workspace_client = get_workspace_client(token, expires_on, subscription_id, resource_group, workspace_name)
        print("✅ Connected to workspace successfully")
        
        # Get the component from workspace
        print(f"📦 Retrieving component from workspace...")
        if component_version:
            component = workspace_client.components.get(name=component_name, version=component_version)
        else:
            component = workspace_client.components.get(name=component_name)

        print(f"✅ Retrieved component: {component.name} version {component.version}")
        if hasattr(component, 'description') and component.description:
            print(f"   • Description: {component.description}")
        if hasattr(component, 'tags') and component.tags:
            print(f"   • Existing Tags: {component.tags}")
        print("")
        
        # Download the component and its dependencies to a temp folder
        with tempfile.TemporaryDirectory() as temp_dir:
            print(f"📥 Downloading component and dependencies to: {temp_dir}")
            workspace_client.components.download(
                name=component_name,
                version=component_version,
                download_path=temp_dir
            )
            spec_path = os.path.join(temp_dir, "component_spec.yaml")
            print(f"📄 Loading component spec from: {spec_path}")
            loaded_component = load_component(source=spec_path)
            # Parse and apply tags if provided
            if tags_str:
                new_tags = parse_tags(tags_str)
                if loaded_component.tags:
                    loaded_component.tags.update(new_tags)
                else:
                    loaded_component.tags = new_tags
            # Preprocess component_spec.yaml to fix command field
            with open(spec_path, 'r', encoding='utf-8') as f:
                spec = yaml.safe_load(f)
            if 'command' in spec:
                # Remove all backslashes and newlines
                cmd = spec['command']
                # Replace all backslashes and newlines with a space
                import re
                cmd_single_line = re.sub(r'[\\\n]+', ' ', cmd)
                spec['command'] = cmd_single_line.strip()
                print(f"🛠️  Preprocessed command field to single line (no backslashes):")
                print(f"   {spec['command']}")
                with open(spec_path, 'w', encoding='utf-8') as f:
                    yaml.safe_dump(spec, f, default_flow_style=False, sort_keys=False)
            # Get registry client and share component
            print("🏛️  Connecting to target registry...")
            print(f"   • Registry: {registry_name}")
            print(f"   • Subscription: {subscription_id}")
            registry_client = get_registry_client(token, expires_on, subscription_id, registry_name)
            print("✅ Connected to registry successfully")
            print("")
            # Share loaded component to registry using create_or_update
            print("📤 Sharing loaded component to registry...")
            shared_component = registry_client.components.create_or_update(loaded_component)
            # Generate outputs
            resource_id = f"/subscriptions/{subscription_id}/resourceGroups//providers/Microsoft.MachineLearningServices/registries/{registry_name}/components/{shared_component.name}/versions/{shared_component.version}"
            component_ref_output = f"azureml:{shared_component.name}:{shared_component.version}"
            # Print comprehensive results
            print_execution_results(shared_component, resource_id, component_ref_output, registry_name)
            # Set GitHub Action outputs
            print("📝 Setting GitHub Action outputs...")
            if 'GITHUB_OUTPUT' in os.environ:
                with open(os.environ['GITHUB_OUTPUT'], 'a') as f:
                    f.write(f"resource-id={resource_id}\n")
                    f.write(f"component-ref={component_ref_output}\n")
                    f.write(f"component-version={shared_component.version}\n")
                print("✅ GitHub Action outputs set successfully")
            else:
                print("ℹ️  GitHub Action outputs not available (not running in GitHub Actions)")
            # End of with tempfile.TemporaryDirectory()
        
    except Exception as e:
        print("")
        print("=" * 60)
        print("❌ ERROR DURING COMPONENT SHARING")
        print("=" * 60)
        print(f"Error Type: {type(e).__name__}")
        print(f"Error Message: {str(e)}")
        print("")
        print("🔍 Troubleshooting Tips:")
        print("• Verify the component exists in the source workspace")
        print("• Check that you have permissions to read from workspace and write to registry")
        print("• Ensure the registry name is correct and accessible")
        print("• Verify the component reference format is valid")
        print("• Check that the authentication token is valid and not expired")
        print("=" * 60)
        sys.exit(1)


if __name__ == "__main__":
    main()
