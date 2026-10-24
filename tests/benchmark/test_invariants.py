import copy

import pytest

from elevator_sim.core.config import Config
from elevator_sim.benchmark.invariants import assert_valid, violations
from elevator_sim.core.models import Event, Passenger, Request, Result

CONFIG = Config(floors=5, elevators=1, capacity=10, dwell_time=0)


def valid_run() -> tuple[Result, list[Request]]:
    """One elevator, one passenger from floor 1 to floor 3, dwell time 0."""
    request = Request(time=0, id="p1", source=1, dest=3)
    passenger_inside = Passenger(request, elevator=0, assigned_at=0, boarded_at=0, arrived_at=2)
    events = [
        Event(0, "p1", 0, 1, "assigned"),
        Event(0, "p1", 0, 1, "boarded"),
        Event(2, "p1", 0, 3, "arrived"),
    ]
    return Result([passenger_inside], [[1], [2], [3]], events), [request]


def broken(result: Result, requests: list[Request], config: Config = CONFIG) -> str:
    """All violations joined into one string, so a test can search it."""
    found = violations(result, requests, config)
    assert found, "expected at least one violation"
    return "\n".join(found)


def test_valid_run_has_no_violations():
    result, requests = valid_run()
    assert violations(result, requests, CONFIG) == []
    assert_valid(result, requests, CONFIG)


def test_missing_arrival():
    result, requests = valid_run()
    result.events.pop()
    result.passengers[0].arrived_at = None
    message = broken(result, requests)
    assert "p1" in message
    assert "arrived" in message


def test_request_with_no_passenger():
    result, requests = valid_run()
    requests.append(Request(time=0, id="p2", source=2, dest=4))
    assert "p2" in broken(result, requests)


def test_arrival_at_wrong_floor():
    result, requests = valid_run()
    requests[0] = Request(time=0, id="p1", source=1, dest=4)
    result.passengers[0] = Passenger(requests[0], elevator=0, assigned_at=0, boarded_at=0, arrived_at=2)
    assert "destination" in broken(result, requests)


def test_boarded_before_requested():
    result, requests = valid_run()
    late = Request(time=1, id="p1", source=1, dest=3)
    requests[0] = late
    result.passengers[0] = Passenger(late, elevator=0, assigned_at=1, boarded_at=0, arrived_at=2)
    result.events[0] = Event(1, "p1", 0, 2, "assigned")
    assert "boarded at 0 before requested at 1" in broken(result, requests)


def test_assigned_before_request_time():
    result, requests = valid_run()
    late = Request(time=1, id="p1", source=1, dest=3)
    requests[0] = late
    result.passengers[0] = Passenger(late, elevator=0, assigned_at=0, boarded_at=1, arrived_at=2)
    assert "assigned at 0 before request time 1" in broken(result, requests)


def test_over_capacity():
    result, requests = valid_run()
    second = Request(time=0, id="p2", source=1, dest=3)
    requests.append(second)
    result.passengers.append(Passenger(second, elevator=0, assigned_at=0, boarded_at=0, arrived_at=2))
    result.events = [
        Event(0, "p1", 0, 1, "assigned"),
        Event(0, "p2", 0, 1, "assigned"),
        Event(0, "p1", 0, 1, "boarded"),
        Event(0, "p2", 0, 1, "boarded"),
        Event(2, "p1", 0, 3, "arrived"),
        Event(2, "p2", 0, 3, "arrived"),
    ]
    tight = Config(floors=5, elevators=1, capacity=1, dwell_time=0)
    assert violations(result, requests, CONFIG) == []
    message = broken(result, requests, tight)
    assert "elevator 0" in message
    assert "capacity 1" in message
    assert "2 passengers inside at time 0" in message


def test_jump_of_two_floors():
    result, requests = valid_run()
    result.positions = [[1], [3], [3]]
    assert "moved from floor 1 to 3 between times 0 and 1" in broken(result, requests)


def test_floor_outside_building():
    result, requests = valid_run()
    result.positions.append([6])
    assert "floor 6 at time 3, outside 1..5" in broken(result, requests)


def test_boarding_on_wrong_floor():
    result, requests = valid_run()
    result.positions = [[2], [2], [3]]
    assert "boarded on floor 1 but elevator 0 was on floor 2 at time 0" in broken(result, requests)


def test_riding_the_wrong_way():
    result, requests = valid_run()
    result.positions = [[1], [2], [1], [2], [3]]
    result.passengers[0].arrived_at = 4
    result.events[2] = Event(4, "p1", 0, 3, "arrived")
    assert "rode down" in broken(result, requests)


def test_boarding_a_different_elevator_than_assigned():
    result, requests = valid_run()
    two_elevators = Config(floors=5, elevators=2, capacity=10, dwell_time=0)
    result.positions = [[1, 1], [2, 1], [3, 1]]
    result.events[0] = Event(0, "p1", 1, 1, "assigned")
    assert "p1: boarded elevator 0 but was assigned elevator 1" in broken(result, requests, two_elevators)


def test_duplicate_events():
    result, requests = valid_run()
    result.events.append(Event(2, "p1", 0, 3, "arrived"))
    assert "2 arrived events" in broken(result, requests)


def test_run_ends_before_last_arrival():
    result, requests = valid_run()
    result.positions = [[1], [2]]
    assert "after the last row" in broken(result, requests)


def test_assert_valid_lists_first_ten_and_counts_the_rest():
    result, requests = valid_run()
    result.positions = [[9]] * 15
    with pytest.raises(AssertionError) as error:
        assert_valid(result, requests, CONFIG)
    text = str(error.value)
    assert "violations" in text
    assert "more" in text


def test_checker_does_not_change_the_result():
    result, requests = valid_run()
    before = copy.deepcopy(result)
    violations(result, requests, CONFIG)
    assert result == before
