"""Building and elevator bank settings, checked when created."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    floors: int = 20
    elevators: int = 4
    capacity: int = 10
    dwell_time: int = 0

    def __post_init__(self) -> None:
        if self.floors < 2:
            raise ValueError(f"floors must be at least 2, got {self.floors}")
        if self.elevators < 1:
            raise ValueError(f"elevators must be at least 1, got {self.elevators}")
        if self.capacity < 1:
            raise ValueError(f"capacity must be at least 1, got {self.capacity}")
        if self.dwell_time < 0:
            raise ValueError(f"dwell_time must be 0 or more, got {self.dwell_time}")

    @property
    def handling_capacity(self) -> float:
        """Passengers per time unit the elevator bank carries running full, end to end, no stops."""
        return self.elevators * self.capacity / (2 * (self.floors - 1))

    @property
    def default_max_wait(self) -> int:
        """Three trips of the shaft, the longest a free elevator takes to reach anyone."""
        return 3 * (self.floors - 1)
