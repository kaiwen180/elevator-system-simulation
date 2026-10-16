"""The clock: reveal requests, assign them, log positions, move every elevator."""

from __future__ import annotations

from .config import Config
from .scheduler import Scheduler
from .models import Elevator, Event, Passenger, Request, Result
from .direction import step


def reveal_schedule(passengers: list[Passenger]) -> dict[int, list[Passenger]]:
    """Passengers grouped by request time, keeping input order within one time."""
    schedule: dict[int, list[Passenger]] = {}
    for p in passengers:
        schedule.setdefault(p.request.time, []).append(p)
    return schedule


def all_idle(elevators: list[Elevator]) -> bool:
    """True when no elevator has passengers in it or waiting for it."""
    for elevator in elevators:
        if not elevator.is_idle:
            return False
    return True


class Simulation:
    def __init__(self, config: Config, scheduler: Scheduler) -> None:
        self.config = config
        self.scheduler = scheduler

    def check_floors(self, requests: list[Request]) -> None:
        """Raise ValueError if a request names a floor outside the building."""
        for r in requests:
            for floor in (r.source, r.dest):
                if not 1 <= floor <= self.config.floors:
                    raise ValueError(f"request {r.id}: floor {floor} is outside 1..{self.config.floors}")

    def assign(self, p: Passenger, elevators: list[Elevator], now: int, events: list[Event]) -> None:
        """Ask the scheduler for an elevator and put the passenger on its waiting list."""
        index = self.scheduler.assign(p, elevators, now)
        p.elevator = index
        p.assigned_at = now
        elevators[index].waiting.append(p)
        events.append(Event(now, p.id, index, p.source, "assigned"))

    def run(self, requests: list[Request], max_time_units: int = 1_000_000) -> Result:
        """Run until every request is served; raise RuntimeError past `max_time_units`."""
        self.check_floors(requests)
        passengers = [Passenger(r) for r in requests]
        schedule = reveal_schedule(passengers)
        elevators = [Elevator(index=i, capacity=self.config.capacity) for i in range(self.config.elevators)]
        positions: list[list[int]] = []
        events: list[Event] = []
        revealed = 0
        for now in range(max_time_units):
            for p in schedule.pop(now, []):
                self.assign(p, elevators, now, events)
                revealed += 1
            positions.append([elevator.floor for elevator in elevators])
            for elevator in elevators:
                step(elevator, now, self.config, events)
            if revealed == len(passengers) and all_idle(elevators):
                return Result(passengers, positions, events)
        raise RuntimeError(f"run did not finish within {max_time_units} time units")
