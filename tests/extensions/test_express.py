import pytest
from conftest import passenger

from elevator_sim.config import Config
from elevator_sim.extensions.express import express_bank, servable
from elevator_sim.invariants import assert_valid, violations
from elevator_sim.models import Elevator, Event, Passenger, Request, Result
from elevator_sim.scenarios import run_scenario, scenarios
from elevator_sim.scheduler import NAMES, make_scheduler
from elevator_sim.simulation import Simulation, eligible

BANK = express_bank(40, local=2, express=2, split=20)
CONFIG = Config(floors=40, elevators=4, capacity=10, served_floors=BANK)
LOW = frozenset(range(1, 21))
HIGH = frozenset({1} | set(range(21, 41)))
ALL = scenarios()
EVERY_FLOOR = "40f-4x10-demand100-up-peak-all-floors"
EXPRESS = "40f-4x10-demand100-up-peak-express"


def bank():
    return [Elevator(index=i, capacity=10) for i in range(4)]


# The layout


def test_express_bank_lists_the_local_elevators_then_the_express_ones():
    assert BANK == (LOW, LOW, HIGH, HIGH)


def test_by_default_every_elevator_serves_every_floor():
    config = Config()
    assert config.served_floors is None
    assert config.serves(0, 1, 20)


def test_serves_reads_the_layout():
    assert CONFIG.serves(0, 1, 20)
    assert not CONFIG.serves(0, 21)
    assert CONFIG.serves(2, 1, 40)
    assert not CONFIG.serves(2, 20)


@pytest.mark.parametrize("served, message", [
    ((LOW, LOW, HIGH), "one set per elevator"),
    ((LOW, LOW, HIGH, frozenset({1, 41})), "41"),
])
def test_a_bad_layout_is_refused(served, message):
    with pytest.raises(ValueError, match=message):
        Config(floors=40, elevators=4, served_floors=served)


# The shared filter


def test_the_filter_keeps_only_elevators_that_serve_both_floors():
    assert [e.index for e in eligible(CONFIG, passenger(1, 30), bank())] == [2, 3]
    assert [e.index for e in eligible(CONFIG, passenger(12, 1), bank())] == [0, 1]
    assert [e.index for e in eligible(CONFIG, passenger(25, 33), bank())] == [2, 3]


def test_with_no_layout_the_filter_keeps_every_elevator():
    elevators = bank()
    assert eligible(Config(floors=40), passenger(5, 30), elevators) == elevators


@pytest.mark.parametrize("name", NAMES)
def test_every_scheduler_assigns_only_elevators_that_serve_the_trip(name):
    scenario = ALL[EXPRESS]
    requests = scenario.requests()
    result = run_scenario(scenario, name)
    assert_valid(result, requests, scenario.config)
    for p in result.passengers:
        assert scenario.config.serves(p.elevator, p.source, p.dest), p.id


def test_a_trip_no_elevator_serves_is_an_error_naming_the_passenger():
    simulation = Simulation(CONFIG, make_scheduler("lowest-cost", CONFIG))
    with pytest.raises(ValueError, match="passenger a"):
        simulation.run([Request(0, "a", 5, 30)])


# The two scenarios


def test_the_two_layouts_share_their_passengers():
    every, express = ALL[EVERY_FLOOR], ALL[EXPRESS]
    assert every.config.served_floors is None
    assert express.config.served_floors == BANK
    assert every.requests() == express.requests()
    assert len(express.requests()) > 100


def test_servable_drops_only_trips_between_the_two_zones():
    requests = [Request(0, "a", 1, 30), Request(0, "b", 5, 30), Request(0, "c", 30, 25), Request(0, "d", 30, 5)]
    assert [r.id for r in servable(requests, CONFIG)] == ["a", "c"]


@pytest.mark.parametrize("name", [EVERY_FLOOR, EXPRESS])
def test_each_layout_obeys_every_rule_under_zoned(name):
    scenario = ALL[name]
    assert_valid(run_scenario(scenario, "zoned"), scenario.requests(), scenario.config)


# No elevator stops at a floor it does not serve


def test_the_rule_checker_catches_a_stop_at_a_floor_the_elevator_does_not_serve():
    config = Config(floors=5, elevators=1, served_floors=(frozenset({1, 3, 5}),))
    request = Request(0, "a", 1, 4)
    rider = Passenger(request, elevator=0, assigned_at=0, boarded_at=0, arrived_at=3)
    events = [Event(0, "a", 0, 1, "assigned"), Event(0, "a", 0, 1, "boarded"), Event(3, "a", 0, 4, "arrived")]
    found = "\n".join(violations(Result([rider], [[1], [2], [3], [4]], events), [request], config))
    assert "floor 4" in found
    assert "does not serve" in found


def test_no_express_elevator_stops_below_the_split():
    scenario = ALL[EXPRESS]
    result = run_scenario(scenario, "lowest-cost")
    stops = {e.floor for e in result.events if e.elevator >= 2 and e.kind != "assigned"}
    assert 1 in stops
    assert stops.isdisjoint(range(2, 21))
    for event in result.events:
        assert scenario.config.serves(event.elevator, event.floor), event


def test_no_elevator_pauses_at_a_floor_it_does_not_serve():
    scenario = ALL[EXPRESS]
    result = run_scenario(scenario, "lowest-cost")
    for before, after in zip(result.positions, result.positions[1:]):
        for index, floor in enumerate(before):
            if floor == after[index]:
                assert scenario.config.serves(index, floor), (index, floor)
