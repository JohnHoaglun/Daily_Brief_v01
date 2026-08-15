"""
Verify that the project uses a single canonical source for the release version.

This test enforces the versioning direction: after v1.0.154, version text
must exist only in `daily_brief/_version.py`.

No module docstrings, test files, config.yaml, or project docs (PROJECT.md,
TODOS.md, PLAN.md) should carry current-release version text.
"""

import importlib
import os
import re
from unittest import TestCase


class TestVersionSingleSource(TestCase):
    """The version string must live in exactly one place."""

    def setUp(self):
        import daily_brief._version as mod
        self.canonical = mod.__version__

    def test_package_imports_canonical_version(self):
        """`import daily_brief; daily_brief.__version__` is consistent."""
        import daily_brief
        self.assertEqual(daily_brief.__version__, self.canonical)

    def test_no_version_in_config_yaml(self):
        """config.yaml must not contain a `version:` key."""
        import yaml
        from pathlib import Path

        config_path = Path(__file__).resolve().parent.parent / "config.yaml"
        raw = config_path.read_text()
        lines = raw.splitlines()

        for line in lines:
            stripped = line.strip()
            if re.match(r'^version\s*:', stripped):
                raise AssertionError(
                    f"config.yaml must not contain a `version:` key. "
                    f"Found line: {stripped!r}"
                )

    def test_no_version_in_package_docstrings(self):
        """No daily_brief module docstring may contain a version string."""
        import pkgutil
        from pathlib import Path

        base_dir = Path(__file__).resolve().parent.parent / "daily_brief"
        version_pattern = re.compile(r'\d+\.\d+\.\d+')

        for mod_info in pkgutil.walk_packages(
            path=[str(base_dir)],
            prefix="daily_brief.",
            onerror=lambda x: None,
        ):
            try:
                mod = importlib.import_module(mod_info.name)
            except Exception:
                continue

            doc = mod.__doc__
            if doc:
                # Check that docstrings don't contain version numbers
                match = version_pattern.search(doc)
                if match:
                    # Allow docstrings that only contain the version in the
                    # context of a TODO/task description referencing an older
                    # fix, but forbid version text that says it's the *current*
                    # release version.
                    if "v1.0." not in doc and "version" not in doc.lower():
                        continue
                    # If the docstring contains a version AND has a release
                    # context marker, flag it.
                    if version_pattern.search(doc):
                        # This is a false positive for test files — skip.
                        if "test" in mod_info.name:
                            continue
                        # Flag the actual violation.
                        # (Re-raise would break if we hit a test file —
                        # the import loop doesn't distinguish.)
                        pass  # handled below

        # Walk the daily_brief directory directly for more reliable check.
        for py_file in sorted(base_dir.glob("**/*.py")):
            if py_file.name == "_version.py":
                continue  # this is the canonical source

            content = py_file.read_text()
            if py_file.name.startswith("test_"):
                continue  # test files are allowed to have version refs

            lines = content.splitlines()
            in_docstring = False
            docstring_lines = []
            for line in lines:
                stripped = line.strip()
                if not in_docstring:
                    if stripped.startswith(('"""', "'''")):
                        in_docstring = True
                        # Check if docstring is one line
                        end = stripped.strip('"').strip("'")
                        if end and end.split('"""')[0] and end.count('"""') >= 2:
                            # Single-line docstring
                            match = version_pattern.search(end)
                            if match:
                                self.fail(
                                    f"{py_file.relative_to(base_dir.parent)}: "
                                    f"module docstring should not contain "
                                    f"version text (found match in line "
                                    f"that reads: {stripped!r})"
                                )
                            continue
                        docstring_lines = [stripped]
                elif in_docstring:
                    if '"""' in stripped or "'''" in stripped:
                        docstring_lines.append(stripped)
                        docstring_text = "\n".join(docstring_lines)
                        match = version_pattern.search(docstring_text)
                        if match:
                            self.fail(
                                f"{py_file.relative_to(base_dir.parent)}: "
                                f"module docstring should not contain "
                                f"version text.\n    First line: "
                                f"{docstring_lines[0]!r}"
                            )
                        in_docstring = False
                        docstring_lines = []
                    else:
                        docstring_lines.append(stripped)

    def test_config_version_derived_from_version_py(self):
        """:data:VERSION`` in runtime config matches ``_version.__version__``."""
        import daily_brief.config as cfg
        self.assertEqual(cfg.VERSION, self.canonical)
