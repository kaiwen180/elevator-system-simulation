import json
from pathlib import Path

import pytest

from elevator_sim.cli import main
from elevator_sim.config import Config
from elevator_sim.extensions.zoning import Zoned
from elevator_sim.files import parse_requests
from elevator_sim.models import Request
from elevator_sim.scheduler import make_scheduler
from elevator_sim.simulation import Simulation
from elevator_sim.stats import summarize
from elevator_sim.scenarios import scenarios
from elevator_sim.trace import MAX_PASSENGERS, PRESETS, Q_EXAMPLE, build_run, build_scheduler, record, trace_runs
from elevator_sim.traffic import Segment, generate

EXAMPLE = Path(__file__).parent.parent / "examples" / "requests.csv"
TWO = Config(floors=20, elevators=2)
COST = 3  # position of the cost in a trial row: id, boarded, arrived, cost


def q_requests():
    return parse_requests(Q_EXAMPLE)


def assignment_of(trace, passenger_id):
    return next(a for a in trace["assignments"] if a["passenger"] == passenger_id)


def picks_lowest_score(a):
    scored = [(score, index) for index, score in enumerate(a["scores"]) if isinstance(score, (int, float))]
    return a["pick"] == min(scored)[1]


# The run itself


def test_a_trace_matches_simulation_run():
    config = Config()
    requests = generate(config, [Segment(100, 0.8, "interfloor")], seed=1)
    trace = record(config, "lowest-cost", requests)
    result = Simulation(config, make_scheduler("lowest-cost", config)).run(requests)
    assert [unit["floors"] for unit in trace["units"]] == result.positions
    events = [(unit["t"], *e) for unit in trace["units"] for e in unit["events"]]
    assert events == [(e.time, e.kind, e.passenger, e.elevator, e.floor) for e in result.events]
    assert [unit["t"] for unit in trace["units"]] == list(range(result.time_units))


def test_each_unit_records_floor_direction_and_who_is_inside_or_waiting():
    trace = record(Config(floors=5, elevators=1), "lowest-cost", [Request(0, "p1", 1, 5), Request(1, "p2", 4, 1)])
    first, second = trace["units"][0], trace["units"][1]
    assert first == {"t": 0, "floors": [1], "dirs": [1], "inside": [["p1"]], "waiting": [[]],
                     "events": [["assigned", "p1", 0, 1], ["boarded", "p1", 0, 1]]}
    assert (second["floors"], second["waiting"]) == ([2], [["p2"]])


def test_the_passenger_table_has_every_time():
    trace = record(Config(floors=5, elevators=1), "lowest-cost", [Request(0, "p1", 5, 1)])
    assert trace["passengers"] == [{"id": "p1", "time": 0, "source": 5, "dest": 1, "elevator": 0,
                                    "boarded": 4, "arrived": 8, "wait": 4, "total": 8}]


def test_the_trace_names_its_scheduler_and_settings():
    trace = record(TWO, "lowest-cost", q_requests(), max_wait=30)
    assert trace["scheduler"] == "lowest-cost"
    assert trace["config"] == {"floors": 20, "elevators": 2, "capacity": 10, "dwell_time": 0,
                               "served_floors": None, "max_wait": 30}


def test_a_run_past_the_cap_raises_a_clear_error():
    with pytest.raises(ValueError, match="3 time units"):
        record(Config(floors=5, elevators=1), "lowest-cost", [Request(0, "p1", 1, 5)], cap=3)


def test_a_run_past_the_time_budget_raises_a_clear_error():
    with pytest.raises(ValueError, match="seconds"):
        record(Config(floors=5, elevators=1), "lowest-cost", [Request(0, "p1", 1, 5)], budget=0)


def test_the_trace_is_plain_json():
    trace = record(TWO, "lowest-cost", q_requests())
    assert json.loads(json.dumps(trace, allow_nan=False)) == trace


# The score behind each assignment


