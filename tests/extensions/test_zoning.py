import copy
from pathlib import Path

import pytest
from conftest import passenger

from elevator_sim.app.cli import main
from elevator_sim.core.config import Config
from elevator_sim.extensions.zoning import Zoned, bands, elevator_bands, zone_floor
from elevator_sim.benchmark.invariants import assert_valid
from elevator_sim.core.models import Elevator
from elevator_sim.core.scheduler import LowestCost
from elevator_sim.benchmark.schedulers import NAMES, make_scheduler
from elevator_sim.core.simulation import Simulation
from elevator_sim.benchmark.traffic import Segment, generate

EXAMPLE = Path(__file__).parent.parent.parent / "examples" / "requests.csv"


def idle(index, floor=1):
    return Elevator(index=index, capacity=10, floor=floor)


# The band split


def test_twenty_floors_split_into_four_bands_above_the_lobby():
    assert bands(20, 4) == [(2, 6), (7, 11), (12, 16), (17, 20)]


@pytest.mark.parametrize("floors, elevators", [(5, 2), (20, 4), (40, 4), (60, 10), (160, 4), (2, 3)])
def test_bands_cover_every_floor_above_the_lobby_once(floors, elevators):
    covered = [floor for low, high in bands(floors, elevators) for floor in range(low, high + 1)]
    assert covered == list(range(2, floors + 1))


def test_band_sizes_differ_by_at_most_one():
    sizes = [high - low + 1 for low, high in bands(40, 4)]
    assert max(sizes) - min(sizes) <= 1


def test_one_band_per_elevator():
    assert elevator_bands(4, 4) == [0, 1, 2, 3]


def test_fewer_floors_than_elevators_gives_one_band_per_floor_shared_by_a_group():
    assert bands(5, 10) == [(2, 2), (3, 3), (4, 4), (5, 5)]
    assert elevator_bands(10, 4) == [0, 0, 0, 1, 1, 1, 2, 2, 3, 3]


def test_the_zone_floor_is_the_floor_that_is_not_the_lobby():
    assert zone_floor(passenger(1, 14)) == 14
    assert zone_floor(passenger(14, 1)) == 14
    assert zone_floor(passenger(9, 3)) == 3


# The choice


def test_zoned_sends_a_lobby_passenger_to_the_elevator_whose_band_holds_their_floor():
    config = Config(floors=20, elevators=4)
    elevators = [idle(i) for i in range(4)]
    a = passenger(1, 18, id="a")
    assert LowestCost(config).assign(a, elevators, 0) == 0
    assert Zoned(config).assign(a, elevators, 0) == 3


def test_zoned_sends_a_passenger_down_to_the_lobby_by_their_origin_floor():
    config = Config(floors=20, elevators=4)
    elevators = [idle(i) for i in range(4)]
    assert Zoned(config).assign(passenger(9, 1, id="a"), elevators, 0) == 1


def test_zoned_picks_the_lowest_cost_elevator_inside_the_band():
    config = Config(floors=5, elevators=10, capacity=20)
    elevators = [idle(i) for i in range(10)]
    elevators[3].floor = 5
    a = passenger(1, 3, id="a")
    assert Zoned(config).assign(a, elevators, 0) == 4


def test_zoned_falls_back_to_lowest_cost_when_no_offered_elevator_holds_the_band():
    config = Config(floors=20, elevators=4)
    offered = [idle(0, floor=10), idle(1, floor=1)]
    assert Zoned(config).assign(passenger(1, 18, id="a"), offered, 0) == 1


def test_zoned_does_not_change_elevators():
    config = Config(floors=20, elevators=4)
    elevators = [idle(i, floor=1 + 3 * i) for i in range(4)]
    a = passenger(9, 16, id="a")
    before = copy.deepcopy(elevators)
    Zoned(config).assign(a, elevators, 0)
    assert elevators == before


# Building it by name


def test_make_scheduler_builds_zoned():
    scheduler = make_scheduler("zoned", Config())
    assert isinstance(scheduler, Zoned)
    assert scheduler.name == "zoned"
    assert "zoned" in NAMES


def test_the_cli_runs_zoned(tmp_path, capsys):
    code = main(["run", str(EXAMPLE), "--elevators", "2", "--scheduler", "zoned", "--out", str(tmp_path)])
    assert code == 0
    assert "Passengers: 3" in capsys.readouterr().out


# Whole runs


@pytest.mark.parametrize("floors, elevators, capacity, pattern, horizon", [
    (20, 4, 10, "interfloor", 300),
    (20, 4, 10, "up-peak", 300),
    (5, 10, 20, "up-peak", 100),
])
def test_a_zoned_run_obeys_every_rule(floors, elevators, capacity, pattern, horizon):
    config = Config(floors=floors, elevators=elevators, capacity=capacity)
    requests = generate(config, [Segment(horizon, 1.0, pattern)], seed=1)
    result = Simulation(config, Zoned(config)).run(requests)
    assert_valid(result, requests, config)


def test_every_zoned_passenger_rides_an_elevator_of_their_band():
    config = Config()
    requests = generate(config, [Segment(300, 1.0, "up-peak")], seed=1)
    result = Simulation(config, Zoned(config)).run(requests)
    split = bands(config.floors, config.elevators)
    groups = elevator_bands(config.elevators, len(split))
    for p in result.passengers:
        low, high = split[groups[p.elevator]]
        assert low <= zone_floor(p) <= high, p.id
