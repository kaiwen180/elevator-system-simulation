"""The scheduler picks the elevator for a new passenger: round robin, nearest car or lowest cost; zoned is in extensions."""

from __future__ import annotations

from dataclasses import replace
from typing import Protocol

from .config import Config
from .direction import run_until_idle
from .models import Direction, Elevator, Passenger

INFINITE_COST = float("inf")


class Scheduler(Protocol):
    name: str

    def assign(self, passenger: Passenger, elevators: list[Elevator], now: int) -> int: ...


def lowest_index(scores: list[float]) -> int:
    """Index of the smallest score; ties go to the lowest index."""
    best = 0
    for index in range(1, len(scores)):
        if scores[index] < scores[best]:
            best = index
    return best


class RoundRobin:
    name = "round-robin"

    def __init__(self, config: Config) -> None:
        self.turn = 0

    def assign(self, passenger: Passenger, elevators: list[Elevator], now: int) -> int:
        index = self.turn % len(elevators)
        self.turn += 1
        return index


def floors_to_reach(elevator: Elevator, passenger: Passenger) -> int:
    """Floors the elevator travels to reach the passenger moving their way, under collective control."""
    f = elevator.floor
    s = passenger.source
    floors = [f, s] + elevator.stops()
    top = max(floors)
    bot = min(floors)
    if elevator.direction == Direction.IDLE:
        return abs(f - s)
    if elevator.direction == Direction.UP:
        if passenger.direction == Direction.UP and s >= f:
            return s - f
        if passenger.direction == Direction.DOWN:
            return (top - f) + (top - s)
        return (top - f) + (top - bot) + (s - bot)
    if passenger.direction == Direction.DOWN and s <= f:
        return f - s
    if passenger.direction == Direction.UP:
        return (f - bot) + (s - bot)
    return (f - bot) + (top - bot) + (top - s)


class NearestCar:
    name = "nearest-car"

    def __init__(self, config: Config) -> None:
        self.config = config

    def assign(self, passenger: Passenger, elevators: list[Elevator], now: int) -> int:
        distances = []
        for elevator in elevators:
            distances.append(floors_to_reach(elevator, passenger))
        return lowest_index(distances)


def clone_elevator(elevator: Elevator) -> Elevator:
    """A copy of the elevator and its passengers that a trial allocation can change freely."""
    inside = [replace(p) for p in elevator.inside]
    waiting = [replace(p) for p in elevator.waiting]
    return replace(elevator, inside=inside, waiting=waiting)


def trial_limit(elevator: Elevator, config: Config) -> int:
    """Time units a trial allocation may run before it counts as stuck."""
    # Each passenger has 2 events, each within two trips of the shaft and one dwell of the last; +1 covers a hold already running.
    passengers = len(elevator.inside) + len(elevator.waiting)
    return 2 * (passengers + 1) * (2 * config.floors + config.dwell_time)


DEFAULT_MAX_WAIT = "default"


class LowestCost:
    name = "lowest-cost"

    def __init__(self, config: Config, max_wait: int | None | str = DEFAULT_MAX_WAIT, penalty: int = 1000) -> None:
        self.config = config
        self.max_wait = config.default_max_wait if max_wait == DEFAULT_MAX_WAIT else max_wait
        self.penalty = penalty

    def assign(self, passenger: Passenger, elevators: list[Elevator], now: int) -> int:
        costs = []
        for elevator in elevators:
            costs.append(self.incremental_cost(elevator, passenger, now))
        return lowest_index(costs)

    def incremental_cost(self, elevator: Elevator, passenger: Passenger, now: int) -> float:
        """Trial allocation cost of the elevator with the passenger, minus without."""
        without = self.trial_cost(clone_elevator(elevator), now)
        with_passenger = clone_elevator(elevator)
        with_passenger.waiting.append(replace(passenger))
        cost = self.trial_cost(with_passenger, now)
        if cost == INFINITE_COST:
            return INFINITE_COST
        return cost - without

    def trial_cost(self, elevator: Elevator, now: int) -> float:
        """Run the elevator until it has no stops and add up its passengers' costs; infinite if it never finishes."""
        passengers = elevator.inside + elevator.waiting
        if not run_until_idle(elevator, now, self.config, trial_limit(elevator, self.config)):
            return INFINITE_COST
        total = 0
        for p in passengers:
            total += self.passenger_cost(p)
        return total

    def passenger_cost(self, p: Passenger) -> int:
        """Total time, plus the penalty for every time unit of wait time past the maximum wait time."""
        if self.max_wait is None:
            return p.total
        return p.total + self.penalty * max(0, p.wait - self.max_wait)


SCHEDULERS = ("round-robin", "nearest-car", "lowest-cost")
NAMES = SCHEDULERS + ("lowest-cost-nocap", "zoned")


def make_scheduler(name: str, config: Config) -> Scheduler:
    """Build a scheduler by name; `lowest-cost-nocap` turns the maximum wait time off."""
    if name == "zoned":
        from .extensions.zoning import Zoned  # imported here because zoning builds on LowestCost above
        return Zoned(config)
    if name == "round-robin":
        return RoundRobin(config)
    if name == "nearest-car":
        return NearestCar(config)
    if name == "lowest-cost":
        return LowestCost(config)
    if name == "lowest-cost-nocap":
        scheduler = LowestCost(config, max_wait=None)
        scheduler.name = "lowest-cost-nocap"
        return scheduler
    raise ValueError(f"unknown scheduler {name!r}, expected one of {', '.join(NAMES)}")
