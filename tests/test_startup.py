"""
Tests for daily_brief.__main__.py setup_logging.
"""
import os
import sys
import tempfile
from unittest import TestCase

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import logging
from daily_brief.__main__ import setup_logging


class TestSetupLoggingCreatesDir(TestCase):
    def test_creates_missing_log_directory_and_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_dir = os.path.join(tmp, "nonexistent", "logs")
            self.assertFalse(os.path.isdir(log_dir))
            setup_logging(log_dir=log_dir)
            self.assertTrue(os.path.isdir(log_dir))
            self.assertTrue(os.path.isfile(os.path.join(log_dir, "daily_brief.log")))
            # Clean up root handlers to avoid leaking state
            for h in list(logging.root.handlers):
                logging.root.removeHandler(h)
