"""Turn runs into JSON traces for the live page: each time unit, each assignment's scores, and summary metrics."""

from __future__ import annotations

import csv
import io
import math
import time
from dataclasses import dataclass, replace

from ..core.config import Config
from ..core.direction import run_until_idle
from ..extensions.express import express_bank, servable
from ..extensions.zoning import Zoned, zone_floor
from .files import parse_requests
from ..core.models import Elevator, Event, Passenger, Request
from ..benchmark.scenarios import scenarios
from ..core.scheduler import INFINITE_COST, LowestCost, NearestCar, RoundRobin, clone_elevator, floors_to_reach
from ..benchmark.schedulers import NAMES
from ..core.scheduler import lowest_index, trial_limit
from ..benchmark.schedulers import make_scheduler
from ..core.simulation import Simulation
from ..benchmark.stats import summarize
from ..benchmark.traffic import PATTERNS, Segment, generate

FORMAT = 1
MAX_TIME_UNITS = 5000
MAX_PASSENGERS = 1000
MAX_SECONDS = 20
MAX_SCHEDULERS = 3
LIMITS = {
    "floors": (2, 60), "elevators": (1, 10), "capacity": (1, 20), "dwell_time": (0, 5),
    "demand": (0, 200), "run_length": (1, 1000), "seed": (0, 2**31 - 1),
}
DEFAULTS = {"floors": 20, "elevators": 4, "capacity": 10, "dwell_time": 0, "demand": 100,
            "pattern": "interfloor", "seed": 1, "run_length": 300, "layout": "all"}
GENERATED = ("demand", "pattern", "seed", "run_length")
BUILDING = ("floors", "elevators", "capacity", "layout")
SHARED = ("dwell_time", "max_wait", "schedulers")
KNOWN = ("scenario", "requests") + BUILDING + GENERATED + SHARED
LAYOUTS = ("all", "express")
STUCK = "stuck"  # a trial allocation that never finished, so its cost is infinite

# S clears elevator A to floor 2, R rides B up to 18; at time 13 the state matches the deck's Q example.
Q_EXAMPLE = "time,id,source,dest\n0,S,1,2\n1,R,1,18\n13,P,10,2\n13,Q,9,16\n"
# Three passengers on floor 2: nearest car sends all to A, round robin splits them, lowest cost sends both down trips to B.
SMALLEST = "time,id,source,dest\n0,p1,2,4\n0,p2,2,1\n1,p3,2,1\n"

PRESETS = {
    "Rush hour": {"floors": 20, "elevators": 4, "capacity": 10, "demand": 100, "pattern": "up-peak", "run_length": 300},
    "Random floors": {"floors": 20, "elevators": 4, "capacity": 10, "demand": 100, "pattern": "interfloor", "run_length": 300},
    "One elevator": {"floors": 20, "elevators": 1, "capacity": 1, "demand": 80, "pattern": "interfloor", "run_length": 1000},
    "Tall building": {"floors": 60, "elevators": 4, "capacity": 10, "demand": 80, "pattern": "interfloor", "run_length": 300},
    "Express, 40 floors": {"floors": 40, "elevators": 4, "capacity": 10, "demand": 100, "pattern": "up-peak",
                           "run_length": 300, "layout": "express"},
    "Two elevators, Q": {"requests": Q_EXAMPLE, "floors": 20, "elevators": 2, "capacity": 10},
    "Smallest, 4 floors": {"requests": SMALLEST, "floors": 4, "elevators": 2, "capacity": 4},
}


@dataclass(frozen=True)
class Run:
    config: Config
    requests: list[Request]
    schedulers: list[str]
    max_wait: int | str | None


# Checking the parameters


def whole(params: dict, key: str) -> int:
    """The parameter as a whole number inside its limits, or ValueError."""
    value = params.get(key, DEFAULTS.get(key))
    low, high = LIMITS[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} must be a whole number, got {value!r}")
    if not low <= value <= high:
        raise ValueError(f"{key} must be between {low} and {high}, got {value}")
    return value


def percent(params: dict) -> float:
    """Demand in percent of handling capacity, as a fraction."""
    value = params.get("demand", DEFAULTS["demand"])
    low, high = LIMITS["demand"]
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not low <= value <= high:
        raise ValueError(f"demand must be a percent between {low} and {high}, got {value!r}")
    return value / 100


def check_max_wait(value) -> None:
    """Raise ValueError unless the maximum wait time is default, off, None or a whole number 0 or more."""
    if value in ("default", "off", None):
        return
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"max_wait must be default, off or a whole number 0 or more, got {value!r}")


