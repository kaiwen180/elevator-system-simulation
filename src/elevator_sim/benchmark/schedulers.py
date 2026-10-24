"""Schedulers by name, for the command line, the scenarios and the live page."""

from __future__ import annotations

from ..core.config import Config
from ..core.scheduler import LowestCost, NearestCar, RoundRobin, Scheduler

SCHEDULERS = ("round-robin", "nearest-car", "lowest-cost")
NAMES = SCHEDULERS + ("lowest-cost-nocap", "zoned")


def make_scheduler(name: str, config: Config) -> Scheduler:
    """Build a scheduler by name; `lowest-cost-nocap` turns the maximum wait time off."""
    if name == "zoned":
        from ..extensions.zoning import Zoned  # imported here because zoning imports this package's traffic module
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
