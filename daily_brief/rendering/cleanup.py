import logging
import os

logger = logging.getLogger(__name__)


def cleanup_old_files(output_dir, log_dir, max_log_versions):
    """Clean up old report and log files, keeping only max_log_versions most recent."""
    try:
        os.makedirs(output_dir, exist_ok=True)
        all_reports = [
            f for f in os.listdir(output_dir) if f.startswith("DailyBrief-") and f.endswith(".md")
        ]
        all_reports.sort(key=lambda x: os.path.getmtime(os.path.join(output_dir, x)), reverse=True)
        for old_report in all_reports[max_log_versions:]:
            os.remove(os.path.join(output_dir, old_report))
            logger.info(f"Removed old report: {old_report}")

        os.makedirs(log_dir, exist_ok=True)
        valid_log_files = sorted(
            [f for f in os.listdir(log_dir) if f.startswith("run_log_") and f.endswith(".md")],
            key=lambda x: os.path.getmtime(os.path.join(log_dir, x)),
            reverse=True,
        )
        for old_log in valid_log_files[max_log_versions:]:
            os.remove(os.path.join(log_dir, old_log))
            logger.info(f"Removed old log: {old_log}")
    except Exception as e:
        logger.warning(f"Could not cleanup old files: {e}")
