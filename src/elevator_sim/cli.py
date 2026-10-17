"""Command line: run a request file, compare scenarios, print the fairness study, write a trace, or serve the live page."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import Config
from .extensions.fairness import DEFAULT_SCENARIOS, fairness_study, fairness_table
from .scheduler import NAMES, SCHEDULERS, make_scheduler
from .files import read_requests, write_logs
from .models import Request
from .scenarios import compare, scenarios
from .simulation import Simulation
from .stats import format_summary, summarize
from .trace import LAYOUTS, trace_runs
from .traffic import PATTERNS

DEFAULT_FLOORS = 20
BAD_INPUT = 2


def build_parser() -> argparse.ArgumentParser:
    """The three subcommands, run, compare and fairness, with their options."""
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

    fairness = commands.add_parser("fairness", help="print the fairness against efficiency study for lowest cost")
    fairness.add_argument("--scenario", action="append", help="repeat to pick several; default: 100%% interfloor and up-peak")

    trace = commands.add_parser("trace", help="write a trace JSON file for the live page")
    source = trace.add_mutually_exclusive_group()
    source.add_argument("--scenario", help="a named scenario; default: generate passengers")
    source.add_argument("--requests", help="CSV file with header time,id,source,dest")
    trace.add_argument("--scheduler", action="append", choices=NAMES, help="repeat to compare up to 3; default: lowest-cost")
    for flag in ("--floors", "--elevators", "--capacity", "--dwell-time", "--seed", "--run-length"):
        trace.add_argument(flag, type=int)
    trace.add_argument("--demand", type=float, help="percent of handling capacity, default 100")
    trace.add_argument("--pattern", choices=PATTERNS)
    trace.add_argument("--layout", choices=LAYOUTS)
    trace.add_argument("--max-wait", help="default, off, or time units")
    trace.add_argument("-o", "--out", default="trace.json", help="the trace file to write")

    serve = commands.add_parser("serve", help="serve the live page and run simulations on demand, on 127.0.0.1")
    serve.add_argument("--port", type=int, default=8080)
    serve.add_argument("--log-requests", action="store_true", help="log method, route and status; also needs ELEVATOR_SIM_LOG=local")
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


def run_fairness(args: argparse.Namespace) -> int:
    """Print the fairness study for the chosen scenarios."""
    print(fairness_table(fairness_study(args.scenario or list(DEFAULT_SCENARIOS))))
    return 0


def max_wait_value(text: str | None):
    """The --max-wait text as default, off or a whole number."""
    if text is None or text in ("default", "off"):
        return text or "default"
    try:
        return int(text)
    except ValueError:
        raise ValueError(f"max_wait must be default, off or a whole number, got {text!r}") from None


def trace_params(args: argparse.Namespace) -> dict:
    """The trace options as the same parameters the server takes."""
    params = {"max_wait": max_wait_value(args.max_wait), "schedulers": args.scheduler or ["lowest-cost"]}
    if args.scenario:
        params["scenario"] = args.scenario
    if args.requests:
        params["requests"] = Path(args.requests).read_text()
    for key in ("floors", "elevators", "capacity", "dwell_time", "seed", "run_length", "pattern", "layout"):
        if getattr(args, key) is not None:
            params[key] = getattr(args, key)
    if args.demand is not None:
        params["demand"] = int(args.demand) if args.demand.is_integer() else args.demand
    return params


def run_trace(args: argparse.Namespace) -> int:
    """Write the trace file for the chosen passengers and schedulers."""
    out = Path(args.out)
    traces = trace_runs(trace_params(args))
    out.write_text(json.dumps(traces, separators=(",", ":"), allow_nan=False))
    names = ", ".join(t["scheduler"] for t in traces["traces"])
    print(f"Wrote {out}: {len(traces['traces'][0]['passengers'])} passengers, {names}")
    return 0


def run_serve(args: argparse.Namespace) -> int:
    """Serve the live page on 127.0.0.1 until interrupted."""
    from .server import serve
    serve(args.port, args.log_requests)
    return 0


def main(argv: list[str] | None = None) -> int:
    """Parse the arguments and run the chosen subcommand; bad input exits 2."""
    args = build_parser().parse_args(argv)
    try:
        if args.command == "run":
            return run_file(args)
        if args.command == "fairness":
            return run_fairness(args)
        if args.command == "trace":
            return run_trace(args)
        if args.command == "serve":
            return run_serve(args)
        return run_compare(args)
    except (ValueError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return BAD_INPUT
