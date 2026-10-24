import copy

import pytest
from conftest import passenger

from elevator_sim.core import scheduler as scheduler_module
from elevator_sim.core.config import Config
from elevator_sim.core.direction import run_until_idle
from elevator_sim.core.models import Direction, Elevator
from elevator_sim.core.scheduler import LowestCost, NearestCar, RoundRobin, floors_to_reach
from elevator_sim.benchmark.schedulers import make_scheduler


def make_elevator(index=0, floor=1, direction=Direction.IDLE, capacity=10, inside=(), waiting=()):
    return Elevator(index=index, capacity=capacity, floor=floor, direction=direction,
               inside=list(inside), waiting=list(waiting))


def passenger_inside(source, dest, boarded_at=0, time=0, id="r"):
    p = passenger(source, dest, time=time, id=id)
    p.boarded_at = boarded_at
    return p


# Round robin


def test_round_robin_cycles_through_the_elevators():
    config = Config(elevators=3)
    scheduler = RoundRobin(config)
    elevators = [make_elevator(index=i) for i in range(3)]
    picks = [scheduler.assign(passenger(1, 5, id=f"p{n}"), elevators, 0) for n in range(4)]
    assert picks == [0, 1, 2, 0]


# Nearest car


def test_nearest_car_picks_the_closer_idle_elevator():
    elevators = [make_elevator(index=0, floor=1), make_elevator(index=1, floor=10)]
    assert NearestCar(Config(elevators=2)).assign(passenger(8, 12), elevators, 0) == 1


def test_nearest_car_tie_goes_to_the_lowest_index():
    elevators = [make_elevator(index=0, floor=5), make_elevator(index=1, floor=11)]
    assert NearestCar(Config(elevators=2)).assign(passenger(8, 12), elevators, 0) == 0


def test_floors_to_reach_an_idle_elevator():
    assert floors_to_reach(make_elevator(floor=5), passenger(9, 12)) == 4
    assert floors_to_reach(make_elevator(floor=5), passenger(2, 12)) == 3


def test_floors_to_reach_a_elevator_moving_toward_the_passenger():
    up = make_elevator(floor=5, direction=Direction.UP, waiting=[passenger(12, 14, id="a")])
    down = make_elevator(floor=10, direction=Direction.DOWN, waiting=[passenger(2, 1, id="a")])
    assert floors_to_reach(up, passenger(9, 12)) == 4
    assert floors_to_reach(down, passenger(4, 1)) == 6


def test_floors_to_reach_a_elevator_moving_away_from_the_passengers_direction():
    up = make_elevator(floor=5, direction=Direction.UP, waiting=[passenger(12, 14, id="a")])
    down = make_elevator(floor=10, direction=Direction.DOWN, waiting=[passenger(2, 1, id="a")])
    assert floors_to_reach(up, passenger(9, 1)) == (12 - 5) + (12 - 9)
    assert floors_to_reach(down, passenger(6, 15)) == (10 - 2) + (6 - 2)


def test_floors_to_reach_a_passenger_behind_the_elevator_going_the_same_way():
    up = make_elevator(floor=5, direction=Direction.UP, waiting=[passenger(12, 14, id="a")])
    down = make_elevator(floor=10, direction=Direction.DOWN, waiting=[passenger(2, 1, id="a")])
    assert floors_to_reach(up, passenger(3, 9)) == (12 - 5) + (12 - 3) + (3 - 3)
    assert floors_to_reach(down, passenger(14, 11)) == (10 - 2) + (14 - 2) + (14 - 14)


# Lowest cost


def test_lowest_cost_picks_the_elevator_that_adds_least():
    config = Config(elevators=2)
    elevators = [make_elevator(index=0, floor=1), make_elevator(index=1, floor=10)]
    q = passenger(8, 12, id="q")
    scheduler = LowestCost(config)
    assert scheduler.incremental_cost(elevators[0], q, 0) == 11
    assert scheduler.incremental_cost(elevators[1], q, 0) == 6
    assert scheduler.assign(q, elevators, 0) == 1


def detour_elevators():
    """Elevator 0 is one floor from Q with five passengers inside; elevator 1 is idle two floors away."""
    inside = [passenger_inside(1, 10, id=f"r{n}") for n in range(5)]
    busy = make_elevator(index=0, floor=2, direction=Direction.UP, inside=inside)
    idle = make_elevator(index=1, floor=5)
    return [busy, idle]


