"""Checks that a finished run obeyed every rule in docs/test-plan.md."""

from __future__ import annotations

from ..core.config import Config
from ..core.models import Event, Passenger, Request, Result

KINDS = ("assigned", "boarded", "arrived")
SHOWN = 10


def events_by_passenger(events: list[Event]) -> dict[str, dict[str, list[Event]]]:
    """Group events by passenger id, then by kind, keeping their order."""
    grouped: dict[str, dict[str, list[Event]]] = {}
    for event in events:
        kinds = grouped.setdefault(event.passenger, {kind: [] for kind in KINDS})
        kinds.setdefault(event.kind, []).append(event)
    return grouped


def first_event(grouped: dict, passenger_id: str, kind: str) -> Event | None:
    """The first event of this kind for this passenger, or None."""
    found = grouped.get(passenger_id, {}).get(kind, [])
    return found[0] if found else None


def floor_at(positions: list[list[int]], time: int, elevator: int) -> int | None:
    """The elevator's floor in row `time`, or None when the log has no such cell."""
    if 0 <= time < len(positions) and 0 <= elevator < len(positions[time]):
        return positions[time][elevator]
    return None


def check_everyone_arrives(result: Result, requests: list[Request], grouped: dict) -> list[str]:
    """Rule 1: one passenger per request, each assigned, boarded and arrived once, at its destination."""
    problems = []
    passengers: dict[str, list[Passenger]] = {}
    for passenger in result.passengers:
        passengers.setdefault(passenger.id, []).append(passenger)
    for request in requests:
        matches = passengers.get(request.id, [])
        if len(matches) != 1:
            problems.append(f"{request.id}: {len(matches)} passengers for this request, expected 1")
        for kind in KINDS:
            count = len(grouped.get(request.id, {}).get(kind, []))
            if count != 1:
                problems.append(f"{request.id}: {count} {kind} events, expected 1")
        arrival = first_event(grouped, request.id, "arrived")
        if arrival is not None and arrival.floor != request.dest:
            problems.append(f"{request.id}: arrived on floor {arrival.floor}, not at destination {request.dest}")
    requested_ids = {request.id for request in requests}
    for passenger_id in passengers:
        if passenger_id not in requested_ids:
            problems.append(f"{passenger_id}: passenger has no request")
    for passenger in result.passengers:
        problems += check_fields_match_events(passenger, grouped)
    return problems


def check_fields_match_events(passenger: Passenger, grouped: dict) -> list[str]:
    """Part of rule 1: the passenger's recorded times and elevator agree with the event log."""
    problems = []
    fields = {"assigned": passenger.assigned_at, "boarded": passenger.boarded_at, "arrived": passenger.arrived_at}
    for kind, recorded in fields.items():
        event = first_event(grouped, passenger.id, kind)
        logged = None if event is None else event.time
        if recorded != logged:
            problems.append(f"{passenger.id}: {kind}_at is {recorded} but the {kind} event is at {logged}")
    assigned = first_event(grouped, passenger.id, "assigned")
    if assigned is not None and passenger.elevator != assigned.elevator:
        problems.append(f"{passenger.id}: elevator is {passenger.elevator} but the assigned event names elevator {assigned.elevator}")
    return problems


def check_order_of_events(requests: list[Request], grouped: dict) -> list[str]:
    """Rule 2: requested <= assigned <= boarded <= arrived, and assigned equals requested."""
    problems = []
    for request in requests:
        assigned = first_event(grouped, request.id, "assigned")
        boarded = first_event(grouped, request.id, "boarded")
        arrived = first_event(grouped, request.id, "arrived")
        if assigned is not None and assigned.time > request.time:
            problems.append(f"{request.id}: assigned at {assigned.time}, not at request time {request.time}")
        if boarded is not None and boarded.time < request.time:
            problems.append(f"{request.id}: boarded at {boarded.time} before requested at {request.time}")
        if assigned is not None and boarded is not None and boarded.time < assigned.time:
            problems.append(f"{request.id}: boarded at {boarded.time} before assigned at {assigned.time}")
        if boarded is not None and arrived is not None and arrived.time < boarded.time:
            problems.append(f"{request.id}: arrived at {arrived.time} before boarded at {boarded.time}")
    return problems


def check_no_peeking(requests: list[Request], grouped: dict) -> list[str]:
    """Rule 3: no passenger is assigned before their request time."""
    problems = []
    for request in requests:
        assigned = first_event(grouped, request.id, "assigned")
        if assigned is not None and assigned.time < request.time:
            problems.append(f"{request.id}: assigned at {assigned.time} before request time {request.time}")
    return problems


def check_capacity(events: list[Event], config: Config) -> list[str]:
    """Rule 4: replaying boardings and arrivals, no elevator ever holds more than its capacity."""
    problems = []
    inside: dict[int, int] = {}
    for event in events:
        if event.kind == "boarded":
            inside[event.elevator] = inside.get(event.elevator, 0) + 1
            if inside[event.elevator] > config.capacity:
                problems.append(
                    f"elevator {event.elevator}: {inside[event.elevator]} passengers inside at time {event.time}, over capacity {config.capacity}"
                )
        elif event.kind == "arrived":
            inside[event.elevator] = inside.get(event.elevator, 0) - 1
    return problems


