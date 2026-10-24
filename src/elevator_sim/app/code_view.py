"""The core functions the live page shows beside the picture, and the lines each moment of a run lights up."""

from __future__ import annotations

import inspect
import textwrap
from pathlib import Path

from ..core import direction
from ..core.scheduler import LowestCost, RoundRobin, floors_to_reach
from ..core.simulation import Simulation

PACKAGE = Path(__file__).resolve().parent.parent
UP = "if elevator.direction == Direction.UP:"
RANGE = ["floors = [f, s] + elevator.stops()", "top = max(floors)", "bot = min(floors)"]

# Each view: a core function, and named groups of its lines that the page lights together.
VIEWS = {
    "clock": (Simulation.run, {
        "reveal": ["for p in schedule.pop(now, []):"],
        "assign": ["self.assign(p, elevators, now, events)"],
        "log": ["positions.append("],
        "move": ["for elevator in elevators:", "step(elevator, now, self.config, events)"],
        "done": ["if revealed == len(passengers) and all_idle(elevators):", "return Result("],
    }),
    "step": (direction.step, {
        "unload": ["left = unload("],
        "board": ["boarded = board("],
        "move": ["move(elevator, config)"],
    }),
    "moving": (direction.choose_moving, {
        "reverse": ["if stop_ahead(elevator):", "if elevator.stops():", "return Direction(-elevator.direction)"],
    }),
    "turn": (RoundRobin.assign, {
        "turn": ["index = self.turn % len(elevators)", "self.turn += 1", "return index"],
    }),
    "floors": (floors_to_reach, {
        "idle": ["if elevator.direction == Direction.IDLE:", "return abs(f - s)"],
        "up-ahead": [UP, "if passenger.direction == Direction.UP and s >= f:", "return s - f"],
        "up-turn": [UP, *RANGE, "if passenger.direction == Direction.DOWN:", "return (top - f) + (top - s)"],
        "up-behind": [UP, *RANGE, "return (top - f) + (top - bot) + (s - bot)"],
        "down-ahead": ["if passenger.direction == Direction.DOWN and s <= f:", "return f - s"],
        "down-turn": [*RANGE, "if passenger.direction == Direction.UP:", "return (f - bot) + (s - bot)"],
        "down-behind": [*RANGE, "return (f - bot) + (top - bot) + (top - s)"],
    }),
    "cost": (LowestCost.incremental_cost, {
        "trial": ["without = self.trial_cost(clone_elevator(elevator), now)", "with_passenger = clone_elevator(elevator)",
                  "with_passenger.waiting.append(replace(passenger))", "cost = self.trial_cost(with_passenger, now)",
                  "return cost - without"],
        "stuck": ["if cost == INFINITE_COST:", "return INFINITE_COST"],
    }),
}


def view(fn, groups: dict[str, list[str]]) -> dict:
    """The function's dedented lines, its file and first line number, and the line indexes of each group."""
    raw, start = inspect.getsourcelines(fn)
    lines = textwrap.dedent("".join(raw)).splitlines()
    marks = {}
    for name, anchors in groups.items():
        hits: set[int] = set()
        for anchor in anchors:
            found = [i for i, line in enumerate(lines) if anchor in line]
            if not found:
                raise LookupError(f"{fn.__qualname__}: no line holds {anchor!r}")
            hits.update(found)
        marks[name] = sorted(hits)
    file = Path(inspect.getsourcefile(fn)).resolve().relative_to(PACKAGE).as_posix()
    return {"name": fn.__qualname__, "file": file, "start": start, "lines": lines, "groups": marks}


def code_views() -> dict:
    """What GET /api/code returns: every view, read from the code as it is now."""
    return {name: view(fn, groups) for name, (fn, groups) in VIEWS.items()}
