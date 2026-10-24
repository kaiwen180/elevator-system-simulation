"""Direction logic: collective control (LOOK in disk scheduling), boarding, unloading, dwell."""

from __future__ import annotations

from .config import Config
from .models import Direction, Elevator, Event, Passenger


def step(elevator: Elevator, now: int, config: Config, events: list[Event] | None = None) -> None:
    """Advance one elevator by one time unit: unload, choose, board, choose, dwell, move."""
    left = unload(elevator, now, events)
    elevator.direction = choose_direction(elevator)
    boarded = board(elevator, now, events)
    elevator.direction = choose_direction(elevator)
    if left or boarded:
        open_doors(elevator, config)
    move(elevator, config)


def choose_direction(elevator: Elevator) -> Direction:
    """Pick the elevator's next direction by collective control, as in docs/design.md."""
    if elevator.direction == Direction.IDLE:
        return choose_idle(elevator)
    return choose_moving(elevator)


def choose_moving(elevator: Elevator) -> Direction:
    """Collective control for a moving elevator: keep going, else reverse, else go idle."""
    if stop_ahead(elevator):
        return elevator.direction
    for p in waiting_here(elevator):
        if p.direction == elevator.direction:
            return elevator.direction
    if elevator.stops():
        return Direction(-elevator.direction)
    return Direction.IDLE


def choose_idle(elevator: Elevator) -> Direction:
    """Collective control for an idle elevator: serve someone here, else head to the nearest stop."""
    here = waiting_here(elevator)
    if here:
        return here[0].direction
    if elevator.stops():
        return direction_toward(elevator, nearest_stop(elevator))
    return Direction.IDLE


def stop_ahead(elevator: Elevator) -> bool:
    """True if any stop lies strictly ahead in the elevator's direction."""
    for stop in elevator.stops():
        if (stop - elevator.floor) * elevator.direction > 0:
            return True
    return False


def waiting_here(elevator: Elevator) -> list[Passenger]:
    """Waiting passengers at the elevator's floor, in assignment order."""
    here = []
    for p in elevator.waiting:
        if p.source == elevator.floor:
            here.append(p)
    return here


def direction_toward(elevator: Elevator, floor: int) -> Direction:
    """The direction from the elevator's floor to `floor`."""
    if floor > elevator.floor:
        return Direction.UP
    if floor < elevator.floor:
        return Direction.DOWN
    return Direction.IDLE


def nearest_stop(elevator: Elevator) -> int:
    """The closest stop; on a tie the earliest-assigned passenger's stop wins."""
    stops = elevator.stops()
    best = stops[0]
    for stop in stops[1:]:
        if abs(stop - elevator.floor) < abs(best - elevator.floor):
            best = stop
    return best


def unload(elevator: Elevator, now: int, events: list[Event] | None) -> int:
    """Let off passengers in the elevator whose destination is this floor; return how many left."""
    staying = []
    left = 0
    for p in elevator.inside:
        if p.dest == elevator.floor:
            p.arrived_at = now
            record(events, now, p, elevator, "arrived")
            left += 1
        else:
            staying.append(p)
    elevator.inside = staying
    return left


def board(elevator: Elevator, now: int, events: list[Event] | None) -> int:
    """Take on passengers here going the elevator's way, in order, until full; return how many."""
    boarded = 0
    for p in waiting_here(elevator):
        if elevator.is_full:
            break
        if p.direction == elevator.direction:
            elevator.waiting.remove(p)
            elevator.inside.append(p)
            p.boarded_at = now
            record(events, now, p, elevator, "boarded")
            boarded += 1
    return boarded


def open_doors(elevator: Elevator, config: Config) -> None:
    """Start the dwell, once per visit."""
    if not elevator.doors_cycled:
        elevator.hold = config.dwell_time
        elevator.doors_cycled = True


def move(elevator: Elevator, config: Config) -> None:
    """Hold while dwelling, otherwise travel one floor; moving or parking ends the visit."""
    if elevator.hold > 0:
        elevator.hold -= 1
        return
    if elevator.direction == Direction.IDLE:
        elevator.doors_cycled = False  # parking ends the visit, so the next passenger gets a dwell
        return
    elevator.floor += elevator.direction
    assert 1 <= elevator.floor <= config.floors, f"elevator {elevator.index} left the shaft at floor {elevator.floor}"
    elevator.doors_cycled = False


def record(events: list[Event] | None, now: int, p: Passenger, elevator: Elevator, kind: str) -> None:
    """Append an event if the caller is collecting them."""
    if events is not None:
        events.append(Event(now, p.id, elevator.index, elevator.floor, kind))


def run_until_idle(elevator: Elevator, now: int, config: Config, limit: int) -> bool:
    """Step the elevator from time `now` until it has no stops; False if `limit` time units pass first."""
    time = now
    while not elevator.is_idle:
        if time - now >= limit:
            return False
        step(elevator, time, config)
        time += 1
    return True
