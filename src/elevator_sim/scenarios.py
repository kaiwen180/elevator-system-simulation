"""The named extreme scenarios and a comparison report across schedulers."""

from __future__ import annotations

from dataclasses import dataclass

from .config import Config
from .scheduler import make_scheduler
from .models import Request, Result
from .simulation import Simulation
from .stats import summarize
from .traffic import Segment, daily_profile, generate

HORIZON = 300
SMALLEST_HORIZON = 1000
TALLEST_SMALLEST_HORIZON = 1500
LARGEST_SMALL_HORIZON = 200
DAILY_SCALE = 60

BUILDINGS = {"small": 5, "typical": 20, "tall": 60, "tallest": 160}
BANKS = {"smallest": (1, 1), "small": (2, 4), "typical": (4, 10), "largest": (10, 20)}
DEMANDS = (0.2, 0.5, 0.8, 1.0, 1.2)

COLUMNS = (
    "scenario", "scheduler", "passengers",
    "mean wait", "p95 wait", "max wait",
    "mean total", "p95 total", "max total", "time units",
)


@dataclass(frozen=True)
class Scenario:
    name: str
    config: Config
    segments: tuple[Segment, ...]
    seed: int = 1

    def requests(self) -> list[Request]:
        """The scenario's passengers, the same every time for the same seed."""
        return generate(self.config, list(self.segments), self.seed)


def scenario_name(config: Config, demand: float, pattern: str) -> str:
    """For example 20f-4x10-demand080-interfloor: floors, elevators x capacity, demand in percent, pattern."""
    return f"{config.floors}f-{config.elevators}x{config.capacity}-demand{round(demand * 100):03d}-{pattern}"


def steady(building: str, bank: str, demand: float, pattern: str = "interfloor", horizon: int = HORIZON) -> Scenario:
    """A scenario with one demand level and one pattern for the whole horizon."""
    elevators, capacity = BANKS[bank]
    config = Config(floors=BUILDINGS[building], elevators=elevators, capacity=capacity)
    return Scenario(scenario_name(config, demand, pattern), config, (Segment(horizon, demand, pattern),))


def daily() -> Scenario:
    """The typical building and elevator bank through a quiet, peak, midday, peak, quiet day."""
    config = Config(floors=BUILDINGS["typical"], elevators=4, capacity=10)
    name = f"{config.floors}f-{config.elevators}x{config.capacity}-daily"
    return Scenario(name, config, tuple(daily_profile(DAILY_SCALE)))


def scenario_list() -> list[Scenario]:
    """The cells of the test plan's matrix that the tests run, in report order."""
    chosen = []
    for demand in DEMANDS:
        chosen.append(steady("typical", "typical", demand))
    for building in BUILDINGS:
        chosen.append(steady(building, "typical", 0.8))
    for bank in BANKS:
        horizon = SMALLEST_HORIZON if bank == "smallest" else HORIZON
        chosen.append(steady("typical", bank, 0.8, horizon=horizon))
    # 1 elevator of 1 in 160 floors carries about 1 passenger per 318 time units, so it needs a long horizon.
    chosen.append(steady("tallest", "smallest", 1.0, horizon=TALLEST_SMALLEST_HORIZON))
    # 10 elevators of 20 in 5 floors get 25 passengers per time unit, so a short horizon keeps it fast.
    chosen.append(steady("small", "largest", 1.0, horizon=LARGEST_SMALL_HORIZON))
    # Interfloor elevators rarely fill, so overload only shows in a peak: the 120% checks use up-peak.
    for demand in (0.8, 1.0, 1.2):
        chosen.append(steady("typical", "typical", demand, pattern="up-peak"))
    chosen.append(daily())
    return chosen


def scenarios() -> dict[str, Scenario]:
    """Every scenario named in docs/test-plan.md, keyed by name."""
    by_name = {}
    for scenario in scenario_list():
        by_name[scenario.name] = scenario
    return by_name


def run_scenario(scenario: Scenario, scheduler: str, requests: list[Request] | None = None) -> Result:
    """Run one scenario under one scheduler, on its own passengers unless others are given."""
    if requests is None:
        requests = scenario.requests()
    simulation = Simulation(scenario.config, make_scheduler(scheduler, scenario.config))
    return simulation.run(requests)


def table_row(cells: list) -> str:
    """One Markdown table row."""
    return "| " + " | ".join(str(cell) for cell in cells) + " |"


def result_row(name: str, scheduler: str, result: Result) -> str:
    """The table row for one finished run."""
    summary = summarize(result)
    wait = summary.wait
    total = summary.total
    return table_row([
        name, scheduler, summary.passengers,
        f"{wait.mean:.1f}", wait.p95, wait.max,
        f"{total.mean:.1f}", total.p95, total.max, summary.time_units,
    ])


def compare(names: list[str], schedulers: list[str]) -> str:
    """Run each scenario under each scheduler; return a Markdown table of results."""
    known = scenarios()
    for name in names:
        if name not in known:
            raise ValueError(f"unknown scenario {name!r}, expected one of {', '.join(known)}")
    lines = [table_row(list(COLUMNS)), table_row(["---"] * len(COLUMNS))]
    for name in names:
        for scheduler in schedulers:
            lines.append(result_row(name, scheduler, run_scenario(known[name], scheduler)))
    return "\n".join(lines)