def check_schedulers(names) -> list[str]:
    """One to three known schedulers, each once."""
    if not isinstance(names, list) or not names:
        raise ValueError("pick at least one scheduler")
    if len(names) > MAX_SCHEDULERS:
        raise ValueError(f"compare at most {MAX_SCHEDULERS} schedulers, got {len(names)}")
    for name in names:
        if name not in NAMES:
            raise ValueError(f"unknown scheduler {name!r}, expected one of {', '.join(NAMES)}")
        if names.count(name) > 1:
            raise ValueError(f"scheduler {name} is listed twice")
    return list(names)


def refuse(params: dict, keys: tuple[str, ...], what: str) -> None:
    """Raise ValueError if any of the keys is given, since it does not apply to `what`."""
    for key in keys:
        if key in params:
            raise ValueError(f"{key} does not apply to {what}")


def request_text(requests) -> str:
    """CSV text from a request file's text or a list of {time, id, source, dest} objects."""
    if isinstance(requests, str):
        return requests
    if not isinstance(requests, list):
        raise ValueError("requests must be CSV text or a list of requests")
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["time", "id", "source", "dest"])
    for row in requests:
        if not isinstance(row, dict) or sorted(row) != ["dest", "id", "source", "time"]:
            raise ValueError("each request needs time, id, source and dest, and nothing else")
        writer.writerow([row["time"], row["id"], row["source"], row["dest"]])
    return buffer.getvalue()


def highest_floor(requests: list[Request]) -> int:
    """The highest floor named in the requests, or 0 when there are none."""
    return max([max(r.source, r.dest) for r in requests], default=0)


