"""Building and elevator bank settings, checked when created."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    floors: int = 20
    elevators: int = 4
    capacity: int = 10
    dwell_time: int = 0
    served_floors: tuple[frozenset[int], ...] | None = None  # one set per elevator; None means every floor

    def __post_init__(self) -> None:
        if self.floors < 2:
            raise ValueError(f"floors must be at least 2, got {self.floors}")
        if self.elevators < 1:
            raise ValueError(f"elevators must be at least 1, got {self.elevators}")
        if self.capacity < 1:
            raise ValueError(f"capacity must be at least 1, got {self.capacity}")
        if self.dwell_time < 0:
            raise ValueError(f"dwell_time must be 0 or more, got {self.dwell_time}")
        if self.served_floors is not None:
            self.check_served_floors()

    def check_served_floors(self) -> None:
        """Raise ValueError unless there is one set per elevator, each inside the building."""
        if len(self.served_floors) != self.elevators:
            raise ValueError(f"served_floors needs one set per elevator, got {len(self.served_floors)} for {self.elevators}")
        for index, served in enumerate(self.served_floors):
            for floor in sorted(served):
                if not 1 <= floor <= self.floors:
                    raise ValueError(f"served_floors: elevator {index} lists floor {floor}, outside 1..{self.floors}")

    def serves(self, elevator: int, *floors: int) -> bool:
        """True if the elevator stops at every one of the floors."""
        if self.served_floors is None:
            return True
        served = self.served_floors[elevator]
        return all(floor in served for floor in floors)

    @property
    def handling_capacity(self) -> float:
        """Passengers per time unit the elevator bank carries running full, end to end, no stops."""
        return self.elevators * self.capacity / (2 * (self.floors - 1))

    @property
    def default_max_wait(self) -> int:
        """Three trips of the shaft, the longest a free elevator takes to reach anyone."""
        return 3 * (self.floors - 1)
