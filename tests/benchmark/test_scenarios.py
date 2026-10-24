from dataclasses import replace

import pytest

from elevator_sim.core.config import Config
from elevator_sim.benchmark.schedulers import SCHEDULERS
from elevator_sim.benchmark.invariants import assert_valid
from elevator_sim.core.models import Request
from elevator_sim.benchmark.scenarios import Scenario, compare, run_scenario, scenarios
from elevator_sim.benchmark.stats import summarize
from elevator_sim.benchmark.traffic import Segment, daily_profile

ALL = scenarios()


def checked(scenario, scheduler):
    """Run a scenario and check every invariant before handing back the result."""
    result = run_scenario(scenario, scheduler)
    assert_valid(result, scenario.requests(), scenario.config)
    return result


def mean_total(result):
    return summarize(result).total.mean


def max_wait(result):
    return summarize(result).wait.max


# The scenario list


def test_each_demand_level_on_the_typical_building_and_bank():
    for demand in ("020", "050", "080", "100", "120"):
        assert f"20f-4x10-demand{demand}-interfloor" in ALL


def test_each_building_with_the_typical_bank_at_80_percent():
    for floors in (5, 20, 60, 160):
        assert f"{floors}f-4x10-demand080-interfloor" in ALL


def test_each_bank_in_the_typical_building_at_80_percent():
    for bank in ("1x1", "2x4", "4x10", "10x20"):
        assert f"20f-{bank}-demand080-interfloor" in ALL


def test_the_corners_and_the_daily_profile():
    assert "160f-1x1-demand100-interfloor" in ALL
    assert "5f-10x20-demand100-interfloor" in ALL
    assert "20f-4x10-daily" in ALL
    for demand in ("080", "100", "120"):
        assert f"20f-4x10-demand{demand}-up-peak" in ALL


def test_names_match_their_settings():
    for name, scenario in ALL.items():
        config = scenario.config
        assert scenario.name == name
        assert name.startswith(f"{config.floors}f-{config.elevators}x{config.capacity}-")


def test_the_daily_profile_scenario_uses_the_daily_profile():
    segments = ALL["20f-4x10-daily"].segments
    assert [(s.demand, s.pattern) for s in segments] == [(s.demand, s.pattern) for s in daily_profile()]


def test_every_scenario_has_passengers():
    for scenario in ALL.values():
        assert len(scenario.requests()) >= 3, scenario.name


def test_requests_are_the_same_for_the_same_seed():
    scenario = ALL["20f-4x10-demand080-interfloor"]
    assert scenario.requests() == scenario.requests()


# Every scenario under every scheduler obeys every rule


@pytest.mark.parametrize("scheduler", SCHEDULERS)
@pytest.mark.parametrize("name", list(ALL))
def test_every_scenario_finishes_and_obeys_every_rule(name, scheduler):
    scenario = ALL[name]
    result = checked(scenario, scheduler)
    assert len(result.passengers) == len(scenario.requests())


# Expected results, checked as tests


@pytest.mark.parametrize("scheduler", SCHEDULERS)
def test_at_20_percent_demand_average_wait_is_under_one_trip_of_the_shaft(scheduler):
    scenario = ALL["20f-4x10-demand020-interfloor"]
    result = checked(scenario, scheduler)
    assert summarize(result).wait.mean < scenario.config.floors - 1


@pytest.mark.parametrize("demand", ["080", "100"])
def test_lowest_cost_beats_round_robin_on_average_total(demand):
    scenario = ALL[f"20f-4x10-demand{demand}-interfloor"]
    lowest = mean_total(checked(scenario, "lowest-cost"))
    robin = mean_total(checked(scenario, "round-robin"))
    assert lowest < robin


def with_dwell_time(scenario, dwell_time):
    """The same scenario with a longer dwell time; passengers are regenerated for the new config."""
    config = replace(scenario.config, dwell_time=dwell_time)
    return Scenario(f"{scenario.name}-dwell{dwell_time}", config, scenario.segments, scenario.seed)


