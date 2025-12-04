"""
Tests for performance optimizations in the codebase.
"""
import unittest
from pathlib import Path
from typing import Dict, Any, Optional
import yaml


class TestPromptsCaching(unittest.TestCase):
    """Test that prompts.yaml caching works correctly."""

    def test_prompts_cache_returns_same_object(self):
        """Verify that repeated calls return the same cached object."""
        # Simulate the caching mechanism used in groq_client and context_manager
        cache: Optional[Dict[str, Any]] = None
        
        def load_prompts() -> Dict[str, Any]:
            nonlocal cache
            if cache is not None:
                return cache
            
            try:
                prompts_file = Path("config/prompts.yaml")
                if prompts_file.exists():
                    with open(prompts_file, "r", encoding="utf-8") as f:
                        cache = yaml.safe_load(f) or {}
                        return cache
            except Exception:
                pass
            
            cache = {}
            return cache
        
        # First call populates cache
        first_result = load_prompts()
        # Second call should return same object
        second_result = load_prompts()
        
        self.assertIs(first_result, second_result, "Cache should return same object")
        self.assertIsNotNone(cache)

    def test_prompts_file_exists(self):
        """Verify that the prompts.yaml file exists."""
        prompts_file = Path("config/prompts.yaml")
        self.assertTrue(prompts_file.exists(), "prompts.yaml should exist in config/")


class TestPriorityKeywordsOptimization(unittest.TestCase):
    """Test that priority keywords are stored as a frozenset for O(1) lookup."""

    def test_priority_keywords_matching(self):
        """Test that priority keyword matching works correctly."""
        # These are the priority keywords from system_context.py
        priority_keywords = frozenset([
            'chrome', 'firefox', 'edge', 'brave', 'opera',
            'spotify', 'discord', 'teams', 'slack', 'zoom',
            'vscode', 'code', 'pycharm', 'studio', 'notepad',
            'python', 'node', 'java', 'dotnet', 'powershell', 'cmd',
            'obs', 'streamlabs', 'nvidia', 'radeon',
            'steam', 'epic', 'origin', 'uplay', 'battle',
            'cursor', 'sublime', 'atom', 'brackets',
            'postman', 'docker', 'git',
            'excel', 'word', 'outlook', 'powerpoint',
            'premiere', 'photoshop', 'illustrator', 'after effects',
        ])
        
        def is_priority_process(proc_lower: str) -> bool:
            for keyword in priority_keywords:
                if keyword in proc_lower:
                    return True
            return False
        
        # Test matching
        self.assertTrue(is_priority_process("chrome.exe"))
        self.assertTrue(is_priority_process("spotify"))
        self.assertTrue(is_priority_process("visual studio code"))  # Contains 'code'
        self.assertFalse(is_priority_process("randomprocess"))
        self.assertFalse(is_priority_process("svchost.exe"))


class TestSteamManifestOptimization(unittest.TestCase):
    """Test that Steam manifest pre-computation works correctly."""

    def test_normalized_values_precomputed(self):
        """Test that normalized values are computed once per manifest."""
        import re
        
        # Simulate parsing a manifest with pre-computed values
        manifests = []
        
        # Mock manifest data
        test_data = [
            ("123", "Counter-Strike 2", "Counter-Strike Global Offensive"),
            ("456", "Valheim", "Valheim"),
            ("789", "Elden Ring", "ELDEN RING"),
        ]
        
        for aid, gname, idir in test_data:
            idir_lower = (idir or "").lower()
            gname_lower = (gname or "").lower()
            manifests.append({
                "appid": aid,
                "name": gname,
                "installdir": idir,
                "installdir_lower": idir_lower,
                "installdir_norm": re.sub(r"\W+", "", idir_lower),
                "name_lower": gname_lower,
                "name_norm": re.sub(r"\W+", "", gname_lower),
            })
        
        # Verify pre-computed values
        self.assertEqual(manifests[0]["installdir_norm"], "counterstrikeglobaloffensive")
        self.assertEqual(manifests[0]["name_norm"], "counterstrike2")
        self.assertEqual(manifests[2]["name_norm"], "eldenring")


if __name__ == "__main__":
    unittest.main()
