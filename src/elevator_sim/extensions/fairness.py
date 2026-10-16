"""The fairness against efficiency study: lowest cost under each maximum wait time and dwell time."""

from __future__ import annotations

from dataclasses import dataclass, replace

from ..scenarios import Scenario, scenarios, table_row
from ..scheduler import LowestCost
from ..simulation import Simulation
from ..stats import summarize

DEFAULT_SCENARIOS = ("20f-4x10-demand100-interfloor", "20f-4x10-demand100-up-peak")
DEFAULT_MAX_WAITS = (None, 57, 40, 30, 20)
DEFAULT_DWELL_TIMES = (0, 3)
COLUMNS = ("scenario", "dwell time", "maximum wait time", "mean total", "p95 wait", "longest wait")


@dataclass(frozen=True)
class FairnessRow:
    scenario: str
    dwell_time: int
    max_wait: int | None
    mean_total: float  # efficiency
    p95_wait: int  # fairness
    longest_wait: int  # fairness


def with_dwell_time(scenario: Scenario, dwell_time: int) -> Scenario:
    """The same scenario with another dwell time; its passengers do not change."""
    return replace(scenario, config=replace(scenario.config, dwell_time=dwell_time))


def study_row(scenario: Scenario, max_wait: int | None) -> FairnessRow:
    """Run lowest cost with one maximum wait time and summarize the run."""
    scheduler = LowestCost(scenario.config, max_wait=max_wait)
    summary = summarize(Simulation(scenario.config, scheduler).run(scenario.requests()))
    return FairnessRow(
        scenario.name, scenario.config.dwell_time, max_wait,
        summary.total.mean, summary.wait.p95, summary.wait.max,
    )


def fairness_study(
    scenario_names=DEFAULT_SCENARIOS, max_waits=DEFAULT_MAX_WAITS, dwell_times=DEFAULT_DWELL_TIMES,
) -> list[FairnessRow]:
    """One row per scenario, dwell time and maximum wait time, in that order; None turns the maximum off."""
    known = scenarios()
    for name in scenario_names:
        if name not in known:
            raise ValueError(f"unknown scenario {name!r}, expected one of {', '.join(known)}")
    rows = []
    for name in scenario_names:
        for dwell_time in dwell_times:
            scenario = with_dwell_time(known[name], dwell_time)
            for max_wait in max_waits:
                rows.append(study_row(scenario, max_wait))
    return rows


def fairness_table(rows: list[FairnessRow]) -> str:
    """The study as a Markdown table."""
    lines = [table_row(list(COLUMNS)), table_row(["---"] * len(COLUMNS))]
    for r in rows:
        max_wait = "none" if r.max_wait is None else r.max_wait
        lines.append(table_row([r.scenario, r.dwell_time, max_wait, f"{r.mean_total:.1f}", r.p95_wait, r.longest_wait]))
    return "\n".join(lines)
