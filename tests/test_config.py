import pytest

from elevator_sim.config import Config


def test_defaults_match_design():
    c = Config()
    assert (c.floors, c.elevators, c.capacity, c.dwell_time) == (20, 4, 10, 0)


@pytest.mark.parametrize("field,value", [("floors", 1), ("elevators", 0), ("capacity", 0), ("dwell_time", -1)])
def test_bad_settings_are_refused(field, value):
    with pytest.raises(ValueError, match=field):
        Config(**{field: value})


def test_handling_capacity_is_full_elevators_on_round_trips():
    assert Config(floors=20, elevators=4, capacity=10).handling_capacity == pytest.approx(40 / 38)


def test_default_max_wait_is_three_trips_of_the_shaft():
    assert Config(floors=20).default_max_wait == 57
