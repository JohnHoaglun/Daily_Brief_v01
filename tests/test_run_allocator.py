"""Tests for daily_brief/lifecycle.py — RunAllocator."""

import os

import pytest

from daily_brief.lifecycle import RunAllocator, RunReservation


@pytest.fixture()
def tmp_dir(tmp_path):
    """Return a real filesystem path (str) for temp directory."""
    return str(tmp_path)


@pytest.fixture()
def allocator(tmp_dir):
    log_dir = os.path.join(tmp_dir, "logs")
    news_dir = os.path.join(tmp_dir, "news")
    os.makedirs(log_dir, exist_ok=True)
    os.makedirs(news_dir, exist_ok=True)
    return RunAllocator(log_dir=log_dir, news_dir=news_dir, today="2026-01-15")


# ---------------------------------------------------------------------------
# test_reserve_produces_valid_reservation
# ---------------------------------------------------------------------------


def test_reserve_produces_valid_reservation(allocator):
    res = allocator.reserve()
    assert isinstance(res, RunReservation)
    assert res.log_ver == 1
    assert res.log_path == os.path.join(allocator.log_dir, "run_log_2026-01-15_v01.md")
    assert res.marker_path.startswith(allocator.log_dir)


# ---------------------------------------------------------------------------
# test_concurrent_reserves_distinct_versions
# ---------------------------------------------------------------------------


def test_concurrent_reserves_distinct_versions(allocator):
    r1 = allocator.reserve()
    r2 = allocator.reserve()
    assert r1.log_ver != r2.log_ver
    assert set([r1.log_ver, r2.log_ver]) == {1, 2}
    assert r1.marker_path != r2.marker_path


# ---------------------------------------------------------------------------
# test_marker_file_exists
# ---------------------------------------------------------------------------


def test_marker_file_exists(allocator):
    res = allocator.reserve()
    assert os.path.isfile(res.marker_path)
    assert os.path.getsize(res.marker_path) == 0  # marker is empty


# ---------------------------------------------------------------------------
# test_reserve_retries_on_collision
# ---------------------------------------------------------------------------


def test_reserve_retries_on_collision(allocator):
    # Pre-create the v01 marker
    preexisting = os.path.join(allocator.log_dir, ".run_reserved_2026-01-15_01")
    with open(preexisting, "w") as f:
        f.write("")

    res = allocator.reserve()
    assert res.log_ver == 2
    assert res.marker_path != preexisting


# ---------------------------------------------------------------------------
# test_reservations_pair_log_and_report_dir
# ---------------------------------------------------------------------------


def test_reservations_pair_log_and_report_dir(allocator):
    res = allocator.reserve()
    assert "run_log_" in res.log_path
    assert res.report_dir == allocator.news_dir
    assert os.path.isdir(res.report_dir)
