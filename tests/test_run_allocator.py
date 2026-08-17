"""Reduced: basic allocation and one collision case."""

import os

import pytest

from daily_brief.lifecycle import RunAllocator, RunReservation


@pytest.fixture()
def tmp_dir(tmp_path):
    return str(tmp_path)


@pytest.fixture()
def allocator(tmp_dir):
    log_dir = os.path.join(tmp_dir, "logs")
    news_dir = os.path.join(tmp_dir, "news")
    os.makedirs(log_dir, exist_ok=True)
    os.makedirs(news_dir, exist_ok=True)
    return RunAllocator(log_dir=log_dir, news_dir=news_dir, today="2026-01-15")


def test_reserve_produces_valid_reservation(allocator):
    res = allocator.reserve()
    assert isinstance(res, RunReservation)
    assert res.log_ver == 1
    assert res.log_path == os.path.join(allocator.log_dir, "run_log_2026-01-15_v01.md")


def test_concurrent_reserves_distinct_versions(allocator):
    r1 = allocator.reserve()
    r2 = allocator.reserve()
    assert r1.log_ver != r2.log_ver
    assert set([r1.log_ver, r2.log_ver]) == {1, 2}


def test_reserve_retries_on_collision(allocator):
    preexisting = os.path.join(allocator.log_dir, ".run_reserved_2026-01-15_01")
    with open(preexisting, "w") as f:
        f.write("")

    res = allocator.reserve()
    assert res.log_ver == 2
    assert res.marker_path != preexisting


def test_marker_file_exists(allocator):
    res = allocator.reserve()
    assert os.path.isfile(res.marker_path)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
