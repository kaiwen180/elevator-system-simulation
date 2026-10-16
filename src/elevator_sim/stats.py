"""Summary numbers for a finished run."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .models import Result


@dataclass(frozen=True)
class Spread:
    min: int
    max: int
    mean: float
    p50: int
    p95: int


@dataclass(frozen=True)
class Summary:
    passengers: int
    time_units: int
    wait: Spread
    travel: Spread
    total: Spread
    served_per_elevator: list[int]


def percentile(ordered: list[int], q: float) -> int:
    """Nearest-rank percentile of an already sorted list."""
    return ordered[math.ceil(q * len(ordered)) - 1]


def spread(values: list[int]) -> Spread:
    """Nearest-rank percentiles: p = sorted[ceil(q * n) - 1]."""
    if not values:
        raise ValueError("spread needs at least one value")
    ordered = sorted(values)
    return Spread(
        min=ordered[0],
        max=ordered[-1],
        mean=sum(ordered) / len(ordered),
        p50=percentile(ordered, 0.50),
        p95=percentile(ordered, 0.95),
    )


def count_served_per_elevator(result: Result) -> list[int]:
    """Number of arrived passengers for each elevator index."""
    elevator_count = len(result.positions[0]) if result.positions else 0
    served = [0] * elevator_count
    for p in result.passengers:
        served[p.elevator] += 1
    return served


def summarize(result: Result) -> Summary:
    """Wait, travel and total spreads over every passenger in a finished run."""
    for p in result.passengers:
        if p.arrived_at is None:
            raise ValueError(f"passenger {p.id} has not arrived")
    return Summary(
        passengers=len(result.passengers),
        time_units=result.time_units,
        wait=spread([p.wait for p in result.passengers]),
        travel=spread([p.travel for p in result.passengers]),
        total=spread([p.total for p in result.passengers]),
        served_per_elevator=count_served_per_elevator(result),
    )


def format_row(label: str, s: Spread) -> str:
    """One table row: label, then min, mean, p50, p95, max."""
    return f"{label:<8}{s.min:>6}{s.mean:>7.1f}{s.p50:>6}{s.p95:>6}{s.max:>6}"


def format_summary(summary: Summary) -> str:
    """Plain-text table a person can read in a terminal."""
    served = ", ".join(f"elevator{i + 1} {n}" for i, n in enumerate(summary.served_per_elevator))
    lines = [
        f"Passengers: {summary.passengers}    Time units: {summary.time_units}",
        f"{'':<8}{'min':>6}{'mean':>7}{'p50':>6}{'p95':>6}{'max':>6}",
        format_row("Wait", summary.wait),
        format_row("Travel", summary.travel),
        format_row("Total", summary.total),
        f"Served per elevator: {served}",
    ]
    return "\n".join(lines)
