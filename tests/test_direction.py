from conftest import passenger

from elevator_sim.config import Config
from elevator_sim.models import Elevator, Direction, Event
from elevator_sim.direction import choose_direction, run_until_idle, step


def make_elevator(floor=1, direction=Direction.IDLE, capacity=10, inside=(), waiting=()):
    return Elevator(index=0, capacity=capacity, floor=floor, direction=direction,
               inside=list(inside), waiting=list(waiting))


# Collective control


def test_idle_elevator_with_no_work_stays_put():
    elevator = make_elevator(floor=7)
    assert choose_direction(elevator) == Direction.IDLE
    step(elevator, 0, Config())
    assert (elevator.floor, elevator.direction) == (7, Direction.IDLE)


def test_idle_elevator_heads_to_nearest_stop():
    elevator = make_elevator(floor=5, waiting=[passenger(8, 9, id="a"), passenger(3, 1, id="b")])
    assert choose_direction(elevator) == Direction.DOWN


def test_idle_elevator_tie_goes_to_earliest_assigned():
    up_first = make_elevator(floor=5, waiting=[passenger(7, 9, id="a"), passenger(3, 1, id="b")])
    down_first = make_elevator(floor=5, waiting=[passenger(3, 1, id="b"), passenger(7, 9, id="a")])
    assert choose_direction(up_first) == Direction.UP
    assert choose_direction(down_first) == Direction.DOWN


def test_idle_elevator_takes_direction_of_earliest_passenger_waiting_here():
    elevator = make_elevator(floor=5, waiting=[passenger(6, 9, id="a"), passenger(5, 1, id="b"), passenger(5, 9, id="c")])
    assert choose_direction(elevator) == Direction.DOWN


def test_moving_elevator_keeps_direction_while_stops_ahead():
    elevator = make_elevator(floor=5, direction=Direction.UP, waiting=[passenger(8, 9, id="a"), passenger(2, 1, id="b")])
    assert choose_direction(elevator) == Direction.UP


def test_moving_elevator_reverses_at_last_stop():
    elevator = make_elevator(floor=8, direction=Direction.UP, waiting=[passenger(2, 1)])
    assert choose_direction(elevator) == Direction.DOWN


def test_moving_elevator_goes_idle_when_empty():
    elevator = make_elevator(floor=8, direction=Direction.UP)
    assert choose_direction(elevator) == Direction.IDLE


def test_passenger_waiting_here_going_the_elevators_way_keeps_it_going():
    same_way = make_elevator(floor=5, direction=Direction.UP, waiting=[passenger(5, 9, id="a"), passenger(2, 1, id="b")])
    other_way = make_elevator(floor=5, direction=Direction.UP, waiting=[passenger(5, 1, id="a"), passenger(2, 1, id="b")])
    assert choose_direction(same_way) == Direction.UP
    assert choose_direction(other_way) == Direction.DOWN


def test_elevator_with_passengers_inside_never_reverses():
    elevator = make_elevator(floor=5, direction=Direction.UP, inside=[passenger(1, 9, id="a")], waiting=[passenger(2, 1, id="b")])
    assert choose_direction(elevator) == Direction.UP
    floors = []
    for now in range(4):
        step(elevator, now, Config())
        floors.append(elevator.floor)
    assert floors == [6, 7, 8, 9]


# Boarding and unloading


def test_boarding_only_in_the_elevators_direction():
    a = passenger(5, 7, id="a")
    b = passenger(5, 1, id="b")
    elevator = make_elevator(floor=5, direction=Direction.UP, inside=[passenger(1, 9, id="r")], waiting=[a, b])
    step(elevator, 3, Config())
    assert a in elevator.inside and a not in elevator.waiting
    assert b in elevator.waiting and b not in elevator.inside
    assert (a.boarded_at, b.boarded_at) == (3, None)


def test_capacity_limit_leaves_the_extra_passenger_waiting():
    a = passenger(1, 3, id="a")
    b = passenger(1, 5, id="b")
    elevator = make_elevator(floor=1, capacity=1, waiting=[a, b])
    step(elevator, 0, Config())
    assert elevator.inside == [a]
    assert elevator.waiting == [b]


