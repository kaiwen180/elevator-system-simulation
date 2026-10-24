"""Plain data: requests, passengers, elevators, events and the result of a run."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum


class Direction(IntEnum):
    DOWN = -1
    IDLE = 0
    UP = 1


@dataclass(frozen=True)
class Request:
    time: int
    id: str
    source: int
    dest: int

    @property
    def direction(self) -> Direction:
        return Direction.UP if self.dest > self.source else Direction.DOWN


@dataclass
class Passenger:
    request: Request
    elevator: int | None = None
    assigned_at: int | None = None
    boarded_at: int | None = None
    arrived_at: int | None = None

    @property
    def id(self) -> str:
        return self.request.id

    @property
    def source(self) -> int:
        return self.request.source

    @property
    def dest(self) -> int:
        return self.request.dest

    @property
    def direction(self) -> Direction:
        return self.request.direction

    @property
    def wait(self) -> int | None:
        return None if self.boarded_at is None else self.boarded_at - self.request.time

    @property
    def travel(self) -> int | None:
        if self.boarded_at is None or self.arrived_at is None:
            return None
        return self.arrived_at - self.boarded_at

    @property
    def total(self) -> int | None:
        return None if self.arrived_at is None else self.arrived_at - self.request.time


@dataclass
class Elevator:
    index: int
    capacity: int
    floor: int = 1
    direction: Direction = Direction.IDLE
    inside: list[Passenger] = field(default_factory=list)
    waiting: list[Passenger] = field(default_factory=list)
    hold: int = 0
    doors_cycled: bool = False

    @property
    def is_idle(self) -> bool:
        return not self.inside and not self.waiting

    @property
    def is_full(self) -> bool:
        return len(self.inside) >= self.capacity

    def stops(self) -> list[int]:
        return [p.dest for p in self.inside] + [p.source for p in self.waiting]


@dataclass(frozen=True)
class Event:
    time: int
    passenger: str
    elevator: int
    floor: int
    kind: str  # "assigned", "boarded" or "arrived"


@dataclass
class Result:
    passengers: list[Passenger]
    positions: list[list[int]]  # positions[t][elevator] is the floor of that elevator at time t
    events: list[Event]

    @property
    def time_units(self) -> int:
        return len(self.positions)