@pytest.mark.parametrize("demand", ["100", "120"])
def test_the_max_wait_trades_average_total_for_a_shorter_longest_wait(demand):
    scenario = with_dwell_time(ALL[f"20f-4x10-demand{demand}-interfloor"], 3)
    capped = summarize(checked(scenario, "lowest-cost"))
    uncapped = summarize(checked(scenario, "lowest-cost-nocap"))
    assert capped.wait.max < uncapped.wait.max
    assert capped.total.mean > uncapped.total.mean


def test_at_dwell_time_zero_the_default_max_wait_never_binds():
    scenario = ALL["20f-4x10-demand120-up-peak"]
    capped = checked(scenario, "lowest-cost")
    uncapped = checked(scenario, "lowest-cost-nocap")
    assert max_wait(uncapped) < scenario.config.default_max_wait
    assert [p.elevator for p in capped.passengers] == [p.elevator for p in uncapped.passengers]


@pytest.mark.parametrize("scheduler", SCHEDULERS)
def test_at_120_percent_up_peak_the_run_ends_and_the_longest_wait_grows(scheduler):
    heavy = checked(ALL["20f-4x10-demand120-up-peak"], scheduler)
    normal = checked(ALL["20f-4x10-demand080-up-peak"], scheduler)
    assert max_wait(heavy) > max_wait(normal)


def boarding_order(result):
    return [(e.passenger, e.kind) for e in result.events if e.kind != "assigned"]


def test_one_elevator_of_capacity_one_serves_passengers_one_at_a_time():
    scenario = ALL["20f-1x1-demand080-interfloor"]
    result = checked(scenario, "lowest-cost")
    order = boarding_order(result)
    assert len(order) == 2 * len(scenario.requests())
    for i in range(0, len(order), 2):
        assert order[i][1] == "boarded"
        assert order[i + 1] == (order[i][0], "arrived")


def test_one_elevator_of_capacity_one_serves_in_the_same_order_under_every_scheduler():
    scenario = ALL["20f-1x1-demand080-interfloor"]
    orders = [boarding_order(checked(scenario, name)) for name in SCHEDULERS]
    assert orders[0] == orders[1] == orders[2]


def test_one_elevator_in_160_floors_serves_floor_160_to_the_lobby():
    config = Config(floors=160, elevators=1, capacity=1)
    scenario = Scenario("one-trip", config, ())
    requests = [Request(0, "p1", 160, 1)]
    for scheduler in SCHEDULERS:
        result = run_scenario(scenario, scheduler, requests)
        assert_valid(result, requests, config)
        assert result.passengers[0].total >= 159


# The comparison table


def test_compare_prints_a_header_and_one_row_per_run():
    table = compare(["5f-4x10-demand080-interfloor"], ["round-robin", "nearest-car"])
    lines = table.splitlines()
    assert lines[0].startswith("| scenario | scheduler | passengers | mean wait |")
    assert lines[0].endswith("| time units |")
    assert lines[1].startswith("| --- |")
    assert len(lines) == 4
    assert lines[2].startswith("| 5f-4x10-demand080-interfloor | round-robin |")
    assert lines[3].startswith("| 5f-4x10-demand080-interfloor | nearest-car |")


def test_compare_rejects_an_unknown_scenario():
    with pytest.raises(ValueError, match="no-such"):
        compare(["no-such"], ["round-robin"])


# Long horizons


@pytest.mark.slow
@pytest.mark.parametrize("scheduler", SCHEDULERS)
def test_a_long_typical_run_at_full_demand(scheduler):
    scenario = Scenario("20f-4x10-demand100-interfloor-long", Config(), (Segment(2000, 1.0, "interfloor"),))
    checked(scenario, scheduler)


@pytest.mark.slow
@pytest.mark.parametrize("scheduler", SCHEDULERS)
def test_a_long_daily_profile(scheduler):
    scenario = Scenario("20f-4x10-daily-long", Config(), tuple(daily_profile(400)))
    checked(scenario, scheduler)
