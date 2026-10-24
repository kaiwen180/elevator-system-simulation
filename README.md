# Elevator system simulation

A simulation of destination dispatch: each passenger enters a destination floor before boarding, the system assigns an elevator at once, and the assignment is final. Time moves in whole time units, one floor of travel each, and the simulation never reads a request made later than now. Three schedulers are compared on total time per passenger (wait time plus travel time).

## How to run

Requires Python 3.12 or later and [uv](https://docs.astral.sh/uv/).

```
uv sync
uv run elevator-sim run examples/requests.csv --elevators 2 --out out
uv run elevator-sim compare
uv run pytest
```

`run` reads a request file (`time,id,source,dest`), writes the two logs to `--out`, and prints the statistics. Options: `--floors`, `--elevators` (default 4), `--capacity` (default 10), `--dwell-time` (default 0) and `--scheduler` (`round-robin`, `nearest-car` or `lowest-cost`, the default). `compare` runs 19 named scenarios under each scheduler.

The spec's sample on 2 elevators prints:

```
Passengers: 3    Time units: 51
           min   mean   p50   p95   max
Wait         0    6.3     0    19    19
Travel      19   35.0    36    50    50
Total       36   41.3    38    50    50
Served per elevator: elevator1 2, elevator2 1
```

**Live page:** `uv run elevator-sim serve`, then open `http://127.0.0.1:8080/`. Click a preset to run it, then step through each assignment. C shows the code behind each step.

## How it works

Each time unit: reveal the requests made now, assign each to an elevator, log every elevator's floor, then move each elevator one floor. An elevator serves stops in floor order in its direction and reverses only when no stop is left ahead (collective control).

- **Round robin:** elevators take turns.
- **Nearest car:** the fewest floors to reach the passenger, moving their way.
- **Lowest cost:** runs a copy of each elevator forward, with and without the new passenger, and picks the one that adds the least total time. A wait past 3 trips of the shaft costs 1000 per time unit.

The algorithm is in `src/elevator_sim/core/` and imports nothing outside it. `docs/design.md` has the full model.

## Results

20 floors, 4 elevators of 10, about 340 passengers, mean total time per passenger:

| traffic | round robin | nearest car | lowest cost |
|---|---|---|---|
| up-peak (from the lobby) | 28.0 | 33.6 | 22.3 |
| interfloor (random floors) | 22.9 | 13.7 | 12.4 |

At up-peak, lowest cost takes 34% less time than nearest car, and its longest wait is 26 against 109. With one elevator, all three tie. `docs/results.md` has the full tables and the three optional extensions: a zoned scheduler, express elevators, and a fairness against efficiency study.

## Assumptions

- Wait time ends at boarding; travel time runs from boarding to arrival.
- Stops cost no time by default (`--dwell-time` changes it).
- All elevators start at floor 1, the lobby.
- An elevator reverses only when no stop is left ahead.
- A full elevator can still be assigned; lowest cost prices the crowding.

## Simplifications and trade-offs

- Time units, not seconds: no acceleration or door model beyond the dwell time.
- Assignment is greedy and final; earlier assignments are never revisited.
- No forecasting, because the spec forbids reading later requests.
- One seed per scenario, so each result is one sample.
- Lowest cost is the slowest scheduler: two trial runs per elevator per passenger.

## What I would improve

- Run each scenario on many seeds and report the spread.
- Use real seconds, with acceleration and door times.
- Price waiting on a rising curve instead of a step penalty.
- Add energy (floors traveled, starts and stops) as a cost.

## Time spent

About 3 hours: design and test plan 1 hour, test-first build 1.5 hours, renaming to the spec's terms 0.5 hours.
