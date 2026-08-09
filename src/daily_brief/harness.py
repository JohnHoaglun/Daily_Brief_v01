"""
Daily Brief v1.0.117 — Test Harness Runner
===========================================
Runs the external Test_validate_run.py harness via subprocess.
"""

import logging
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class HarnessResult:
    """Typed result from test harness execution."""
    status: str  # "PASS", "WARN", "FAIL", "SKIPPED", "ERROR"
    message: str
    exit_code: Optional[int] = None
    stdout_lines: List[str] = field(default_factory=list)
    stderr_lines: List[str] = field(default_factory=list)


def run_test_harness(run_logfile, script_dir=None) -> HarnessResult:
    """Run the external Test_validate_run.py harness against the latest output.

    Args:
        run_logfile: Path to the current run log file (e.g., "run_log_2026-07-26_v18.md")
        script_dir: Optional project root directory. Defaults to parent of src/daily_brief/

    Returns:
        HarnessResult with typed status (PASS/WARN/FAIL/SKIPPED/ERROR)
    """
    if script_dir is None:
        script_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    harness_script = os.path.join(script_dir, 'Test_validate_run.py')
    config_file = os.path.join(script_dir, 'config.yaml')

    if not os.path.exists(harness_script):
        msg = f"Test harness script not found: {harness_script}"
        logger.warning(msg)
        return HarnessResult(status="SKIPPED", message=msg)

    if not run_logfile:
        msg = "No run_logfile set — skipping test harness"
        logger.warning(msg)
        return HarnessResult(status="SKIPPED", message=msg)

    basename = os.path.basename(run_logfile)
    # Extract date and version from "run_log_2026-07-26_v18.md"
    match = re.match(r"run_log_(\d{4}-\d{2}-\d{2})_(v\d+)\.md$", basename)
    if not match:
        msg = f"Cannot parse date/version from run log: {basename}"
        logger.warning(msg)
        return HarnessResult(status="SKIPPED", message=msg)

    run_date, run_version = match.group(1), match.group(2)

    logger.info("Running test harness for %s %s...", run_date, run_version)
    cmd = [
        sys.executable, harness_script,
        "--config", config_file,
        "--date", run_date,
        "--version", run_version,
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )

        stdout_lines = result.stdout.strip().split('\n') if result.stdout.strip() else []
        stderr_lines = result.stderr.strip().split('\n') if result.stderr.strip() else []

        # Log the full output
        for line in stdout_lines:
            logger.info("[TEST HARNES] %s", line)
        for line in stderr_lines:
            logger.info("[TEST HARNES ERROR] %s", line)

        exit_code = result.returncode
        status_label = {0: "PASS", 1: "WARN", 2: "FAIL"}.get(exit_code, f"EXIT_{exit_code}")
        logger.info("Test harness finished: %s (exit code %d)", status_label, exit_code)
        return HarnessResult(
            status=status_label,
            message=f"exit code {exit_code}",
            exit_code=exit_code,
            stdout_lines=stdout_lines,
            stderr_lines=stderr_lines,
        )
    except FileNotFoundError:
        msg = f"Test harness script not found at: {harness_script}"
        logger.error(msg)
        return HarnessResult(status="ERROR", message=msg)
    except subprocess.TimeoutExpired:
        msg = "Test harness timed out (30s)"
        logger.error(msg)
        return HarnessResult(status="ERROR", message=msg)
    except Exception as e:
        msg = f"Test harness error: {e}"
        logger.error(msg)
        return HarnessResult(status="ERROR", message=msg)
