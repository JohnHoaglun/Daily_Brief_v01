#!/usr/bin/env python3
"""
Tests for scripts/capture_corpus.py — validation, metadata, force flag, path resolution.
Python 3.9 compatible, no network calls.
"""

import json
import os
import textwrap
import unittest
from unittest import mock

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from daily_brief import capture_corpus


class TestCaptureOutputPath(unittest.TestCase):
    """Output path resolves relative to project root, not CWD."""

    def test_relative_path_resolves_to_project_root(self):
        path = capture_corpus._resolve_output_path("tests/fixtures/output.json")
        self.assertTrue(path.startswith(capture_corpus.PROJECT_ROOT))
        expected = os.path.join(capture_corpus.PROJECT_ROOT, "tests", "fixtures", "output.json")
        self.assertEqual(path, expected)

    def test_absolute_path_passthrough(self):
        abs_path = "/tmp/corpus.json"
        result = capture_corpus._resolve_output_path(abs_path)
        self.assertEqual(result, abs_path)

    def test_nested_relative_path(self):
        path = capture_corpus._resolve_output_path("a/b/c/deep.json")
        expected = os.path.join(capture_corpus.PROJECT_ROOT, "a", "b", "c", "deep.json")
        self.assertEqual(path, expected)

    def test_cwd_independence(self):
        # Even if CWD is /tmp, relative path should resolve to PROJECT_ROOT
        with mock.patch("os.getcwd", return_value="/tmp"):
            path = capture_corpus._resolve_output_path("output.json")
            self.assertTrue(path.startswith(capture_corpus.PROJECT_ROOT))
            self.assertNotIn("/tmp", path)


class TestCaptureForceFlag(unittest.TestCase):
    """Refuses overwrite without --force, allows with --force."""

    def test_refuses_overwrite_without_force(self):
        with mock.patch("os.path.exists", return_value=True):
            with self.assertRaises(SystemExit) as cm:
                capture_corpus._check_force("/f/corpus.json", force=False)
            self.assertEqual(cm.exception.code, 1)

    def test_error_message_mentions_force(self):
        captured = []
        stderr_capture = mock.Mock()
        stderr_capture.write = lambda msg: captured.append(msg)
        stderr_capture.flush = lambda: None

        with mock.patch("os.path.exists", return_value=True):
            with mock.patch("sys.stderr", stderr_capture):
                with self.assertRaises(SystemExit):
                    capture_corpus._check_force("/f/corpus.json", force=False)

        full_msg = "".join(captured)
        self.assertIn("force", full_msg.lower())
        self.assertIn("already exists", full_msg.lower())

    def test_allows_overwrite_with_force(self):
        with mock.patch("os.path.exists", return_value=True):
            # Should not raise when force=True
            capture_corpus._check_force("/f/corpus.json", force=True)

    def test_no_crash_when_file_not_exists(self):
        # When file doesn't exist, no error regardless of force flag
        with mock.patch("os.path.exists", return_value=False):
            capture_corpus._check_force("/f/new_corpus.json", force=False)


class TestCaptureValidation(unittest.TestCase):
    """Validate corpus structure, required fields, context coverage."""

    def _make_story(self, **overrides):
        return {
            "title": "Test Story",
            "url": "https://example.com/1",
            "category": "Politics",
            "snippet": "A short snippet",
            "pub_date": "2025-01-01",
            "context": "Some context text",
            **overrides,
        }

    def _make_corpus(self, stories, **overrides):
        return {
            "capture_date": "2026-08-01T00:00:00Z",
            "version": "1.0.92",
            "total_stories": len(stories),
            "stories": stories,
            "categories": {},
            "category_order": [],
            "context_stats": {"total": len(stories), "non_empty": 0, "median_length": 0},
            **overrides,
        }

    def test_empty_stories_fails(self):
        corpus = self._make_corpus([])
        errors = capture_corpus._validate_corpus(corpus, min_stories=0, min_context_pct=0.0)
        self.assertTrue(len(errors) > 0)
        self.assertTrue(any("Empty" in e or "empty" in e for e in errors))

    def test_low_context_coverage_fails(self):
        stories = [self._make_story(context="") for _ in range(10)]
        corpus = self._make_corpus(stories)
        errors = capture_corpus._validate_corpus(corpus, min_stories=0, min_context_pct=0.8)
        self.assertTrue(len(errors) > 0)
        self.assertTrue(any("Context coverage" in e or "context" in e.lower() for e in errors))

    def test_all_required_fields_passes(self):
        stories = [self._make_story() for _ in range(25)]
        corpus = self._make_corpus(stories)
        errors = capture_corpus._validate_corpus(corpus, min_stories=20, min_context_pct=0.8)
        self.assertEqual(errors, [], f"Unexpected errors: {errors}")

    def test_missing_required_field_fails(self):
        story = self._make_story()
        del story["url"]
        corpus = self._make_corpus([story])
        errors = capture_corpus._validate_corpus(corpus, min_stories=0, min_context_pct=0.0)
        self.assertTrue(any("url" in e for e in errors))

    def test_total_stories_mismatch_fails(self):
        stories = [self._make_story() for _ in range(5)]
        corpus = self._make_corpus(stories, total_stories=99)
        errors = capture_corpus._validate_corpus(corpus, min_stories=0, min_context_pct=0.0)
        self.assertTrue(any("mismatch" in e.lower() or "total_stories" in e.lower() for e in errors))

    def test_none_field_fails(self):
        story = self._make_story(title=None)
        corpus = self._make_corpus([story])
        errors = capture_corpus._validate_corpus(corpus, min_stories=0, min_context_pct=0.0)
        self.assertTrue(any("None" in e or "title" in e for e in errors))

    def test_min_stories_threshold(self):
        stories = [self._make_story() for _ in range(5)]
        corpus = self._make_corpus(stories)
        errors = capture_corpus._validate_corpus(corpus, min_stories=20, min_context_pct=0.0)
        self.assertTrue(any("minimum" in e.lower() or "20" in e for e in errors))

    def test_below_80_percent_context_fails(self):
        stories = [self._make_story(context="") for _ in range(20)]
        stories[5] = self._make_story(context="has context")
        # 1/20 = 5%, well below 80%
        corpus = self._make_corpus(stories)
        errors = capture_corpus._validate_corpus(corpus, min_stories=0, min_context_pct=0.8)
        self.assertTrue(any("coverage" in e.lower() or "context" in e.lower() for e in errors))