def test_round_robin_records_the_turn():
    trace = record(TWO, "round-robin", q_requests())
    picks = [(a["turn"], a["pick"], a["scores"]) for a in trace["assignments"]]
    assert picks == [(0, 0, [0, 1]), (1, 1, [1, 0]), (2, 0, [0, 1]), (3, 1, [1, 0])]
    assert trace["assignments"][0]["rule"] == "turn"


def test_the_q_example_reaches_the_explainer_state_under_every_scheduler():
    for name in ("round-robin", "nearest-car", "lowest-cost"):
        trace = record(TWO, name, q_requests())
        q = assignment_of(trace, "Q")
        unit = trace["units"][q["t"]]
        assert (q["t"], unit["floors"], unit["inside"][1]) == (13, [2, 13], ["R"]), name
        assert [assignment_of(trace, pid)["pick"] for pid in ("S", "R", "P")] == [0, 1, 0], name


def test_nearest_car_records_floors_to_reach():
    q = assignment_of(record(TWO, "nearest-car", q_requests()), "Q")
    assert (q["rule"], q["scores"], q["pick"]) == ("floors", [7, 14], 0)


def test_lowest_cost_records_both_trial_allocations_with_each_passengers_tally():
    q = assignment_of(record(TWO, "lowest-cost", q_requests()), "Q")
    assert (q["rule"], q["scores"], q["pick"]) == ("cost", [26, 21], 1)
    assert [t["elevator"] for t in q["trials"]] == [0, 1]
    on_b = q["trials"][1]
    assert on_b["elevator"] == 1
    assert on_b["with"]["sum"] - on_b["without"]["sum"] == 21
    for trial in q["trials"]:
        for side in ("with", "without"):
            assert sum(row[COST] for row in trial[side]["rows"]) == trial[side]["sum"]
    assert [row[0] for row in on_b["with"]["rows"]] == ["R", "Q"]
    assert [row[0] for row in q["trials"][0]["without"]["rows"]] == ["P"]


def test_zoned_scores_only_the_elevators_of_the_band():
    trace = record(Config(floors=20, elevators=4), "zoned", [Request(0, "a", 1, 18)])
    a = trace["assignments"][0]
    assert (a["rule"], a["band"], a["pick"]) == ("cost", [17, 20], 3)
    assert a["scores"][:3] == [None, None, None]
    assert [t["elevator"] for t in a["trials"]] == [3]


def test_an_express_trace_offers_only_the_elevators_that_serve_the_trip():
    run = build_run({"floors": 40, "elevators": 4, "layout": "express", "pattern": "up-peak", "run_length": 40})
    trace = record(run.config, "nearest-car", run.requests)
    assert trace["config"]["served_floors"][0] == list(range(1, 21))
    for a in trace["assignments"]:
        assert len(a["offered"]) == 2
        assert [index for index, score in enumerate(a["scores"]) if score is not None] == a["offered"]


@pytest.mark.parametrize("name", ["nearest-car", "lowest-cost", "lowest-cost-nocap", "zoned"])
def test_the_pick_always_has_the_lowest_score(name):
    config = Config()
    requests = generate(config, [Segment(80, 1.0, "up-peak")], seed=2)
    trace = record(config, name, requests)
    assert len(trace["assignments"]) == len(requests)
    assert all(picks_lowest_score(a) for a in trace["assignments"])


# Summary metrics


def test_the_summary_matches_stats():
    trace = record(TWO, "lowest-cost", q_requests())
    summary = summarize(Simulation(TWO, make_scheduler("lowest-cost", TWO)).run(q_requests()))
    assert trace["summary"] == {
        "passengers": 4, "time_units": summary.time_units,
        "wait": {"mean": summary.wait.mean, "p95": summary.wait.p95, "max": summary.wait.max},
        "total": {"mean": summary.total.mean, "p95": summary.total.p95, "max": summary.total.max},
        "served_per_elevator": summary.served_per_elevator,
    }


def test_an_empty_run_has_an_empty_summary():
    trace = record(TWO, "nearest-car", [])
    assert (trace["summary"]["passengers"], trace["summary"]["wait"]) == (0, None)


# The scheduler and the maximum wait time


