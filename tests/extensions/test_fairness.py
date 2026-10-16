import pytest

from elevator_sim.cli import main
from elevator_sim.extensions.fairness import (
    DEFAULT_DWELL_TIMES, DEFAULT_MAX_WAITS, DEFAULT_SCENARIOS, fairness_study, fairness_table,
)

SMALL = "5f-4x10-demand080-interfloor"
HEADER = "| scenario | dwell time | maximum wait time | mean total | p95 wait | longest wait |"


def test_the_defaults_are_the_study_in_the_readme():
    assert DEFAULT_MAX_WAITS == (None, 57, 40, 30, 20)
    assert DEFAULT_DWELL_TIMES == (0, 3)
    assert DEFAULT_SCENARIOS == ("20f-4x10-demand100-interfloor", "20f-4x10-demand100-up-peak")


def test_one_row_per_scenario_dwell_time_and_maximum_wait_time_in_that_order():
    rows = fairness_study([SMALL], [None, 10], [0, 3])
    assert [(r.scenario, r.dwell_time, r.max_wait) for r in rows] == [
        (SMALL, 0, None), (SMALL, 0, 10), (SMALL, 3, None), (SMALL, 3, 10),
    ]
    for r in rows:
        assert r.p95_wait <= r.longest_wait
        assert r.mean_total > 0


def test_the_table_has_a_header_a_rule_and_one_line_per_row():
    rows = fairness_study([SMALL], [None, 10], [3])
    lines = fairness_table(rows).splitlines()
    assert lines[0] == HEADER
    assert lines[1] == "| --- | --- | --- | --- | --- | --- |"
    assert len(lines) == 4
    assert lines[2].startswith(f"| {SMALL} | 3 | none | ")
    assert lines[3].startswith(f"| {SMALL} | 3 | 10 | ")


def test_an_unknown_scenario_is_refused():
    with pytest.raises(ValueError, match="no-such"):
        fairness_study(["no-such"], [None], [0])


def test_at_dwell_time_3_the_default_maximum_wait_time_trades_mean_total_for_a_shorter_longest_wait():
    capped, uncapped = fairness_study(["20f-4x10-demand100-interfloor"], [57, None], [3])
    assert capped.longest_wait < uncapped.longest_wait
    assert capped.mean_total > uncapped.mean_total


def test_the_cli_prints_the_table(capsys):
    assert main(["fairness", "--scenario", SMALL]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == HEADER
    assert len(lines) == 2 + len(DEFAULT_DWELL_TIMES) * len(DEFAULT_MAX_WAITS)


def test_the_cli_refuses_an_unknown_scenario(capsys):
    assert main(["fairness", "--scenario", "no-such"]) == 2
    assert "no-such" in capsys.readouterr().err
