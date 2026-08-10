"""Run reservation system for concurrent CLI processes. (v1.0.144)

Provides atomic filesystem-based allocation of unique run versions,
replacing the two separate scans (pipeline log scan + report output scan)
with a single atomic reservation step.
"""

import os
import re
from dataclasses import dataclass


@dataclass
class RunReservation:
    """Identity assigned to a single pipeline run."""

    log_ver: int
    log_path: str
    report_dir: str
    marker_path: str


class RunAllocator:
    """Atomically reserve a unique version number for a run."""

    def __init__(self, log_dir: str, news_dir: str, today: str):
        self.log_dir = log_dir
        self.news_dir = news_dir
        self.today = today

    def _find_max_log_ver(self) -> int:
        """Scan existing log files to determine the highest version."""
        if not os.path.isdir(self.log_dir):
            os.makedirs(self.log_dir, exist_ok=True)
            return 0

        pattern = re.compile(r"^run_log_" + re.escape(self.today) + r"_v(\d+)\.md$")
        max_ver = 0
        for entry in os.listdir(self.log_dir):
            m = pattern.search(entry)
            if m:
                max_ver = max(max_ver, int(m.group(1)))
        return max_ver

    def _find_max_reserved_ver(self) -> int:
        """Scan existing reservation markers to determine the highest claimed version."""
        if not os.path.isdir(self.log_dir):
            return 0

        pattern = re.compile(r"^\.run_reserved_" + re.escape(self.today) + r"_v?(\d+)$")
        max_ver = 0
        for entry in os.listdir(self.log_dir):
            m = pattern.search(entry)
            if m:
                max_ver = max(max_ver, int(m.group(1)))
        return max_ver

    def reserve(self) -> RunReservation:
        """Atomically reserve one run identity.

        Uses O_CREAT | O_EXCL on a marker file to guarantee exclusivity
        across concurrent processes.  On collision the version is
        incremented and retried.
        """
        os.makedirs(self.log_dir, exist_ok=True)

        # Determine starting version from both existing logs and markers
        max_ver = max(self._find_max_log_ver(), self._find_max_reserved_ver())
        ver = max_ver + 1

        while True:
            marker = os.path.join(self.log_dir, f".run_reserved_{self.today}_{ver:02d}")

            try:
                fd = os.open(marker, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            except FileExistsError:
                ver += 1
                continue

            os.close(fd)

            log_path = os.path.join(self.log_dir, f"run_log_{self.today}_v{ver:02d}.md")

            return RunReservation(
                log_ver=ver,
                log_path=log_path,
                report_dir=self.news_dir,
                marker_path=marker,
            )
