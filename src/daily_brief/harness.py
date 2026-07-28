"""
Daily Brief v1.0.13 — Test Harness Runner
==========================================
Runs the external Test_validate_run.py harness via subprocess.
"""

import logging
import os
import re
import subprocess
import sys

logger = logging.getLogger(__name__)


def run_test_harness(run_logfile, script_dir=None):
    """Run the external Test_validate_run.py harness against the latest output.

    Args:
        run_logfile: Path to the current run log file (e.g., "run_log_2026-07-26_v18.md")
        script_dir: Optional project root directory. Defaults to parent of src/daily_brief/
    """
    if script_dir is None:
        script_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    harness_script = os.path.join(script_dir, 'Test_validate_run.py')
    config_file = os.path.join(script_dir, 'config.yaml')

    if not os.path.exists(harness_script):
        logger.warning("Test harness script not found: %s", harness_script)
        return

    if not run_logfile:
        logger.warning("No run_logfile set — skipping test harness")
        return

    basename = os.path.basename(run_logfile)
    # Extract date and version from "run_log_2026-07-26_v18.md"
    match = re.match(r"run_log_(\d{4}-\d{2}-\d{2})_(v\d+)\.md$", basename)
    if not match:
        logger.warning("Cannot parse date/version from run log: %s", basename)
        return

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

        # Log the full output
        for line in result.stdout.strip().split('\n'):
            logger.info("[TEST HARNES] %s", line)
        if result.stderr.strip():
            for line in result.stderr.strip().split('\n'):
                logger.info("[TEST HARNES ERROR] %s", line)

        exit_code = result.returncode
        status_label = {0: "PASS", 1: "WARN", 2: "FAIL"}.get(exit_code, f"EXIT_{exit_code}")
        logger.info("Test harness finished: %s (exit code %d)", status_label, exit_code)
    except FileNotFoundError:
        logger.error("Test harness script not found at: %s", harness_script)
    except subprocess.TimeoutExpired:
        logger.error("Test harness timed out (30s)")
    except Exception as e:
        logger.error("Test harness error: %s", e)