def check_one_floor_per_time_unit(positions: list[list[int]], config: Config) -> list[str]:
    """Rule 5: every row has one floor per elevator, inside the building, at most 1 floor from the last row."""
    problems = []
    for time, row in enumerate(positions):
        if len(row) != config.elevators:
            problems.append(f"time {time}: {len(row)} elevators in the row, expected {config.elevators}")
        for elevator, floor in enumerate(row):
            if not 1 <= floor <= config.floors:
                problems.append(f"elevator {elevator}: floor {floor} at time {time}, outside 1..{config.floors}")
            if time > 0 and elevator < len(positions[time - 1]):
                before = positions[time - 1][elevator]
                if abs(floor - before) > 1:
                    problems.append(f"elevator {elevator}: moved from floor {before} to {floor} between times {time - 1} and {time}")
    return problems


def check_events_where_elevator_is(result: Result) -> list[str]:
    """Rule 6: a boarding or arrival happens on the floor the elevator shows in the row for that time."""
    problems = []
    for event in result.events:
        if event.kind == "assigned":
            continue
        floor = floor_at(result.positions, event.time, event.elevator)
        if floor is not None and floor != event.floor:
            problems.append(
                f"{event.passenger}: {event.kind} on floor {event.floor} but elevator {event.elevator} "
                f"was on floor {floor} at time {event.time}"
            )
    return problems


def check_direction(result: Result, requests: list[Request], grouped: dict) -> list[str]:
    """Rule 7: on every time unit a passenger rides, their elevator moves toward their destination or stays."""
    problems = []
    for request in requests:
        boarded = first_event(grouped, request.id, "boarded")
        arrived = first_event(grouped, request.id, "arrived")
        if boarded is None or arrived is None:
            continue
        for time in range(boarded.time, arrived.time):
            here = floor_at(result.positions, time, boarded.elevator)
            there = floor_at(result.positions, time + 1, boarded.elevator)
            if here is None or there is None:
                continue
            step = there - here
            if step != 0 and step != int(request.direction):
                moved = "up" if step > 0 else "down"
                wanted = request.direction.name.lower()
                problems.append(
                    f"{request.id}: rode {moved} on elevator {boarded.elevator} between times {time} and {time + 1}, "
                    f"but travels {wanted}"
                )
    return problems


def check_final_assignment(requests: list[Request], grouped: dict) -> list[str]:
    """Rule 8: a passenger boards, and leaves, the elevator they were assigned."""
    problems = []
    for request in requests:
        assigned = first_event(grouped, request.id, "assigned")
        boarded = first_event(grouped, request.id, "boarded")
        arrived = first_event(grouped, request.id, "arrived")
        if assigned is not None and boarded is not None and boarded.elevator != assigned.elevator:
            problems.append(f"{request.id}: boarded elevator {boarded.elevator} but was assigned elevator {assigned.elevator}")
        if boarded is not None and arrived is not None and arrived.elevator != boarded.elevator:
            problems.append(f"{request.id}: arrived on elevator {arrived.elevator} but boarded elevator {boarded.elevator}")
    return problems


def check_no_early_stop(result: Result) -> list[str]:
    """Rule 9: no event happens after the last row of the positions log."""
    problems = []
    last_row = len(result.positions) - 1
    for event in result.events:
        if event.time > last_row:
            problems.append(f"{event.passenger}: {event.kind} at {event.time}, after the last row {last_row}")
    return problems


def check_served_floors(events: list[Event], config: Config) -> list[str]:
    """Rule 10: an elevator boards or lets off passengers only at floors it serves."""
    problems = []
    for event in events:
        if event.kind != "assigned" and not config.serves(event.elevator, event.floor):
            problems.append(f"{event.passenger}: {event.kind} at floor {event.floor}, which elevator {event.elevator} does not serve")
    return problems


def violations(result: Result, requests: list[Request], config: Config) -> list[str]:
    """Every broken rule, one readable line each; empty when the run is valid."""
    grouped = events_by_passenger(result.events)
    found = []
    found += check_everyone_arrives(result, requests, grouped)
    found += check_order_of_events(requests, grouped)
    found += check_no_peeking(requests, grouped)
    found += check_capacity(result.events, config)
    found += check_one_floor_per_time_unit(result.positions, config)
    found += check_events_where_elevator_is(result)
    found += check_direction(result, requests, grouped)
    found += check_final_assignment(requests, grouped)
    found += check_no_early_stop(result)
    found += check_served_floors(result.events, config)
    return found


def assert_valid(result: Result, requests: list[Request], config: Config) -> None:
    """Raise AssertionError listing the first 10 violations."""
    found = violations(result, requests, config)
    if not found:
        return
    lines = [f"{len(found)} violations:"] + found[:SHOWN]
    if len(found) > SHOWN:
        lines.append(f"... and {len(found) - SHOWN} more")
    raise AssertionError("\n".join(lines))
