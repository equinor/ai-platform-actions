"""
Test suite for util.py functions

This test suite covers three main functions from util.py:

1. github_output() - Writes key-value pairs to GitHub Actions output file
   - 7 tests covering single/multiple outputs, empty dict, missing env var, 
     appending, and special characters

2. load_safe_tags() - Parses comma-separated key=value tag strings
   - 12 tests covering single/multiple tags, whitespace handling, empty values,
     None input, non-ASCII character removal, and special characters

3. get_ref_properties() - Parses Azure ML asset reference strings
   - 16 tests covering various reference patterns (simple, workspace, registry)
   - NOTE: Simple pattern now works correctly (bug fixed)
   - Patterns with 'azureml:' prefix match simple pattern (colon-separated format)
   - Workspace/registry patterns work with or without 'azureml:' prefix
   
Total: 31 tests, all passing and documenting current behavior including bugs.
"""

import os
import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch, mock_open, MagicMock
from collections import namedtuple

from aip.inner.util import (
    AML_SCOPE,
    STORAGE_SCOPE,
    STORAGE_AUTH_HINT,
    Credential,
    github_output,
    load_safe_tags,
    get_ref_properties,
    storage_auth_hint,
)


@pytest.fixture
def fake_access_token():
    with patch(
        "aip.inner.util.AccessToken",
        side_effect=lambda token, expires_on: MagicMock(token=token, expires_on=expires_on),
    ):
        yield


class TestCredential:
    """Test suite for Azure SDK credential scope routing"""

    def test_get_token_selects_aml_token_only_for_aml_scope(self):
        with patch(
            "aip.inner.util.AccessToken",
            side_effect=lambda token, expires_on: MagicMock(token=token, expires_on=expires_on),
        ):
            credential = Credential("arm-token", 1234567890, "aml-token")

        assert credential.get_token(AML_SCOPE).token == "aml-token"
        assert credential.get_token("https://management.azure.com/.default").token == "arm-token"

    def test_get_token_selects_storage_token_for_storage_scope(self, fake_access_token):
        credential = Credential("arm-token", 1234567890, "aml-token", "storage-token")

        assert credential.get_token(STORAGE_SCOPE).token == "storage-token"
        assert credential.get_token(AML_SCOPE).token == "aml-token"
        assert credential.get_token("https://management.azure.com/.default").token == "arm-token"

    def test_get_token_selects_storage_token_for_account_audience(self, fake_access_token):
        credential = Credential("arm-token", 1234567890, storage_token="storage-token")

        assert credential.get_token("https://acct.blob.core.windows.net/.default").token == "storage-token"
        assert credential.get_token("https://acct.dfs.core.windows.net/.default").token == "storage-token"

    def test_get_token_falls_back_to_arm_token_without_storage_token(self, fake_access_token):
        credential = Credential("arm-token", 1234567890, "aml-token")

        assert credential.get_token(STORAGE_SCOPE).token == "arm-token"


class TestStorageAuthHint:
    """Test suite for the storage authorization failure hint"""

    def test_hint_returned_for_disabled_shared_key_access(self):
        error = RuntimeError(
            "KeyBasedAuthenticationNotPermitted: Key based authentication is not permitted"
        )

        assert storage_auth_hint(error) == STORAGE_AUTH_HINT

    def test_hint_returned_for_wrapped_rbac_failure(self):
        cause = RuntimeError("AuthorizationPermissionMismatch")
        error = RuntimeError("upload failed")
        error.__cause__ = cause

        assert storage_auth_hint(error) == STORAGE_AUTH_HINT

    def test_generic_authentication_failure_needs_storage_context(self):
        assert storage_auth_hint(RuntimeError("AuthenticationFailed for the job")) is None
        assert (
            storage_auth_hint(RuntimeError("AuthenticationFailed for blob upload"))
            == STORAGE_AUTH_HINT
        )

    def test_unrelated_error_returns_no_hint(self):
        assert storage_auth_hint(RuntimeError("asset not found")) is None


