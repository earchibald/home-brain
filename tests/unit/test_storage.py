"""
Unit tests for storage classes (ApiKeyStore, ModelPreferenceStore).

These tests verify persistent storage functionality for user API keys
and model preferences.
"""

import os
import json
import tempfile
import pytest
from unittest.mock import patch

# Import from slack_agent (these are internal classes)
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from agents.slack_agent import ApiKeyStore, ModelPreferenceStore

pytestmark = pytest.mark.unit


class TestApiKeyStore:
    """Test suite for ApiKeyStore class."""

    def test_init_creates_file(self):
        """Test that initialization creates storage file with secure permissions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = os.path.join(tmpdir, "test_api_keys.json")
            store = ApiKeyStore(storage_path)
            
            assert os.path.exists(storage_path)
            assert oct(os.stat(storage_path).st_mode)[-3:] == "600"
    
    def test_set_and_get_key(self):
        """Test storing and retrieving an API key."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = os.path.join(tmpdir, "test_api_keys.json")
            store = ApiKeyStore(storage_path)
            
            store.set_key("U123", "gemini", "test-key-12345")
            retrieved = store.get_key("U123", "gemini")
            
            assert retrieved == "test-key-12345"
    
    def test_get_nonexistent_key(self):
        """Test retrieving a key that doesn't exist returns None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = os.path.join(tmpdir, "test_api_keys.json")
            store = ApiKeyStore(storage_path)
            
            assert store.get_key("U999", "gemini") is None
    
    def test_delete_key(self):
        """Test deleting an API key."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = os.path.join(tmpdir, "test_api_keys.json")
            store = ApiKeyStore(storage_path)
            
            store.set_key("U123", "gemini", "test-key")
            store.delete_key("U123", "gemini")
            
            assert store.get_key("U123", "gemini") is None
    
    def test_multiple_users(self):
        """Test storing keys for multiple users."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = os.path.join(tmpdir, "test_api_keys.json")
            store = ApiKeyStore(storage_path)
            
            store.set_key("U123", "gemini", "key1")
            store.set_key("U456", "gemini", "key2")
            
            assert store.get_key("U123", "gemini") == "key1"
            assert store.get_key("U456", "gemini") == "key2"
    
    def test_multiple_providers(self):
        """Test storing keys for multiple providers for same user."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = os.path.join(tmpdir, "test_api_keys.json")
            store = ApiKeyStore(storage_path)
            
            store.set_key("U123", "gemini", "gemini-key")
            store.set_key("U123", "anthropic", "anthropic-key")
            
            assert store.get_key("U123", "gemini") == "gemini-key"
            assert store.get_key("U123", "anthropic") == "anthropic-key"
    
    def test_mask_key(self):
        """Test key masking for display."""
        store = ApiKeyStore(storage_path="/tmp/unused")
        
        assert store.mask_key("") == "(not set)"
        assert store.mask_key(None) == "(not set)"
        assert store.mask_key("short") == "****"
        assert store.mask_key("test-key-12345") == "test...2345"


class TestModelPreferenceStore:
    """Test suite for ModelPreferenceStore class."""

    def test_init_creates_file(self):
        """Test that initialization creates storage file with secure permissions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = os.path.join(tmpdir, "test_model_prefs.json")
            store = ModelPreferenceStore(storage_path)
            
            assert os.path.exists(storage_path)
            assert oct(os.stat(storage_path).st_mode)[-3:] == "600"
    
    def test_set_and_get_preference(self):
        """Test storing and retrieving a model preference."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = os.path.join(tmpdir, "test_model_prefs.json")
            store = ModelPreferenceStore(storage_path)
            
            store.set_preference("U123", "gemini", "gemini-1.5-flash")
            pref = store.get_preference("U123")
            
            assert pref == {
                "provider_id": "gemini",
                "model_name": "gemini-1.5-flash"
            }
    
    def test_get_nonexistent_preference(self):
        """Test retrieving a preference that doesn't exist returns None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = os.path.join(tmpdir, "test_model_prefs.json")
            store = ModelPreferenceStore(storage_path)
            
            assert store.get_preference("U999") is None
    
    def test_update_preference(self):
        """Test updating an existing preference."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = os.path.join(tmpdir, "test_model_prefs.json")
            store = ModelPreferenceStore(storage_path)
            
            store.set_preference("U123", "ollama_local", "llama3.2")
            store.set_preference("U123", "gemini", "gemini-1.5-flash")
            
            pref = store.get_preference("U123")
            assert pref["provider_id"] == "gemini"
            assert pref["model_name"] == "gemini-1.5-flash"
    
    def test_clear_preference(self):
        """Test clearing a user's preference."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = os.path.join(tmpdir, "test_model_prefs.json")
            store = ModelPreferenceStore(storage_path)
            
            store.set_preference("U123", "gemini", "gemini-1.5-flash")
            store.clear_preference("U123")
            
            assert store.get_preference("U123") is None
    
    def test_multiple_users(self):
        """Test storing preferences for multiple users."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = os.path.join(tmpdir, "test_model_prefs.json")
            store = ModelPreferenceStore(storage_path)
            
            store.set_preference("U123", "gemini", "gemini-1.5-flash")
            store.set_preference("U456", "ollama_local", "llama3.2")
            
            pref1 = store.get_preference("U123")
            pref2 = store.get_preference("U456")
            
            assert pref1["provider_id"] == "gemini"
            assert pref2["provider_id"] == "ollama_local"
    
    def test_persistence_across_instances(self):
        """Test that preferences persist across store instances."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = os.path.join(tmpdir, "test_model_prefs.json")
            
            # Create store and save preference
            store1 = ModelPreferenceStore(storage_path)
            store1.set_preference("U123", "gemini", "gemini-1.5-flash")
            
            # Create new store instance and verify persistence
            store2 = ModelPreferenceStore(storage_path)
            pref = store2.get_preference("U123")
            
            assert pref == {
                "provider_id": "gemini",
                "model_name": "gemini-1.5-flash"
            }
    
    def test_corrupted_file_recovery(self):
        """Test that store recovers from corrupted JSON file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = os.path.join(tmpdir, "test_model_prefs.json")
            
            # Create corrupted file
            with open(storage_path, 'w') as f:
                f.write("{ invalid json }")
            
            # Store should recover and return None for missing data
            store = ModelPreferenceStore(storage_path)
            assert store.get_preference("U123") is None
            
            # Should still be able to save new data
            store.set_preference("U123", "gemini", "gemini-1.5-flash")
            pref = store.get_preference("U123")
            assert pref is not None
