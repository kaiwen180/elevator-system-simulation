"""Read requests.csv and write positions.csv and events.csv."""

from __future__ import annotations

import csv
import io
from pathlib import Path

from elevator_sim.models import Request, Result

REQUEST_HEADER = ["time", "id", "source", "dest"]
EVENT_HEADER = ["time", "passenger", "elevator", "floor", "event"]


def parse_requests(text: str) -> list[Request]:
    """Parse requests.csv text into requests sorted by time."""
    reader = csv.reader(io.StringIO(text))
    check_header(next(reader, []))
    requests = []
    seen_ids = set()
    for row in reader:
        if not row:
            continue
        request = parse_row(row, reader.line_num)
        if request.id in seen_ids:
            raise ValueError(f"line {reader.line_num}: duplicate id {request.id!r}")
        seen_ids.add(request.id)
        requests.append(request)
    return sorted(requests, key=lambda r: r.time)


def check_header(header: list[str]) -> None:
    """Raise unless the header is exactly time,id,source,dest."""
    names = [name.strip() for name in header]
    if names != REQUEST_HEADER:
        raise ValueError(f"line 1: header must be {','.join(REQUEST_HEADER)}")


def parse_row(row: list[str], line: int) -> Request:
    """Turn one CSV row into a Request, or raise ValueError naming the line."""
    if len(row) != 4:
        raise ValueError(f"line {line}: expected 4 columns, got {len(row)}")
    time = parse_int(row[0], "time", line)
    request_id = row[1].strip()
    source = parse_int(row[2], "source", line)
    dest = parse_int(row[3], "dest", line)
    if time < 0:
        raise ValueError(f"line {line}: time must not be negative")
    if source < 1 or dest < 1:
        raise ValueError(f"line {line}: floors start at 1")
    if source == dest:
        raise ValueError(f"line {line}: source equals dest")
    return Request(time, request_id, source, dest)


def parse_int(value: str, column: str, line: int) -> int:
    """Read one integer column, or raise ValueError naming the line."""
    try:
        return int(value.strip())
    except ValueError:
        raise ValueError(f"line {line}: {column} must be an integer, got {value!r}") from None


def read_requests(path: str | Path) -> list[Request]:
    """Read and parse a requests.csv file."""
    return parse_requests(Path(path).read_text())


def to_csv(rows: list[list]) -> str:
    """Join rows into CSV text with plain newline line endings."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerows(rows)
    return buffer.getvalue()


def positions_csv(result: Result) -> str:
    """One row per time unit: the time, then each elevator's floor."""
    elevator_count = len(result.positions[0]) if result.positions else 0
    header = ["time"] + [f"elevator{n}" for n in range(1, elevator_count + 1)]
    rows = [header]
    for t, floors in enumerate(result.positions):
        rows.append([t] + floors)
    return to_csv(rows)


def events_csv(result: Result) -> str:
    """One row per event, in the order it happened, elevators numbered from 1."""
    rows = [EVENT_HEADER]
    for event in result.events:
        rows.append([event.time, event.passenger, event.elevator + 1, event.floor, event.kind])
    return to_csv(rows)


def write_logs(result: Result, out_dir: str | Path) -> tuple[Path, Path]:
    """Write positions.csv and events.csv into out_dir and return their paths."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    positions_path = out / "positions.csv"
    events_path = out / "events.csv"
    positions_path.write_text(positions_csv(result), newline="\n")
    events_path.write_text(events_csv(result), newline="\n")
    return positions_path, events_path
