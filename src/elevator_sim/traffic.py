"""Synthetic passengers: traffic patterns, demand levels and daily profiles."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from .config import Config
from .models import Request

PATTERNS = ("up-peak", "down-peak", "interfloor")
LOBBY = 1
PEAK_SHARE = 0.85


@dataclass(frozen=True)
class Segment:
    duration: int
    demand: float  # 1.0 is the elevator bank's handling capacity
    pattern: str


def generate(config: Config, segments: list[Segment], seed: int) -> list[Request]:
    """Poisson arrivals per time unit for each segment in turn, ids p1, p2, ... in time order."""
    rng = random.Random(seed)
    requests: list[Request] = []
    start = 0
    for segment in segments:
        check_segment(segment)
        mean = segment.demand * config.handling_capacity
        for time in range(start, start + segment.duration):
            for _ in range(poisson(rng, mean)):
                source, dest = choose_trip(rng, config.floors, segment.pattern)
                requests.append(Request(time, f"p{len(requests) + 1}", source, dest))
        start += segment.duration
    return requests


def check_segment(segment: Segment) -> None:
    """Raise ValueError if the segment cannot be generated."""
    if segment.pattern not in PATTERNS:
        raise ValueError(f"unknown pattern {segment.pattern!r}, expected one of {PATTERNS}")
    if segment.demand < 0:
        raise ValueError(f"demand must be 0 or more, got {segment.demand}")
    if segment.duration <= 0:
        raise ValueError(f"duration must be positive, got {segment.duration}")


def poisson(rng: random.Random, mean: float) -> int:
    """One Poisson draw with the given mean."""
    # Knuth's method: fine for the means here (under about 50), slow and imprecise for large ones.
    limit = math.exp(-mean)
    count = 0
    product = rng.random()
    while product > limit:
        count += 1
        product *= rng.random()
    return count


def choose_trip(rng: random.Random, floors: int, pattern: str) -> tuple[int, int]:
    """Source and destination for one arrival under the pattern."""
    if pattern == "up-peak" and rng.random() < PEAK_SHARE:
        return LOBBY, rng.randint(2, floors)
    if pattern == "down-peak" and rng.random() < PEAK_SHARE:
        return rng.randint(2, floors), LOBBY
    return random_pair(rng, floors)


def random_pair(rng: random.Random, floors: int) -> tuple[int, int]:
    """Two different floors, chosen uniformly."""
    source, dest = rng.sample(range(1, floors + 1), 2)
    return source, dest


def daily_profile(scale: int = 100) -> list[Segment]:
    """Quiet, morning peak at 120%, midday interfloor at 50%, evening peak at 100%, quiet."""
    return [
        Segment(scale, 0.2, "interfloor"),
        Segment(scale, 1.2, "up-peak"),
        Segment(scale, 0.5, "interfloor"),
        Segment(scale, 1.0, "down-peak"),
        Segment(scale, 0.2, "interfloor"),
    ]
