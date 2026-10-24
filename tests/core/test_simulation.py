import pytest

from elevator_sim.core.config import Config
from elevator_sim.benchmark.schedulers import SCHEDULERS, make_scheduler
from elevator_sim.benchmark.invariants import assert_valid
from elevator_sim.core.models import Event, Request
from elevator_sim.core.simulation import Simulation
from elevator_sim.benchmark.traffic import Segment, generate


def run(config, requests, scheduler="lowest-cost", max_time_units=1_000_000):
    """Run the simulation and check every invariant before handing back the result."""
    result = Simulation(config, make_scheduler(scheduler, config)).run(requests, max_time_units)
    assert_valid(result, requests, config)
    return result


def times(result):
    """(wait, total) for each passenger, keyed by id."""
    return {p.id: (p.wait, p.total) for p in result.passengers}


# Worked examples with exact times


def test_one_passenger_from_the_lobby_to_floor_5():
    result = run(Config(floors=5, elevators=1), [Request(0, "p1", 1, 5)])
    assert times(result) == {"p1": (0, 4)}
    assert result.positions == [[1], [2], [3], [4], [5]]


def test_one_passenger_from_floor_5_to_the_lobby():
    result = run(Config(floors=5, elevators=1), [Request(0, "p1", 5, 1)])
    assert times(result) == {"p1": (4, 8)}


def test_the_spec_sample_with_two_elevators_and_60_floors():
    config = Config(floors=60, elevators=2, dwell_time=0)
    requests = [
        Request(0, "passenger1", 1, 51),
        Request(0, "passenger2", 1, 37),
        Request(10, "passenger3", 20, 1),
    ]
    result = run(config, requests)
    assert [p.elevator for p in result.passengers] == [0, 0, 1]
    assert times(result) == {"passenger1": (0, 50), "passenger2": (0, 36), "passenger3": (19, 38)}
    assert result.time_units == 51


def test_dwell_time_two_holds_the_elevator_at_the_lobby():
    result = run(Config(floors=5, elevators=1, dwell_time=2), [Request(0, "p1", 1, 3)])
    p1 = result.passengers[0]
    assert (p1.boarded_at, p1.arrived_at) == (0, 4)
    assert result.positions == [[1], [1], [1], [2], [3]]


def test_capacity_one_serves_two_lobby_passengers_one_at_a_time():
    config = Config(floors=5, elevators=1, capacity=1)
    result = run(config, [Request(0, "a", 1, 3), Request(0, "b", 1, 5)])
    a, b = result.passengers
    assert (a.boarded_at, a.arrived_at) == (0, 2)
    assert (b.boarded_at, b.arrived_at) == (4, 8)


def test_no_requests_gives_one_row_and_no_events():
    result = run(Config(elevators=3), [])
    assert result.positions == [[1, 1, 1]]
    assert result.events == []
    assert result.passengers == []


# The clock


def test_passengers_come_back_in_input_order():
    requests = [Request(3, "b", 4, 1), Request(0, "a", 1, 2)]
    result = run(Config(floors=5, elevators=2), requests)
    assert [p.id for p in result.passengers] == ["b", "a"]


def test_assignment_records_the_elevator_time_and_event():
    result = run(Config(floors=5, elevators=1), [Request(0, "p1", 3, 5)])
    p1 = result.passengers[0]
    assert (p1.elevator, p1.assigned_at) == (0, 0)
    assert result.events[0] == Event(0, "p1", 0, 3, "assigned")


def test_arrivals_are_logged_before_boardings_in_the_same_time_unit():
    result = run(Config(floors=5, elevators=1), [Request(0, "a", 1, 3), Request(0, "b", 3, 5)])
    at_two = [(e.kind, e.passenger) for e in result.events if e.time == 2]
    assert at_two == [("arrived", "a"), ("boarded", "b")]


def test_a_request_at_time_5_is_assigned_at_5():
    result = run(Config(floors=5, elevators=2), [Request(5, "p1", 2, 4)])
    p1 = result.passengers[0]
    assert p1.assigned_at == 5
    assert result.events[0].time == 5


class SpyScheduler:
    """Round robin that records every elevator's passengers at each call."""

    name = "spy"

    def __init__(self):
        self.calls = []

    def assign(self, passenger, elevators, now):
        seen = [passenger]
        for elevator in elevators:
            seen += elevator.inside + elevator.waiting
        self.calls.append((now, seen))
        return len(self.calls) % len(elevators)


def test_the_scheduler_never_sees_a_later_request():
    config = Config(floors=10, elevators=2)
    requests = generate(config, [Segment(50, 0.8, "interfloor")], seed=3)
    spy = SpyScheduler()
    result = Simulation(config, spy).run(requests)
    assert_valid(result, requests, config)
    assert len(spy.calls) == len(requests)
    for now, seen in spy.calls:
        for p in seen:
            assert p.request.time <= now


@pytest.mark.parametrize("source, dest", [(0, 5), (3, 21)])
def test_floors_outside_the_building_raise(source, dest):
    with pytest.raises(ValueError, match="floor"):
        Simulation(Config(floors=20), make_scheduler("round-robin", Config())).run([Request(0, "p1", source, dest)])


def test_max_time_units_raises():
    config = Config(floors=5, elevators=1)
    with pytest.raises(RuntimeError, match="3"):
        Simulation(config, make_scheduler("lowest-cost", config)).run([Request(0, "p1", 1, 5)], max_time_units=3)


def test_watch_sees_every_time_unit_after_the_step():
    seen = []
    config = Config(floors=5, elevators=1)
    watch = lambda now, elevators, events: seen.append((now, elevators[0].floor, len(events)))
    result = Simulation(config, make_scheduler("lowest-cost", config)).run([Request(0, "p1", 1, 3)], watch=watch)
    assert seen == [(0, 2, 2), (1, 3, 2), (2, 3, 3)]
    assert result.time_units == 3


def test_max_time_units_exactly_enough_finishes():
    result = run(Config(floors=5, elevators=1), [Request(0, "p1", 1, 5)], max_time_units=5)
    assert result.time_units == 5


# A generated run under every scheduler


@pytest.mark.slow
@pytest.mark.parametrize("pattern", ["interfloor", "up-peak"])
def test_lowest_cost_on_the_largest_bank_at_full_demand(pattern):
    config = Config(floors=5, elevators=10, capacity=20)
    requests = generate(config, [Segment(200, 1.0, pattern)], seed=1)
    result = run(config, requests)
    assert len(result.passengers) == len(requests)


@pytest.mark.parametrize("name", SCHEDULERS + ("lowest-cost-nocap",))
def test_every_scheduler_finishes_a_generated_run(name):
    config = Config()
    requests = generate(config, [Segment(300, 0.8, "interfloor")], seed=1)
    result = run(config, requests, scheduler=name)
    assert len(result.passengers) == len(requests)
    assert result.time_units >= 300