def test_the_maximum_wait_time_reaches_the_scheduler():
    config = Config()
    assert build_scheduler("lowest-cost", config, "default").max_wait == 57
    assert build_scheduler("lowest-cost", config, "off").max_wait is None
    assert build_scheduler("lowest-cost", config, 30).max_wait == 30
    zoned = build_scheduler("zoned", config, 30)
    assert isinstance(zoned, Zoned) and zoned.cost.max_wait == 30
    assert build_scheduler("lowest-cost-nocap", config, 30).max_wait is None


@pytest.mark.parametrize("bad", [-1, "soon", True, 2.5])
def test_a_bad_maximum_wait_time_is_refused(bad):
    with pytest.raises(ValueError, match="max_wait"):
        build_scheduler("lowest-cost", Config(), bad)


# Parameters: the same checks for the command line and the server


def test_generated_passengers_use_the_defaults():
    run = build_run({})
    assert run.config == Config()
    assert run.requests == generate(Config(), [Segment(300, 1.0, "interfloor")], seed=1)
    assert (run.schedulers, run.max_wait) == (["lowest-cost"], "default")


def test_demand_is_in_percent():
    run = build_run({"demand": 50, "pattern": "up-peak", "seed": 3, "run_length": 100})
    assert run.requests == generate(Config(), [Segment(100, 0.5, "up-peak")], seed=3)


def test_a_named_scenario_keeps_its_own_passengers():
    run = build_run({"scenario": "60f-4x10-demand080-interfloor", "dwell_time": 2})
    assert (run.config.floors, run.config.dwell_time, len(run.requests)) == (60, 2, 98)
    assert len(run.requests) > 0


def test_a_request_list_works_like_the_request_file():
    rows = [{"time": 0, "id": "a", "source": 1, "dest": 5}, {"time": 1, "id": "b", "source": 3, "dest": 1}]
    run = build_run({"requests": rows})
    assert run.requests == [Request(0, "a", 1, 5), Request(1, "b", 3, 1)]
    assert run.config.floors == 20


@pytest.mark.parametrize("params, message", [
    ({"color": "red"}, "unknown parameter"),
    ({"scenario": "no-such"}, "no-such"),
    ({"scenario": "60f-4x10-demand080-interfloor", "seed": 9}, "seed"),
    ({"requests": Q_EXAMPLE, "demand": 50}, "demand"),
    ({"requests": "time,id,source,dest\n0,a,1,5\n1,b,3,3\n"}, "line 3"),
    ({"requests": "time,id,source,dest\n0,a,1,25\n", "floors": 20}, "floor 25"),
    ({"requests": [{"time": 0, "id": "a"}]}, "time, id, source and dest"),
    ({"requests": 7}, "requests"),
    ({"floors": 1}, "floors"),
    ({"floors": 500}, "floors"),
    ({"elevators": 11}, "elevators"),
    ({"capacity": 0}, "capacity"),
    ({"dwell_time": -1}, "dwell_time"),
    ({"demand": 300}, "demand"),
    ({"run_length": 5000}, "run_length"),
    ({"pattern": "sideways"}, "pattern"),
    ({"floors": "20"}, "floors"),
    ({"seed": True}, "seed"),
    ({"layout": "express", "elevators": 1}, "2 elevators"),
    ({"layout": "diagonal"}, "layout"),
    ({"schedulers": []}, "scheduler"),
    ({"schedulers": ["fastest"]}, "fastest"),
    ({"schedulers": ["zoned", "zoned"]}, "twice"),
    ({"schedulers": ["round-robin", "nearest-car", "lowest-cost", "zoned"]}, "at most"),
    ({"scenario": "60f-4x10-demand080-interfloor", "requests": Q_EXAMPLE}, "not both"),
    ({"floors": 61}, "floors"),
    ({"layout": "express", "floors": 3, "elevators": 2}, "split"),
    ({"max_wait": "soon"}, "max_wait"),
])
def test_bad_parameters_are_refused_with_a_message(params, message):
    with pytest.raises(ValueError, match=message):
        build_run(params)


