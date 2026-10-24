import pytest

from elevator_sim.app.files import events_csv, parse_requests, positions_csv, read_requests, write_logs
from elevator_sim.core.models import Event, Request, Result

SAMPLE = """time,id,source,dest
0,passenger1,1,51
0,passenger2,1,37
10,passenger3,20,1
"""


def sample_result() -> Result:
    positions = [[1, 1], [2, 1], [3, 2]]
    events = [
        Event(0, "p1", 0, 1, "assigned"),
        Event(0, "p1", 0, 1, "boarded"),
        Event(2, "p1", 1, 3, "arrived"),
    ]
    return Result(passengers=[], positions=positions, events=events)


def test_parse_spec_sample():
    assert parse_requests(SAMPLE) == [
        Request(0, "passenger1", 1, 51),
        Request(0, "passenger2", 1, 37),
        Request(10, "passenger3", 20, 1),
    ]


def test_parse_sorts_by_time_and_keeps_order_within_time():
    text = "time,id,source,dest\n5,a,1,3\n0,b,2,1\n5,c,4,2\n0,d,1,9\n"
    ids = [r.id for r in parse_requests(text)]
    assert ids == ["b", "d", "a", "c"]


def test_parse_skips_blank_lines_and_allows_header_whitespace():
    text = " time , id , source , dest \n\n0,a,1,2\n\n"
    assert parse_requests(text) == [Request(0, "a", 1, 2)]


@pytest.mark.parametrize("header", ["time,id,source", "id,time,source,dest", ""])
def test_parse_rejects_bad_header(header):
    with pytest.raises(ValueError):
        parse_requests(header + "\n0,a,1,2\n")


@pytest.mark.parametrize(
    "row",
    [
        "0,a,1",
        "0,a,1,2,3",
        "x,a,1,2",
        "0,a,one,2",
        "0,a,1,2.5",
        "-1,a,1,2",
        "0,a,3,3",
        "0,a,0,2",
        "0,a,2,0",
    ],
)
def test_parse_bad_row_names_the_line(row):
    text = "time,id,source,dest\n0,ok,1,2\n\n" + row + "\n"
    with pytest.raises(ValueError, match="line 4"):
        parse_requests(text)


def test_parse_rejects_duplicate_id():
    text = "time,id,source,dest\n0,a,1,2\n1,a,2,3\n"
    with pytest.raises(ValueError, match="line 3"):
        parse_requests(text)


def test_read_requests(tmp_path):
    path = tmp_path / "requests.csv"
    path.write_text(SAMPLE)
    assert len(read_requests(path)) == 3


def test_positions_csv():
    assert positions_csv(sample_result()) == "time,elevator1,elevator2\n0,1,1\n1,2,1\n2,3,2\n"


def test_events_csv_numbers_elevators_from_one_and_keeps_order():
    expected = (
        "time,passenger,elevator,floor,event\n"
        "0,p1,1,1,assigned\n"
        "0,p1,1,1,boarded\n"
        "2,p1,2,3,arrived\n"
    )
    assert events_csv(sample_result()) == expected


def test_write_logs_creates_dir_and_files(tmp_path):
    out = tmp_path / "out" / "logs"
    positions_path, events_path = write_logs(sample_result(), out)
    assert positions_path == out / "positions.csv"
    assert events_path == out / "events.csv"
    assert positions_path.read_bytes() == positions_csv(sample_result()).encode()
    assert events_path.read_bytes() == events_csv(sample_result()).encode()