def test_unloading_at_destination():
    passenger_inside = passenger(1, 4)
    elevator = make_elevator(floor=4, direction=Direction.UP, inside=[passenger_inside])
    step(elevator, 6, Config())
    assert elevator.inside == []
    assert passenger_inside.arrived_at == 6
    assert elevator.direction == Direction.IDLE


def test_boarded_and_arrived_events_are_recorded():
    passenger_inside = passenger(1, 4, id="a")
    waiting = passenger(4, 9, id="b")
    elevator = make_elevator(floor=4, direction=Direction.UP, inside=[passenger_inside], waiting=[waiting])
    events = []
    step(elevator, 6, Config(), events)
    assert events == [Event(6, "a", 0, 4, "arrived"), Event(6, "b", 0, 4, "boarded")]
    assert (passenger_inside.arrived_at, waiting.boarded_at) == (6, 6)


# Dwell time


def test_dwell_time_zero_boards_and_leaves_in_the_same_time_unit():
    p = passenger(1, 3)
    elevator = make_elevator(floor=1, waiting=[p])
    step(elevator, 0, Config(dwell_time=0))
    assert p.boarded_at == 0
    assert elevator.floor == 2


def test_dwell_time_two_holds_and_a_late_passenger_does_not_restart_it():
    config = Config(dwell_time=2)
    a = passenger(1, 3, id="a")
    late = passenger(1, 4, time=1, id="b")
    elevator = make_elevator(floor=1, waiting=[a])
    step(elevator, 0, config)
    assert a.boarded_at == 0
    assert elevator.floor == 1
    elevator.waiting.append(late)
    step(elevator, 1, config)
    assert late.boarded_at == 1
    assert elevator.floor == 1
    step(elevator, 2, config)
    assert elevator.floor == 2


def test_dwell_holds_again_on_the_next_visit():
    config = Config(dwell_time=2)
    p = passenger(1, 3)
    elevator = make_elevator(floor=1, waiting=[p])
    floors = []
    for now in range(7):
        step(elevator, now, config)
        floors.append(elevator.floor)
    assert p.arrived_at == 4
    assert floors == [1, 1, 2, 3, 3, 3, 3]


def test_a_parked_elevator_dwells_again_for_a_new_passenger():
    config = Config(dwell_time=2)
    first = passenger(1, 3, id="a")
    elevator = make_elevator(floor=1, waiting=[first])
    for now in range(8):
        step(elevator, now, config)
    assert (elevator.floor, elevator.is_idle) == (3, True)
    second = passenger(3, 1, time=8, id="b")
    elevator.waiting.append(second)
    step(elevator, 8, config)
    assert second.boarded_at == 8
    assert elevator.floor == 3


# Trial allocation


def test_run_until_idle_finishes_the_trip():
    p = passenger(1, 5)
    elevator = make_elevator(floor=1, waiting=[p])
    assert run_until_idle(elevator, 0, Config(), limit=5) is True
    assert (p.boarded_at, p.arrived_at) == (0, 4)


def test_run_until_idle_counts_from_now():
    p = passenger(1, 5, time=10)
    elevator = make_elevator(floor=1, waiting=[p])
    assert run_until_idle(elevator, 10, Config(), limit=100) is True
    assert (p.boarded_at, p.arrived_at) == (10, 14)


def test_run_until_idle_returns_false_when_limit_is_too_small():
    p = passenger(1, 5)
    elevator = make_elevator(floor=1, waiting=[p])
    assert run_until_idle(elevator, 0, Config(), limit=4) is False
    assert p.arrived_at is None


def test_run_until_idle_on_an_idle_elevator_is_true_at_once():
    assert run_until_idle(make_elevator(), 0, Config(), limit=0) is True


def test_a_160_floor_trip_from_the_top_to_the_lobby():
    config = Config(floors=160, elevators=1, capacity=1)
    p = passenger(160, 1)
    elevator = make_elevator(floor=160, capacity=1, waiting=[p])
    assert run_until_idle(elevator, 0, config, limit=1000) is True
    assert (p.boarded_at, p.arrived_at) == (0, 159)
    assert p.total >= 159