def test_lowest_cost_prefers_an_idle_elevator_over_a_detour_that_delays_passengers_inside():
    config = Config(floors=20, elevators=2, dwell_time=2)
    elevators = detour_elevators()
    q = passenger(3, 4, id="q")
    scheduler = LowestCost(config)
    assert NearestCar(config).assign(q, elevators, 0) == 0
    assert scheduler.incremental_cost(elevators[0], q, 0) == 4 + 5 * 4
    assert scheduler.incremental_cost(elevators[1], q, 0) == 5
    assert scheduler.assign(q, elevators, 0) == 1


def test_max_wait_changes_the_choice():
    config = Config(floors=20, elevators=2, dwell_time=2)
    inside = [passenger_inside(1, 10, id=f"r{n}") for n in range(5)]
    far = make_elevator(index=0, floor=20)
    busy = make_elevator(index=1, floor=2, direction=Direction.UP, inside=inside)
    elevators = [far, busy]
    q = passenger(3, 4, id="q")
    nocap = LowestCost(config, max_wait=None)
    capped = LowestCost(config, max_wait=10)
    assert nocap.incremental_cost(far, q, 0) == 20
    assert nocap.incremental_cost(busy, q, 0) == 24
    assert nocap.assign(q, elevators, 0) == 0
    assert capped.incremental_cost(far, q, 0) == 20 + 1000 * (17 - 10)
    assert capped.assign(q, elevators, 0) == 1


def test_default_max_wait_comes_from_the_config():
    config = Config(floors=20)
    assert LowestCost(config).max_wait == 57
    assert LowestCost(config, max_wait=None).max_wait is None


def explainer_elevators():
    """Elevator A at 2 going up to fetch P; elevator B at 13 going up with one passenger inside to 18."""
    p = passenger(10, 2, time=0, id="P")
    elevator_a = make_elevator(index=0, floor=2, direction=Direction.UP, waiting=[p])
    elevator_b = make_elevator(index=1, floor=13, direction=Direction.UP, inside=[passenger_inside(1, 18, id="R")])
    return [elevator_a, elevator_b]


def test_explainer_example_nearest_car_picks_a():
    elevators = explainer_elevators()
    q = passenger(9, 16, time=1, id="Q")
    assert NearestCar(Config(floors=20, elevators=2)).assign(q, elevators, 1) == 0


def test_explainer_example_lowest_cost_picks_b():
    config = Config(floors=20, elevators=2, dwell_time=0)
    elevators = explainer_elevators()
    q = passenger(9, 16, time=1, id="Q")
    scheduler = LowestCost(config)
    assert scheduler.incremental_cost(elevators[0], q, 1) == 26
    assert scheduler.incremental_cost(elevators[1], q, 1) == 21
    assert scheduler.assign(q, elevators, 1) == 1


def test_a_trial_allocation_that_hits_its_limit_costs_infinity(monkeypatch):
    monkeypatch.setattr(scheduler_module, "trial_limit", lambda elevator, config: 1)
    scheduler = LowestCost(Config(floors=20, elevators=1))
    assert scheduler.incremental_cost(make_elevator(floor=1), passenger(8, 12, id="q"), 0) == float("inf")


def test_trial_limit_is_longer_than_a_real_route():
    config = Config(floors=20, elevators=1, capacity=1, dwell_time=2)
    waiting = [passenger(20, 1, id=f"w{n}") for n in range(5)]
    elevator = make_elevator(floor=1, capacity=1, waiting=waiting)
    assert run_until_idle(elevator, 0, config, scheduler_module.trial_limit(elevator, config)) is True


# No scheduler changes an elevator


@pytest.mark.parametrize("name", ["round-robin", "nearest-car", "lowest-cost", "lowest-cost-nocap"])
def test_schedulers_do_not_change_elevators(name):
    config = Config(floors=20, elevators=2)
    elevators = explainer_elevators()
    q = passenger(9, 16, time=1, id="Q")
    elevators_before = copy.deepcopy(elevators)
    q_before = copy.deepcopy(q)
    make_scheduler(name, config).assign(q, elevators, 1)
    assert elevators == elevators_before
    assert q == q_before


# Building by name


def test_make_scheduler_by_name():
    config = Config()
    assert isinstance(make_scheduler("round-robin", config), RoundRobin)
    assert isinstance(make_scheduler("nearest-car", config), NearestCar)
    assert make_scheduler("lowest-cost", config).max_wait == config.default_max_wait
    nocap = make_scheduler("lowest-cost-nocap", config)
    assert isinstance(nocap, LowestCost)
    assert nocap.max_wait is None
    assert nocap.name == "lowest-cost-nocap"
    assert make_scheduler("lowest-cost", config).name == "lowest-cost"


def test_make_scheduler_unknown_name_lists_the_valid_ones():
    with pytest.raises(ValueError, match="round-robin.*nearest-car.*lowest-cost.*lowest-cost-nocap"):
        make_scheduler("fastest", Config())
