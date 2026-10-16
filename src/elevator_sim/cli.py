"""Command line: run a request file, or compare the named scenarios."""

from __future__ import annotations

import argparse
import sys

from .config import Config
from .scheduler import NAMES, SCHEDULERS, make_scheduler
from .files import read_requests, write_logs
from .models import Request
from .scenarios import compare, scenarios
from .simulation import Simulation
from .stats import format_summary, summarize

DEFAULT_FLOORS = 20
BAD_INPUT = 2


def build_parser() -> argparse.ArgumentParser:
    """The two subcommands, run and compare, with their options."""
    parser = argparse.ArgumentParser(prog="elevator-sim", description="Destination dispatch elevator simulation.")
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("run", help="run a request file and write the two logs")
    run.add_argument("requests", help="CSV file with header time,id,source,dest")
    run.add_argument("--floors", type=int, help=f"default: the highest floor in the file, or {DEFAULT_FLOORS}")
    run.add_argument("--elevators", type=int, default=Config.elevators)
    run.add_argument("--capacity", type=int, default=Config.capacity)
    run.add_argument("--dwell-time", type=int, default=Config.dwell_time)
    run.add_argument("--scheduler", choices=NAMES, default="lowest-cost")
    run.add_argument("--out", default="out", help="folder for positions.csv and events.csv")
    add_old_flag(run, "--cars", "elevators", type=int)
    add_old_flag(run, "--door-time", "dwell_time", type=int)
    add_old_flag(run, "--dispatcher", "scheduler", choices=NAMES)

    comparison = commands.add_parser("compare", help="print a table of scenarios under each scheduler")
    comparison.add_argument("--scenario", action="append", help="repeat to pick several; default: every scenario")
    comparison.add_argument("--scheduler", action="append", choices=NAMES, help="default: the 3 main schedulers")
    add_old_flag(comparison, "--dispatcher", "scheduler", action="append", choices=NAMES)
    return parser


def add_old_flag(parser: argparse.ArgumentParser, flag: str, dest: str, **options) -> None:
    """An earlier flag name, hidden from help, that sets the same value as its new name."""
    parser.add_argument(flag, dest=dest, default=argparse.SUPPRESS, help=argparse.SUPPRESS, **options)


def highest_floor(requests: list[Request]) -> int:
    """The highest floor named in the requests, or 0 when there are none."""
    highest = 0
    for r in requests:
        highest = max(highest, r.source, r.dest)
    return highest


def run_file(args: argparse.Namespace) -> int:
    """Read the request file, run it, write the logs and print the summary."""
    requests = read_requests(args.requests)
    floors = args.floors or max(highest_floor(requests), DEFAULT_FLOORS)
    config = Config(floors=floors, elevators=args.elevators, capacity=args.capacity, dwell_time=args.dwell_time)
    result = Simulation(config, make_scheduler(args.scheduler, config)).run(requests)
    positions_path, events_path = write_logs(result, args.out)
    if requests:
        print(format_summary(summarize(result)))
    else:
        print("no requests")
    print(f"Wrote {positions_path} and {events_path}")
    return 0


def run_compare(args: argparse.Namespace) -> int:
    """Print the comparison table for the chosen scenarios and schedulers."""
    names = args.scenario or list(scenarios())
    schedulers = args.scheduler or list(SCHEDULERS)
    print(compare(names, schedulers))
    return 0


def main(argv: list[str] | None = None) -> int:
    """Parse the arguments and run the chosen subcommand; bad input exits 2."""
    args = build_parser().parse_args(argv)
    try:
        if args.command == "run":
            return run_file(args)
        return run_compare(args)
    except (ValueError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return BAD_INPUT