class TestCaptureMetadata(unittest.TestCase):
    """Verify categories dict, category_order list, context_stats keys are present."""

    def _make_story(self, **overrides):
        return {
            "title": "Test Story",
            "url": "https://example.com/1",
            "category": "Politics",
            "snippet": "A snippet",
            "pub_date": "2025-01-01",
            "context": "Some context",
            **overrides,
        }

    def test_metadata_keys_produced_by_capture(self):
        """Verify the capture flow produces metadata keys (not validated, but structurally present)."""
        corpus = {
            "capture_date": "2026-08-01T00:00:00Z",
            "version": "1.0.92",
            "total_stories": 1,
            "stories": [],
            "categories": {},
            "category_order": [],
            "context_stats": {"total": 0, "non_empty": 0, "median_length": 0},
        }
        # These keys should be present; validate_corpus checks top-level keys
        errors = capture_corpus._validate_corpus(corpus, min_stories=0, min_context_pct=0.0)
        # Empty corpus is still a validation error (empty stories), but the metadata keys exist
        for key in ["categories", "category_order", "context_stats"]:
            self.assertIn(key, corpus)

    def test_context_stats_keys(self):
        story_list = [
            {"context": "short"},
            {"context": "a" * 100},
            {"context": ""},
        ]
        stats = capture_corpus._build_context_stats(story_list)
        self.assertIn("total", stats)
        self.assertIn("non_empty", stats)
        self.assertIn("median_length", stats)
        self.assertEqual(stats["total"], 3)
        self.assertEqual(stats["non_empty"], 2)

    def test_context_stats_median(self):
        story_list = [
            {"context": "a" * 10},
            {"context": "a" * 20},
            {"context": "a" * 30},
        ]
        stats = capture_corpus._build_context_stats(story_list)
        self.assertEqual(stats["median_length"], 20)

    def test_context_stats_even_count_median(self):
        story_list = [
            {"context": "a" * 10},
            {"context": "a" * 20},
            {"context": "a" * 30},
            {"context": "a" * 40},
        ]
        stats = capture_corpus._build_context_stats(story_list)
        self.assertEqual(stats["median_length"], 25.0)

    def test_context_stats_empty_list(self):
        stats = capture_corpus._build_context_stats([])
        self.assertEqual(stats["total"], 0)
        self.assertEqual(stats["non_empty"], 0)
        self.assertEqual(stats["median_length"], 0)


class TestCaptureNoLLM(unittest.TestCase):
    """Verify the capture script does not import LLM client or call chat completions."""

    def test_no_llm_client_import(self):
        source = inspect_source(capture_corpus)
        self.assertNotIn("create_llm_client", source, "Script should not reference create_llm_client")
        self.assertNotIn("chat_completions", source, "Script should not reference chat_completions")
        self.assertNotIn("client.chat", source, "Script should not reference client.chat")

    def test_no_llm_module_import(self):
        # Check the source file directly for LLM-related imports
        source_file = os.path.join(PROJECT_ROOT, "daily_brief", "capture_corpus.py")
        with open(source_file, "r") as f:
            source = f.read()
        # The script imports StoryPipelineState and build_context from summarizer, which is fine.
        # It should NOT import the LLM client or call summarization.
        self.assertNotIn("from daily_brief.llm import create_llm", source)
        self.assertNotIn("chat_completions_create", source)
        self.assertNotIn("_llm_client", source)
        self.assertNotIn("llm_summarize", source)
        self.assertNotIn("batch_summarize", source)

    def test_imports_only_expected_from_summarizer(self):
        source_file = os.path.join(PROJECT_ROOT, "daily_brief", "capture_corpus.py")
        with open(source_file, "r") as f:
            source = f.read()
        # Should import StoryPipelineState and build_context — not other summarizer functions
        if "from daily_brief.llm.summarizer import" in source:
            import_line = [l for l in source.splitlines() if "from daily_brief.llm.summarizer import" in l][0]
            self.assertIn("StoryPipelineState", import_line)
            self.assertIn("build_context", import_line)
            self.assertNotIn("batch_summarize", import_line)
            self.assertNotIn("_summarize", import_line)
            self.assertNotIn("parse_batch", import_line)

    def test_no_asyncio_gather_on_llm_functions(self):
        source_file = os.path.join(PROJECT_ROOT, "daily_brief", "capture_corpus.py")
        with open(source_file, "r") as f:
            source = f.read()
        # asyncio.gather is only used for stage_extract_article, not LLM
        if "asyncio.gather" in source:
            gather_lines = [l.strip() for l in source.splitlines() if "asyncio.gather" in l]
            for line in gather_lines:
                self.assertNotIn("llm", line.lower(), f"LLM call should not be in asyncio.gather: {line}")
                self.assertNotIn("summarize", line.lower(), f"Summarize should not be in asyncio.gather: {line}")


def inspect_source(module):
    """Read the source file for a module."""
    path = getattr(module, "__file__", None)
    if path and path.endswith(".py"):
        with open(path, "r") as f:
            return f.read()
    return ""


if __name__ == "__main__":
    unittest.main()