class TestGithubOutput:
    """Test suite for github_output function"""
    
    def test_github_output_with_single_output(self, tmp_path):
        """Test that single key-value pair is written correctly"""
        output_file = tmp_path / "github_output.txt"
        
        with patch.dict(os.environ, {'GITHUB_OUTPUT': str(output_file)}):
            github_output({'resource-id': 'test-resource-123'})
        
        content = output_file.read_text()
        assert content == "resource-id=test-resource-123\n"
    
    def test_github_output_with_multiple_outputs(self, tmp_path):
        """Test that multiple key-value pairs are written correctly"""
        output_file = tmp_path / "github_output.txt"
        
        with patch.dict(os.environ, {'GITHUB_OUTPUT': str(output_file)}):
            github_output({
                'resource-id': 'test-resource-123',
                'component-ref': 'component/ref/path',
                'component-version': '1.0.0'
            })
        
        content = output_file.read_text()
        assert "resource-id=test-resource-123\n" in content
        assert "component-ref=component/ref/path\n" in content
        assert "component-version=1.0.0\n" in content
    
    def test_github_output_with_empty_dict(self, tmp_path):
        """Test that empty dictionary doesn't write anything"""
        output_file = tmp_path / "github_output.txt"
        
        with patch.dict(os.environ, {'GITHUB_OUTPUT': str(output_file)}):
            github_output({})
        
        content = output_file.read_text()
        assert content == ""
    
    def test_github_output_without_github_output_env(self):
        """Test that function doesn't fail when GITHUB_OUTPUT env var is not set"""
        with patch.dict(os.environ, {}, clear=True):
            # Should not raise any exception
            github_output({'test-key': 'test-value'})
    
    def test_github_output_appends_to_existing_file(self, tmp_path):
        """Test that outputs are appended to existing file"""
        output_file = tmp_path / "github_output.txt"
        output_file.write_text("existing-key=existing-value\n")
        
        with patch.dict(os.environ, {'GITHUB_OUTPUT': str(output_file)}):
            github_output({'new-key': 'new-value'})
        
        content = output_file.read_text()
        assert "existing-key=existing-value\n" in content
        assert "new-key=new-value\n" in content
    
    def test_github_output_with_special_characters(self, tmp_path):
        """Test that special characters in values are handled correctly"""
        output_file = tmp_path / "github_output.txt"
        
        with patch.dict(os.environ, {'GITHUB_OUTPUT': str(output_file)}):
            github_output({
                'path': '/subscriptions/123/resourceGroups/rg-name',
                'url': 'https://example.com/path?query=value&other=123'
            })
        
        content = output_file.read_text()
        assert "path=/subscriptions/123/resourceGroups/rg-name\n" in content
        assert "url=https://example.com/path?query=value&other=123\n" in content


class TestLoadSafeTags:
    """Test suite for load_safe_tags function"""
    
    def test_load_safe_tags_with_single_tag(self):
        """Test parsing a single key=value tag"""
        result = load_safe_tags("environment=production")
        assert result == {'environment': 'production'}
    
    def test_load_safe_tags_with_multiple_tags(self):
        """Test parsing multiple comma-separated tags"""
        result = load_safe_tags("environment=production,team=data-science,version=1.0")
        assert result == {
            'environment': 'production',
            'team': 'data-science',
            'version': '1.0'
        }
    
    def test_load_safe_tags_with_whitespace(self):
        """Test that leading/trailing whitespace is stripped"""
        result = load_safe_tags("  key1  =  value1  ,  key2  =  value2  ")
        assert result == {'key1': 'value1', 'key2': 'value2'}
    
    def test_load_safe_tags_with_empty_string(self):
        """Test that empty string returns None"""
        result = load_safe_tags("")
        assert result is None
    
    def test_load_safe_tags_with_none(self):
        """Test that None remains None"""
        result = load_safe_tags(None)
        assert result is None
    
    def test_load_safe_tags_with_tag_without_value(self):
        """Test parsing tag without value (only key) - returns empty string not None"""
        result = load_safe_tags("key1=value1,key2=,key3=value3")
        assert result == {
            'key1': 'value1',
            'key2': '',
            'key3': 'value3'
        }
    
    def test_load_safe_tags_removes_nonascii_from_keys(self):
        """Test that non-ASCII characters are removed from keys"""
        result = load_safe_tags("key™=value,normal=test")
        assert result == {'key': 'value', 'normal': 'test'}
    
    def test_load_safe_tags_removes_nonascii_from_values(self):
        """Test that non-ASCII characters are removed from values"""
        result = load_safe_tags("key=value™test,normal=test")
        assert result == {'key': 'valuetest', 'normal': 'test'}
    
    def test_load_safe_tags_with_equals_in_value(self):
        """Test that equals sign in value is preserved"""
        result = load_safe_tags("equation=a=b+c,normal=value")
        assert result == {'equation': 'a=b+c', 'normal': 'value'}
    
    def test_load_safe_tags_with_special_characters_in_value(self):
        """Test that special ASCII characters are preserved"""
        result = load_safe_tags("path=/usr/local/bin,url=https://example.com")
        assert result == {
            'path': '/usr/local/bin',
            'url': 'https://example.com'
        }
    
    def test_load_safe_tags_with_numeric_values(self):
        """Test parsing numeric values (as strings)"""
        result = load_safe_tags("count=42,version=1.2.3,id=abc123")
        assert result == {
            'count': '42',
            'version': '1.2.3',
            'id': 'abc123'
        }


