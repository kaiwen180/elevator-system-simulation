import pytest

from elevator_sim.models import Passenger, Request, Result
from elevator_sim.stats import Spread, format_summary, spread, summarize


def make_passenger(pid, time, boarded, arrived, elevator):
    p = Passenger(Request(time=time, id=pid, source=1, dest=5), elevator=elevator)
    p.boarded_at = boarded
    p.arrived_at = arrived
    return p


def sample_result():
    passengers = [
        make_passenger("p1", 0, 0, 4, 0),
        make_passenger("p2", 1, 10, 20, 0),
        make_passenger("p3", 2, 2, 8, 1),
    ]
    positions = [[1, 1]] * 61
    return Result(passengers=passengers, positions=positions, events=[])


def test_spread_single_value():
    assert spread([7]) == Spread(min=7, max=7, mean=7.0, p50=7, p95=7)


def test_spread_nearest_rank():
    s = spread(list(range(1, 21)))
    assert s.p50 == 10
    assert s.p95 == 19
    assert s.mean == 10.5
    assert (s.min, s.max) == (1, 20)


def test_spread_unsorted_input():
    s = spread([9, 0, 0])
    assert (s.min, s.p50, s.p95, s.max) == (0, 0, 9, 9)
    assert s.mean == 3.0


def test_spread_empty_raises():
    with pytest.raises(ValueError):
        spread([])


def test_summarize_counts_and_spreads():
    summary = summarize(sample_result())
    assert summary.passengers == 3
    assert summary.time_units == 61
    assert summary.wait == spread([0, 9, 0])
    assert summary.travel == spread([4, 10, 6])
    assert summary.total == spread([4, 19, 6])
    assert summary.served_per_elevator == [2, 1]


def test_summarize_unarrived_raises():
    result = sample_result()
    result.passengers[0].arrived_at = None
    with pytest.raises(ValueError):
        summarize(result)


def test_format_summary_shape():
    text = format_summary(summarize(sample_result()))
    assert "Passengers: 3" in text
    assert "Time units: 61" in text
    for label in ("min", "mean", "p50", "p95", "max", "Wait", "Travel", "Total"):
        assert label in text
    assert "3.0" in text
    assert "Served per elevator: elevator1 2, elevator2 1" in text
