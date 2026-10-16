from pathlib import Path

import pytest

from elevator_sim.cli import main

EXAMPLE = Path(__file__).parent.parent / "examples" / "requests.csv"


def header(path):
    return path.read_text().splitlines()[0]


def test_run_writes_both_logs_and_prints_the_summary(tmp_path, capsys):
    code = main(["run", str(EXAMPLE), "--elevators", "2", "--out", str(tmp_path)])
    out = capsys.readouterr().out
    assert code == 0
    assert header(tmp_path / "positions.csv") == "time,elevator1,elevator2"
    assert header(tmp_path / "events.csv") == "time,passenger,elevator,floor,event"
    assert "Passengers: 3    Time units: 51" in out
    assert "Wait" in out and "Total" in out


def test_run_defaults_floors_to_the_highest_floor_in_the_input(tmp_path, capsys):
    main(["run", str(EXAMPLE), "--elevators", "1", "--out", str(tmp_path)])
    capsys.readouterr()
    rows = (tmp_path / "positions.csv").read_text().splitlines()
    assert max(int(row.split(",")[1]) for row in rows[1:]) == 51


def test_run_takes_every_setting(tmp_path, capsys):
    argv = [
        "run", str(EXAMPLE), "--floors", "60", "--elevators", "3", "--capacity", "1",
        "--dwell-time", "1", "--scheduler", "round-robin", "--out", str(tmp_path),
    ]
    assert main(argv) == 0
    capsys.readouterr()
    assert header(tmp_path / "positions.csv") == "time,elevator1,elevator2,elevator3"


def test_the_old_flags_still_run(tmp_path, capsys):
    argv = [
        "run", str(EXAMPLE), "--floors", "60", "--cars", "3", "--capacity", "1",
        "--door-time", "1", "--dispatcher", "round-robin", "--out", str(tmp_path),
    ]
    assert main(argv) == 0
    capsys.readouterr()
    assert header(tmp_path / "positions.csv") == "time,elevator1,elevator2,elevator3"
    main(["compare", "--scenario", "5f-4x10-demand080-interfloor", "--dispatcher", "lowest-cost"])
    rows = [line for line in capsys.readouterr().out.splitlines() if line.startswith("| 5f")]
    assert len(rows) == 1


def test_the_old_flags_are_hidden_from_help(capsys):
    for command in ("run", "compare"):
        with pytest.raises(SystemExit):
            main([command, "--help"])
        text = capsys.readouterr().out
        for old in ("--cars", "--door-time", "--dispatcher"):
            assert old not in text


def test_a_bad_file_exits_2_and_names_the_line(tmp_path, capsys):
    bad = tmp_path / "bad.csv"
    bad.write_text("time,id,source,dest\n0,a,1,5\n1,b,3,x\n")
    code = main(["run", str(bad), "--out", str(tmp_path / "out")])
    err = capsys.readouterr().err
    assert code == 2
    assert "line 3" in err


def test_a_floor_above_the_building_exits_2(tmp_path, capsys):
    code = main(["run", str(EXAMPLE), "--floors", "40", "--out", str(tmp_path)])
    assert code == 2
    assert "floor 51" in capsys.readouterr().err


def test_an_empty_request_file_prints_no_requests_and_writes_the_logs(tmp_path, capsys):
    empty = tmp_path / "empty.csv"
    empty.write_text("time,id,source,dest\n")
    code = main(["run", str(empty), "--elevators", "2", "--out", str(tmp_path / "out")])
    assert code == 0
    assert "no requests" in capsys.readouterr().out
    assert (tmp_path / "out" / "positions.csv").read_text() == "time,elevator1,elevator2\n0,1,1\n"
    assert header(tmp_path / "out" / "events.csv") == "time,passenger,elevator,floor,event"


def test_compare_prints_one_row_per_scheduler(capsys):
    code = main(["compare", "--scenario", "5f-4x10-demand080-interfloor"])
    lines = capsys.readouterr().out.splitlines()
    assert code == 0
    rows = [line for line in lines if line.startswith("| 5f-4x10-demand080-interfloor |")]
    assert [row.split(" | ")[1] for row in rows] == ["round-robin", "nearest-car", "lowest-cost"]


def test_compare_takes_chosen_schedulers(capsys):
    main(["compare", "--scenario", "5f-4x10-demand080-interfloor", "--scheduler", "lowest-cost-nocap"])
    rows = [line for line in capsys.readouterr().out.splitlines() if line.startswith("| 5f")]
    assert len(rows) == 1
    assert "lowest-cost-nocap" in rows[0]


def test_compare_with_an_unknown_scenario_exits_2(capsys):
    assert main(["compare", "--scenario", "no-such"]) == 2
    assert "no-such" in capsys.readouterr().err


def test_an_unknown_scheduler_is_refused(tmp_path, capsys):
    with pytest.raises(SystemExit) as stop:
        main(["run", str(EXAMPLE), "--scheduler", "fastest", "--out", str(tmp_path)])
    assert stop.value.code == 2