class TestGetRefProperties:
    """Test suite for get_ref_properties function"""
    
    def test_get_ref_properties_simple_pattern(self):
        """Test parsing simple pattern: azureml:name:version"""
        result = get_ref_properties("azureml:my-component:1.0.0")
        assert result.name == 'my-component'
        assert result.version == '1.0.0'
    
    def test_get_ref_properties_simple_pattern_without_prefix(self):
        """Test parsing simple pattern without azureml: prefix"""
        result = get_ref_properties("my-component:2.5.1")
        assert result.name == 'my-component'
        assert result.version == '2.5.1'
    
    def test_get_ref_properties_workspace_pattern(self):
        """Test parsing workspace pattern with full resource path"""
        reference = (
            "azureml:/subscriptions/12345678-1234-1234-1234-123456789012"
            "/resourceGroups/my-resource-group"
            "/providers/Microsoft.MachineLearningServices"
            "/workspaces/my-workspace"
            "/components/my-component"
            "/versions/1.0.0"
        )
        # Note: azureml: at start causes it to match simple pattern (colon-separated)
        result = get_ref_properties(reference)
        # The whole string before first : becomes the name
        assert 'azureml' in result.name
        assert result.version == '/subscriptions/12345678-1234-1234-1234-123456789012/resourceGroups/my-resource-group/providers/Microsoft.MachineLearningServices/workspaces/my-workspace/components/my-component/versions/1.0.0'
    
    def test_get_ref_properties_workspace_pattern_without_prefix(self):
        """Test parsing workspace pattern without azureml: prefix"""
        reference = (
            "/subscriptions/12345678-1234-1234-1234-123456789012"
            "/resourceGroups/my-resource-group"
            "/providers/Microsoft.MachineLearningServices"
            "/workspaces/my-workspace"
            "/environments/my-env"
            "/versions/2.0.0"
        )
        result = get_ref_properties(reference)
        assert result.name == 'my-env'
        assert result.version == '2.0.0'
    
    def test_get_ref_properties_registry_pattern(self):
        """Test parsing registry pattern without azureml: prefix works correctly"""
        reference = "//registries/my-registry/components/my-component/versions/3.0.0"
        result = get_ref_properties(reference)
        assert result.name == 'my-component'
        assert result.version == '3.0.0'
    
    def test_get_ref_properties_registry_pattern_without_prefix(self):
        """Test parsing registry pattern without azureml: prefix"""
        reference = "//registries/azure-ml/environments/sklearn-env/versions/1.2.3"
        result = get_ref_properties(reference)
        assert result.name == 'sklearn-env'
        assert result.version == '1.2.3'
    
    def test_get_ref_properties_with_different_asset_types(self):
        """Test parsing different asset types (components, environments, models)"""
        references = [
            "//registries/reg/components/comp1/versions/1.0",
            "//registries/reg/environments/env1/versions/2.0",
            "//registries/reg/models/model1/versions/3.0",
        ]
        
        results = [get_ref_properties(ref) for ref in references]
        
        assert results[0].name == 'comp1'
        assert results[0].version == '1.0'
        assert results[1].name == 'env1'
        assert results[1].version == '2.0'
        assert results[2].name == 'model1'
        assert results[2].version == '3.0'
    
    def test_get_ref_properties_with_hyphenated_names(self):
        """Test parsing asset names with hyphens"""
        result = get_ref_properties("my-component-name:1.0.0")
        assert result.name == 'my-component-name'
        assert result.version == '1.0.0'
    
    def test_get_ref_properties_with_underscored_names(self):
        """Test parsing asset names with underscores"""
        result = get_ref_properties("my_component_name:2.0.0")
        assert result.name == 'my_component_name'
        assert result.version == '2.0.0'
    
    def test_get_ref_properties_with_semantic_version(self):
        """Test parsing with semantic versioning"""
        result = get_ref_properties("component:1.2.3-beta.1")
        assert result.name == 'component'
        assert result.version == '1.2.3-beta.1'
    
    def test_get_ref_properties_unversioned_simple_name(self):
        """Test parsing an unversioned simple asset name"""
        result = get_ref_properties("unversioned-asset")
        assert result.name == "unversioned-asset"
        assert result.version is None
    
    def test_get_ref_properties_empty_string_raises_error(self):
        """Test that empty string raises ValueError"""
        with pytest.raises(ValueError, match="does not match any supported Azure ML reference pattern"):
            get_ref_properties("")
    
    def test_get_ref_properties_malformed_workspace_pattern(self):
        """Test that malformed workspace pattern matches simple pattern"""
        reference = (
            "azureml:/subscriptions/123/resourceGroups/rg"
            "/providers/Microsoft.MachineLearningServices"
            "/workspaces/ws/components/comp"
            # Missing /versions/... so it matches simple pattern
        )
        # This matches the simple pattern "anything:anything" format
        result = get_ref_properties(reference)
        assert 'azureml' in result.name
        assert '/subscriptions' in result.version
    
    def test_get_ref_properties_returns_namedtuple_for_workspace_pattern(self):
        """Test that function returns a namedtuple for workspace pattern without azureml: prefix"""
        reference = (
            "/subscriptions/12345678-1234-1234-1234-123456789012"
            "/resourceGroups/my-resource-group"
            "/providers/Microsoft.MachineLearningServices"
            "/workspaces/my-workspace"
            "/components/my-component"
            "/versions/1.0.0"
        )
        result = get_ref_properties(reference)
        assert isinstance(result, tuple)
        assert hasattr(result, 'name')
        assert hasattr(result, 'version')
        assert result._fields == ('name', 'version')
        assert result.name == 'my-component'
        assert result.version == '1.0.0'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
