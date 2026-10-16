"""Traffic patterns, demand levels and profiles produce what they claim."""

from __future__ import annotations

import pytest

from elevator_sim.config import Config
from elevator_sim.traffic import Segment, daily_profile, generate

TYPICAL = Config(floors=20, elevators=4, capacity=10)


def share_from_lobby(requests):
    lobby = 0
    for r in requests:
        if r.source == 1:
            lobby += 1
    return lobby / len(requests)


def share_to_lobby(requests):
    lobby = 0
    for r in requests:
        if r.dest == 1:
            lobby += 1
    return lobby / len(requests)


def test_same_seed_gives_identical_output():
    segments = [Segment(200, 1.0, "interfloor")]
    assert generate(TYPICAL, segments, seed=7) == generate(TYPICAL, segments, seed=7)


def test_different_seeds_differ():
    segments = [Segment(200, 1.0, "interfloor")]
    assert generate(TYPICAL, segments, seed=1) != generate(TYPICAL, segments, seed=2)


@pytest.mark.parametrize("pattern", ["up-peak", "down-peak", "interfloor"])
def test_every_request_is_valid(pattern):
    requests = generate(TYPICAL, [Segment(300, 1.0, pattern)], seed=3)
    assert requests
    for r in requests:
        assert 1 <= r.source <= TYPICAL.floors
        assert 1 <= r.dest <= TYPICAL.floors
        assert r.source != r.dest
        assert 0 <= r.time < 300


def test_up_peak_mostly_leaves_the_lobby():
    requests = generate(TYPICAL, [Segment(3000, 1.0, "up-peak")], seed=11)
    assert 0.80 <= share_from_lobby(requests) <= 0.90


def test_down_peak_mostly_goes_to_the_lobby():
    requests = generate(TYPICAL, [Segment(3000, 1.0, "down-peak")], seed=11)
    assert 0.80 <= share_to_lobby(requests) <= 0.90


def test_interfloor_has_no_lobby_bias():
    requests = generate(TYPICAL, [Segment(3000, 1.0, "interfloor")], seed=11)
    # A random pair starts at the lobby 1 time in 20 on a 20-floor building.
    assert share_from_lobby(requests) < 0.10
    assert share_to_lobby(requests) < 0.10


@pytest.mark.parametrize("demand", [0.2, 1.0, 1.2])
def test_mean_arrivals_match_demand(demand):
    time_units = 5000
    requests = generate(TYPICAL, [Segment(time_units, demand, "interfloor")], seed=5)
    expected = demand * TYPICAL.handling_capacity
    assert abs(len(requests) / time_units - expected) <= 0.10 * expected


def test_zero_demand_gives_no_requests():
    assert generate(TYPICAL, [Segment(500, 0.0, "up-peak")], seed=1) == []


def test_ids_in_order_and_times_non_decreasing():
    requests = generate(TYPICAL, daily_profile(scale=50), seed=9)
    for i, r in enumerate(requests):
        assert r.id == f"p{i + 1}"
    for before, after in zip(requests, requests[1:]):
        assert before.time <= after.time


def test_segment_boundaries_are_respected():
    segments = [Segment(100, 1.0, "up-peak"), Segment(100, 0.0, "interfloor"), Segment(100, 1.0, "down-peak")]
    requests = generate(TYPICAL, segments, seed=4)
    first = [r for r in requests if r.time < 100]
    middle = [r for r in requests if 100 <= r.time < 200]
    last = [r for r in requests if 200 <= r.time < 300]
    assert len(first) + len(middle) + len(last) == len(requests)
    assert middle == []
    assert share_from_lobby(first) > 0.6
    assert share_to_lobby(last) > 0.6


def test_smallest_building_works():
    small = Config(floors=2, elevators=1, capacity=1)
    for pattern in ["up-peak", "down-peak", "interfloor"]:
        requests = generate(small, [Segment(2000, 1.0, pattern)], seed=2)
        assert requests
        for r in requests:
            assert {r.source, r.dest} == {1, 2}


def test_unknown_pattern_raises():
    with pytest.raises(ValueError):
        generate(TYPICAL, [Segment(10, 1.0, "sideways")], seed=1)


def test_negative_demand_raises():
    with pytest.raises(ValueError):
        generate(TYPICAL, [Segment(10, -0.1, "interfloor")], seed=1)


@pytest.mark.parametrize("duration", [0, -5])
def test_non_positive_duration_raises(duration):
    with pytest.raises(ValueError):
        generate(TYPICAL, [Segment(duration, 1.0, "interfloor")], seed=1)


def test_daily_profile_shape():
    profile = daily_profile(scale=30)
    assert len(profile) == 5
    assert sum(s.duration for s in profile) == 5 * 30
    assert [(s.demand, s.pattern) for s in profile] == [
        (0.2, "interfloor"),
        (1.2, "up-peak"),
        (0.5, "interfloor"),
        (1.0, "down-peak"),
        (0.2, "interfloor"),
    ]
    for s in profile:
        assert s.duration == 30


def test_daily_profile_default_scale():
    assert sum(s.duration for s in daily_profile()) == 500
