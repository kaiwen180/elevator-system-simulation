"""The zoned scheduler: each elevator owns a band of floors above the lobby, lowest cost inside the band."""

from __future__ import annotations

from ..core.config import Config
from ..core.models import Elevator, Passenger
from ..core.scheduler import LowestCost, lowest_index
from ..benchmark.traffic import LOBBY


def split_evenly(count: int, parts: int) -> list[int]:
    """Sizes of `parts` groups that add up to `count`, the larger groups first."""
    base, extra = divmod(count, parts)
    return [base + 1 if part < extra else base for part in range(parts)]


def bands(floors: int, elevators: int) -> list[tuple[int, int]]:
    """Equal bands (lowest, highest) of the floors above the lobby: one per elevator, or one per floor if fewer."""
    upper = floors - LOBBY
    found = []
    low = LOBBY + 1
    for size in split_evenly(upper, min(elevators, upper)):
        found.append((low, low + size - 1))
        low += size
    return found


def elevator_bands(elevators: int, band_count: int) -> list[int]:
    """The band index of each elevator; with fewer bands than elevators, equal groups share a band."""
    found = []
    for band, size in enumerate(split_evenly(elevators, band_count)):
        found += [band] * size
    return found


def zone_floor(p: Passenger) -> int:
    """The floor that places the passenger in a band: the origin for trips to the lobby, else the destination."""
    return p.source if p.dest == LOBBY else p.dest


class Zoned:
    name = "zoned"

    def __init__(self, config: Config) -> None:
        self.bands = bands(config.floors, config.elevators)
        self.band_of = elevator_bands(config.elevators, len(self.bands))
        self.cost = LowestCost(config)

    def in_band(self, elevator: Elevator, floor: int) -> bool:
        """True if the floor lies in the elevator's band."""
        low, high = self.bands[self.band_of[elevator.index]]
        return low <= floor <= high

    def assign(self, passenger: Passenger, elevators: list[Elevator], now: int) -> int:
        """Lowest incremental cost among the offered elevators of the passenger's band, or among all offered if none."""
        floor = zone_floor(passenger)
        candidates = [i for i, elevator in enumerate(elevators) if self.in_band(elevator, floor)]
        if not candidates:
            candidates = list(range(len(elevators)))
        costs = [self.cost.incremental_cost(elevators[i], passenger, now) for i in candidates]
        return candidates[lowest_index(costs)]