def building(params: dict, floors: int) -> Config:
    """The building and elevator bank, with the express layout if asked for."""
    elevators = whole(params, "elevators")
    config = Config(floors=floors, elevators=elevators, capacity=whole(params, "capacity"), dwell_time=whole(params, "dwell_time"))
    layout = params.get("layout", DEFAULTS["layout"])
    if layout not in LAYOUTS:
        raise ValueError(f"layout must be all or express, got {layout!r}")
    if layout == "all":
        return config
    if elevators < 2:
        raise ValueError("the express layout needs at least 2 elevators")
    local = elevators // 2
    return replace(config, served_floors=express_bank(floors, local=local, express=elevators - local, split=floors // 2))


def from_scenario(params: dict) -> tuple[Config, list[Request]]:
    """A named scenario's settings and passengers; only the dwell time may change."""
    if "requests" in params:
        raise ValueError("give a scenario or a request list, not both")
    refuse(params, BUILDING + GENERATED, "a named scenario")
    known = scenarios()
    name = params["scenario"]
    if name not in known:
        raise ValueError(f"unknown scenario {name!r}, expected one of {', '.join(known)}")
    scenario = known[name]
    config = scenario.config
    if "dwell_time" in params:
        config = replace(config, dwell_time=whole(params, "dwell_time"))
    return config, scenario.requests()


def from_requests(params: dict) -> tuple[Config, list[Request]]:
    """A request list, checked like the request file; floors default to the highest floor, at least 20."""
    refuse(params, GENERATED, "a request list")
    requests = parse_requests(request_text(params["requests"]))
    floors = params.get("floors", max(highest_floor(requests), DEFAULTS["floors"]))
    config = building({**params, "floors": floors}, whole({"floors": floors}, "floors"))
    Simulation(config, RoundRobin(config)).check_floors(requests)
    return config, requests


def generated(params: dict) -> tuple[Config, list[Request]]:
    """Synthetic passengers for one demand level and pattern, the same for the same seed."""
    config = building(params, whole(params, "floors"))
    pattern = params.get("pattern", DEFAULTS["pattern"])
    if pattern not in PATTERNS:
        raise ValueError(f"pattern must be one of {', '.join(PATTERNS)}, got {pattern!r}")
    segment = Segment(whole(params, "run_length"), percent(params), pattern)
    expected = round(segment.demand * config.handling_capacity * segment.duration)
    if expected > 2 * MAX_PASSENGERS:
        raise ValueError(f"about {expected} passengers is more than {MAX_PASSENGERS}; lower the demand or the run length")
    plain = replace(config, served_floors=None)
    return config, servable(generate(plain, [segment], whole(params, "seed")), config)


def build_run(params: dict) -> Run:
    """Check every parameter and build the run, or raise ValueError with the reason."""
    if not isinstance(params, dict):
        raise ValueError("parameters must be a JSON object")
    for key in params:
        if key not in KNOWN:
            raise ValueError(f"unknown parameter {key!r}, expected one of {', '.join(KNOWN)}")
    if "scenario" in params:
        config, requests = from_scenario(params)
    elif "requests" in params:
        config, requests = from_requests(params)
    else:
        config, requests = generated(params)
    if len(requests) > MAX_PASSENGERS:
        raise ValueError(f"{len(requests)} passengers is more than {MAX_PASSENGERS}; lower the demand or the run length")
    max_wait = params.get("max_wait", "default")
    check_max_wait(max_wait)
    return Run(config, requests, check_schedulers(params.get("schedulers", ["lowest-cost"])), max_wait)


# Scheduler scores


def build_scheduler(name: str, config: Config, max_wait="default"):
    """The scheduler by name, with the maximum wait time for lowest cost and zoned."""
    check_max_wait(max_wait)
    if name not in ("lowest-cost", "zoned"):
        return make_scheduler(name, config)
    cost = LowestCost(config) if max_wait == "default" else LowestCost(config, max_wait=None if max_wait in ("off", None) else max_wait)
    if name == "lowest-cost":
        return cost
    zoned = Zoned(config)
    zoned.cost = cost
    return zoned


def json_number(value: float):
    """A JSON-safe score: infinite costs become STUCK."""
    return value if math.isfinite(value) else STUCK


def trial_side(cost: LowestCost, elevator: Elevator, now: int, extra: Passenger | None) -> tuple[float, dict]:
    """One trial allocation, as LowestCost.trial_cost runs it, with each passenger's tally."""
    copy = clone_elevator(elevator)
    if extra is not None:
        copy.waiting.append(replace(extra))
    passengers = copy.inside + copy.waiting
    if not run_until_idle(copy, now, cost.config, trial_limit(copy, cost.config)):
        return INFINITE_COST, {"sum": STUCK, "rows": [[p.id, p.boarded_at, p.arrived_at, None] for p in passengers]}
    rows = [[p.id, p.boarded_at, p.arrived_at, cost.passenger_cost(p)] for p in passengers]
    total = sum(row[3] for row in rows)
    return total, {"sum": total, "rows": rows}


def trial_pair(cost: LowestCost, elevator: Elevator, p: Passenger, now: int) -> tuple[float, dict]:
    """The incremental cost of the passenger on this elevator, and both trial allocations behind it."""
    without, without_side = trial_side(cost, elevator, now, None)
    with_cost, with_side = trial_side(cost, elevator, now, p)
    score = INFINITE_COST if with_cost == INFINITE_COST else with_cost - without
    return score, {"elevator": elevator.index, "with": with_side, "without": without_side}


def cost_scores(cost: LowestCost, p: Passenger, elevators: list[Elevator], now: int, entry: dict) -> list[float]:
    """Scores by trial allocation for the given elevators; the trials go into the entry."""
    scores = []
    for elevator in elevators:
        score, trial = trial_pair(cost, elevator, p, now)
        scores.append(score)
        entry["trials"].append(trial)
    return scores


def score(scheduler, p: Passenger, elevators: list[Elevator], now: int, total: int) -> dict:
    """What the scheduler weighs for this passenger, by real elevator index, and the elevator it picks."""
    entry = {"t": now, "passenger": p.id, "offered": [e.index for e in elevators], "scores": [None] * total}
    scored = elevators
    if isinstance(scheduler, RoundRobin):
        entry.update(rule="turn", turn=scheduler.turn)
        scores = [(k - scheduler.turn) % len(elevators) for k in range(len(elevators))]
    elif isinstance(scheduler, NearestCar):
        entry["rule"] = "floors"
        scores = [floors_to_reach(e, p) for e in elevators]
    elif isinstance(scheduler, LowestCost):
        entry.update(rule="cost", trials=[])
        scores = cost_scores(scheduler, p, elevators, now, entry)
    elif isinstance(scheduler, Zoned):
        floor = zone_floor(p)
        band = next(b for b in scheduler.bands if b[0] <= floor <= b[1])
        scored = [e for e in elevators if scheduler.in_band(e, floor)] or elevators
        entry.update(rule="cost", band=list(band), trials=[])
        scores = cost_scores(scheduler.cost, p, scored, now, entry)
    else:
        raise ValueError(f"no score for scheduler {scheduler.name}")
    for elevator, value in zip(scored, scores):
        entry["scores"][elevator.index] = json_number(value)
    entry["pick"] = scored[lowest_index(scores)].index
    return entry


class Recorder:
    """Wraps a scheduler: records each assignment's scores, then lets the scheduler itself choose."""

    def __init__(self, scheduler, total: int) -> None:
        self.inner = scheduler
        self.name = scheduler.name
        self.total = total
        self.assignments: list[dict] = []

    def assign(self, passenger: Passenger, elevators: list[Elevator], now: int) -> int:
        entry = score(self.inner, passenger, elevators, now, self.total)
        index = self.inner.assign(passenger, elevators, now)
        if elevators[index].index != entry["pick"]:
            raise AssertionError(f"trace scores pick elevator {entry['pick']}, the scheduler picked {elevators[index].index}")
        self.assignments.append(entry)
        return index


# The trace


def effective_max_wait(scheduler) -> int | None:
    """The maximum wait time the scheduler uses, or None if it uses none."""
    if isinstance(scheduler, LowestCost):
        return scheduler.max_wait
    if isinstance(scheduler, Zoned):
        return scheduler.cost.max_wait
    return None


def config_json(config: Config, scheduler) -> dict:
    """The settings of a run as plain JSON."""
    served = None if config.served_floors is None else [sorted(s) for s in config.served_floors]
    return {"floors": config.floors, "elevators": config.elevators, "capacity": config.capacity,
            "dwell_time": config.dwell_time, "served_floors": served, "max_wait": effective_max_wait(scheduler)}


def passenger_json(p: Passenger) -> dict:
    """One passenger's request and times."""
    return {"id": p.id, "time": p.request.time, "source": p.source, "dest": p.dest, "elevator": p.elevator,
            "boarded": p.boarded_at, "arrived": p.arrived_at, "wait": p.wait, "total": p.total}


def summary_json(result, elevators: int) -> dict:
    """Mean, p95 and longest wait time, the same for total time, and passengers per elevator."""
    if not result.passengers:
        return {"passengers": 0, "time_units": result.time_units, "wait": None, "total": None,
                "served_per_elevator": [0] * elevators}
    s = summarize(result)
    return {"passengers": s.passengers, "time_units": s.time_units,
            "wait": {"mean": s.wait.mean, "p95": s.wait.p95, "max": s.wait.max},
            "total": {"mean": s.total.mean, "p95": s.total.p95, "max": s.total.max},
            "served_per_elevator": s.served_per_elevator}


def unit_json(now: int, floors: list[int], elevators: list[Elevator], events: list[Event]) -> dict:
    """One time unit: floors at its start; directions, riders and waiting passengers after the step; its events."""
    return {"t": now, "floors": floors, "dirs": [int(e.direction) for e in elevators],
            "inside": [[p.id for p in e.inside] for e in elevators], "waiting": [[p.id for p in e.waiting] for e in elevators],
            "events": [[e.kind, e.passenger, e.elevator, e.floor] for e in events]}


def record(config: Config, scheduler_name: str, requests: list[Request], max_wait="default",
           cap: int = MAX_TIME_UNITS, budget: float = MAX_SECONDS) -> dict:
    """Run the simulation once and return its trace; ValueError past `cap` time units or `budget` seconds."""
    scheduler = build_scheduler(scheduler_name, config, max_wait)
    recorder = Recorder(scheduler, config.elevators)
    units: list[dict] = []
    state = {"floors": [1] * config.elevators, "seen": 0}
    start = time.perf_counter()

    def watch(now: int, elevators: list[Elevator], events: list[Event]) -> None:
        if time.perf_counter() - start >= budget:
            raise ValueError(f"the run took longer than {budget} seconds; lower the demand or the run length")
        units.append(unit_json(now, state["floors"], elevators, events[state["seen"]:]))
        state["floors"] = [e.floor for e in elevators]
        state["seen"] = len(events)

    try:
        result = Simulation(config, recorder).run(requests, max_time_units=cap, watch=watch)
    except RuntimeError:
        raise ValueError(f"the run did not finish within the cap of {cap} time units; lower the demand or the run length") from None
    return {"scheduler": scheduler.name, "config": config_json(config, scheduler),
            "passengers": [passenger_json(p) for p in result.passengers], "units": units,
            "assignments": recorder.assignments, "summary": summary_json(result, config.elevators)}


def trace_runs(params: dict) -> dict:
    """Check the parameters, then trace every chosen scheduler on the same passengers."""
    run = build_run(params)
    traces = [record(run.config, name, run.requests, run.max_wait) for name in run.schedulers]
    return {"format": FORMAT, "traces": traces}