def test_the_presets_give_the_named_scenarios_passengers():
    known = scenarios()
    pairs = [("Rush hour", "20f-4x10-demand100-up-peak"), ("Random floors", "20f-4x10-demand100-interfloor"),
             ("One elevator", "20f-1x1-demand080-interfloor"), ("Tall building", "60f-4x10-demand080-interfloor"),
             ("Express, 40 floors", "40f-4x10-demand100-up-peak-express")]
    for preset, name in pairs:
        run = build_run(PRESETS[preset])
        assert (run.config, run.requests) == (known[name].config, known[name].requests()), preset


def test_the_q_preset_runs():
    run = build_run(PRESETS["Two elevators, Q"])
    assert (run.config.elevators, [r.id for r in run.requests]) == (2, ["S", "R", "P", "Q"])


def test_too_many_passengers_are_refused():
    with pytest.raises(ValueError, match=f"{MAX_PASSENGERS}"):
        build_run({"floors": 5, "elevators": 10, "capacity": 20, "run_length": 1000})
    with pytest.raises(ValueError, match=f"{MAX_PASSENGERS}"):
        build_run({"scenario": "5f-4x10-demand080-interfloor"})


def test_the_express_layout_drops_trips_it_cannot_carry():
    run = build_run({"floors": 40, "elevators": 4, "layout": "express", "pattern": "up-peak"})
    assert run.config.served_floors is not None
    for r in run.requests:
        assert any(run.config.serves(i, r.source, r.dest) for i in range(4))


def test_every_scheduler_gets_the_same_passengers():
    out = trace_runs({"schedulers": ["nearest-car", "lowest-cost"], "requests": Q_EXAMPLE, "elevators": 2})
    assert out["format"] == 1
    assert [t["scheduler"] for t in out["traces"]] == ["nearest-car", "lowest-cost"]
    ids = [[p["id"] for p in t["passengers"]] for t in out["traces"]]
    assert ids[0] == ids[1] == ["S", "R", "P", "Q"]


# The command line


def test_the_trace_command_writes_one_trace_per_scheduler(tmp_path, capsys):
    out = tmp_path / "trace.json"
    argv = ["trace", "--scenario", "60f-4x10-demand080-interfloor", "--scheduler", "nearest-car",
            "--scheduler", "lowest-cost", "--dwell-time", "1", "-o", str(out)]
    assert main(argv) == 0
    traces = json.loads(out.read_text())["traces"]
    assert [t["scheduler"] for t in traces] == ["nearest-car", "lowest-cost"]
    assert traces[0]["config"]["dwell_time"] == 1
    assert "Wrote" in capsys.readouterr().out


def test_the_trace_command_reads_a_request_file(tmp_path, capsys):
    out = tmp_path / "trace.json"
    assert main(["trace", "--requests", str(EXAMPLE), "--elevators", "2", "--max-wait", "off", "-o", str(out)]) == 0
    trace = json.loads(out.read_text())["traces"][0]
    assert (trace["config"]["floors"], trace["config"]["max_wait"], len(trace["passengers"])) == (51, None, 3)
    capsys.readouterr()


def test_the_trace_command_generates_passengers(tmp_path, capsys):
    out = tmp_path / "trace.json"
    argv = ["trace", "--floors", "10", "--elevators", "2", "--demand", "50", "--pattern", "down-peak",
            "--seed", "4", "--run-length", "50", "--max-wait", "30", "--scheduler", "zoned", "-o", str(out)]
    assert main(argv) == 0
    trace = json.loads(out.read_text())["traces"][0]
    assert (trace["scheduler"], trace["config"]["max_wait"]) == ("zoned", 30)
    capsys.readouterr()


def test_the_trace_command_refuses_bad_input(tmp_path, capsys):
    assert main(["trace", "--floors", "500", "-o", str(tmp_path / "t.json")]) == 2
    assert "floors" in capsys.readouterr().err
    assert main(["trace", "--scenario", "no-such", "-o", str(tmp_path / "t.json")]) == 2
    assert "no-such" in capsys.readouterr().err
