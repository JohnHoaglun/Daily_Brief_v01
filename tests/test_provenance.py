"""Unit tests for daily_brief/provenance.py."""

import os
import subprocess
from unittest import TestCase, mock

from daily_brief import provenance


class TestProvenance(TestCase):
    """Provenance module tests covering happy path, failures, and edge cases."""

    # -- Happy path: project repo has a valid git history -------------------

    def test_commit_sha_in_project_repo(self):
        sha = provenance.resolve_git_commit_sha(".")
        self.assertIsInstance(sha, str)
        self.assertEqual(len(sha), 7)

    def test_committed_at_in_project_repo(self):
        stamp = provenance.resolve_git_committed_at(".")
        self.assertIsInstance(stamp, str)
        self.assertNotIn(" ", stamp)  # ISO 8601 should not have spaces

    def test_author_name_in_project_repo(self):
        name = provenance.resolve_git_author_name(".")
        self.assertIsInstance(name, str)
        self.assertGreater(len(name), 0)

    def test_committer_name_in_project_repo(self):
        name = provenance.resolve_git_committer_name(".")
        self.assertIsInstance(name, str)
        self.assertGreater(len(name), 0)

    def test_all_functions_return_str_or_none(self):
        """Type guard: every resolved value is str | None."""
        for fn in (
            provenance.resolve_git_commit_sha,
            provenance.resolve_git_committed_at,
            provenance.resolve_git_author_name,
            provenance.resolve_git_committer_name,
        ):
            val = fn(".")
            self.assertIsInstance(val, (str, type(None)))

    # -- Failure cases: subprocess errors, non-git directories --------------

    @mock.patch("daily_brief.provenance.subprocess.run")
    def test_git_not_found_returns_none(self, mock_run):
        mock_run.side_effect = FileNotFoundError("git not in PATH")
        self.assertIsNone(provenance.resolve_git_commit_sha("/no/such/repo"))

    @mock.patch("daily_brief.provenance.subprocess.run")
    def test_not_a_directory_returns_none(self, mock_run):
        mock_run.side_effect = NotADirectoryError("epath")
        self.assertIsNone(provenance.resolve_git_committed_at("/not/a/dir"))

    @mock.patch("daily_brief.provenance.subprocess.run")
    def test_subprocess_nonzero_returncode(self, mock_run):
        mock_run.return_value = mock.Mock(
            returncode=128,
            stdout=b"",
            stderr=b"fatal: not a git repository",
        )
        self.assertIsNone(provenance.resolve_git_commit_sha("/empty/dir"))

    @mock.patch("daily_brief.provenance.subprocess.run")
    def test_subprocess_timeout_returns_none(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired("git", 5)
        self.assertIsNone(provenance.resolve_git_author_name("/slow/repo"))

    @mock.patch("daily_brief.provenance.subprocess.run")
    def test_generic_exception_returns_none(self, mock_run):
        mock_run.side_effect = OSError("something went wrong")
        self.assertIsNone(provenance.resolve_git_committer_name("/bad/repo"))

    def test_non_git_directory_returns_none(self):
        tmpdir = "/tmp"  # not a git repository
        self.assertIsNone(provenance.resolve_git_commit_sha(tmpdir))

    # -- Edge cases: stripped whitespace, empty output ----------------------

    @mock.patch("daily_brief.provenance.subprocess.run")
    def test_whitespace_stripped(self, mock_run):
        mock_run.return_value = mock.Mock(
            returncode=0,
            stdout=b" abc1234 \n",
            stderr=b"",
        )
        self.assertEqual(provenance.resolve_git_commit_sha("."), "abc1234")

    # -- No shell=True verification -----------------------------------------

    def test_no_shell_true_in_source(self):
        """Grep the source to confirm shell=False is always used."""
        source = open(provenance.__file__).read()
        self.assertNotIn("shell=True", source)

    def test_shell_false_explicit(self):
        """Confirm the keyword argument is present in the source."""
        source = open(provenance.__file__).read()
        self.assertIn("shell=False", source)

    # -- No email addresses leaked in output --------------------------------

    def test_author_name_no_email(self):
        name = provenance.resolve_git_author_name(".")
        self.assertIsInstance(name, str)
        self.assertNotIn("@", name)

    def test_committer_name_no_email(self):
        name = provenance.resolve_git_committer_name(".")
        self.assertIsInstance(name, str)
        self.assertNotIn("@", name)

    # -- No class, pure functions only --------------------------------------

    def test_module_is_functions_not_class(self):
        source = open(provenance.__file__).read()
        self.assertNotIn("class ", source)
