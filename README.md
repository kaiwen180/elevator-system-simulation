# Elevator system simulation

A simulation of destination dispatch for a bank of elevators. Each passenger enters a destination floor before boarding, the system assigns an elevator at once, and the assignment is final. Time moves in whole time units, one floor of travel each, and the simulation never looks at a request made later than now. Four schedulers are compared on total time per passenger (wait time plus travel time), across 19 named scenarios that stretch the building height, the elevator bank and the demand. The spec's three optional extensions live in `src/elevator_sim/extensions/`.

## How to run

Requires Python 3.12 or later and [uv](https://docs.astral.sh/uv/).

```
uv sync
uv run elevator-sim run examples/requests.csv --elevators 2 --out out
uv run elevator-sim compare
uv run elevator-sim fairness
uv run pytest
uv run pytest -m "not slow"
```

`run` reads a request file (`time,id,source,dest`), writes `positions.csv` and `events.csv` to the `--out` folder, and prints a summary. `compare` runs the named scenarios under each scheduler and prints a Markdown table. `fairness` prints the fairness study below. `compare` takes `--scenario` and `--scheduler` and `fairness` takes `--scenario`, each repeatable. `pytest -m "not slow"` skips the long-horizon runs.

| `run` option | Default | Meaning |
|---|---|---|
| `--floors` | highest floor in the file, at least 20 | floors in the building |
| `--elevators` | 4 | elevators in the bank |
| `--capacity` | 10 | passengers per elevator |
| `--dwell-time` | 0 | time units an elevator holds at a stop |
| `--scheduler` | `lowest-cost` | `round-robin`, `nearest-car`, `lowest-cost`, `lowest-cost-nocap` or `zoned` |
| `--out` | `out` | folder for the two logs |

The spec's sample (2 elevators, 60 floors) prints:

```
Passengers: 3    Time units: 51
           min   mean   p50   p95   max
Wait         0    6.3     0    19    19
Travel      19   35.0    36    50    50
Total       36   41.3    38    50    50
Served per elevator: elevator1 2, elevator2 1
```

## Live UI

An interactive page, driven by the same engine, for showing each scheduler at work. Each assignment shows every elevator's score and the winner.

```
uv run elevator-sim serve --port 8080
uv run elevator-sim trace --scenario 20f-4x10-demand100-up-peak --scheduler nearest-car --scheduler lowest-cost -o trace.json
```

`serve` listens on 127.0.0.1 only: open `http://127.0.0.1:8080/`, pick a preset or set the sliders, choose up to 3 schedulers, and press Run. `trace` writes the same JSON the server returns; open `src/elevator_sim/ui/index.html` as a file and load or paste it. Screenshots: `docs/screenshots/rush-hour-assignment.png`, `docs/screenshots/rush-hour-results.png`, `docs/screenshots/two-elevators-q.png`.

## How it works

At each time unit `t`:

1. **Reveal** the requests made at `t`, in input order.
2. **Assign** each one: the scheduler picks among the elevators that serve the trip, and the passenger joins its waiting list.
3. **Log** each elevator's floor as row `t` of the positions log.
4. **Step** each elevator: let off passengers, choose a direction, board waiting passengers going that way until full, dwell if anyone left or boarded, then move one floor.

**Collective control** (LOOK, in disk scheduling) chooses the direction. A moving elevator keeps going while a stop lies ahead, and reverses only when none is left. An idle elevator serves a passenger at its floor first, else heads to the nearest stop. The schedulers:

- **round-robin:** elevators in turn.
- **nearest-car:** the fewest floors to reach the passenger while moving their way.
- **lowest-cost:** for each elevator, a trial allocation runs a copy forward with and without the new passenger; the elevator that adds the least total time wins. Each time unit of wait past the maximum wait time (3 trips of the shaft, 57 in 20 floors) costs 1000.
- **zoned:** each elevator owns a band of floors above the lobby, and lowest cost picks inside the band.

## Assumptions and design decisions

The spec leaves these open, and each one changes the numbers.

| Question | Decision |
|---|---|
| When does wait time end? | At boarding. Travel time runs from boarding to arrival. |
| Do stops cost time? | Dwell time per stop, in time units, defaults to 0; `--dwell-time` changes it. |
| Where do elevators start? | All at floor 1. |
| Which floor is the lobby? | Floor 1. Up-peak and down-peak traffic run to and from it. |
| When can an elevator reverse? | Only when no stop is left ahead, so no passenger inside rides away from their destination. |
| What if an elevator will be full? | It stays assignable. The trial allocation prices the crowding, so lowest cost avoids it unless every elevator is crowded. |
| What does a run log? | `positions.csv`: each elevator's floor per time unit. `events.csv`: every assignment, boarding and arrival. |

## Simplifications and trade-offs

- No acceleration or door model beyond the dwell time.
- The destination is entered at the origin floor and is final.
- Assignment is greedy, one passenger at a time; earlier assignments are never revisited.
- No forecasting: the spec forbids looking at later requests.
- One seed per scenario, so each result is one sample, not a spread.
- Time units, not seconds.
- Lowest cost is slower than the others: two trial allocations per elevator per passenger.

## Optional extensions

### Zone-based scheduler

File `src/elevator_sim/extensions/zoning.py`, scheduler `zoned`. The floors above the lobby split into equal bands, one per elevator; with fewer floors above the lobby than elevators, each floor is a band and equal groups of elevators share it. A passenger's band comes from their non-lobby floor: the destination for trips up from the lobby, the origin for trips down to it, the destination for interfloor trips. Command: `uv run elevator-sim compare --scenario 20f-4x10-demand100-interfloor --scenario 20f-4x10-demand100-up-peak --scheduler lowest-cost --scheduler zoned`.

| scenario | scheduler | mean wait | max wait | mean total |
|---|---|---|---|---|
| 20f-4x10-demand100-interfloor | lowest-cost | 5.6 | 28 | 12.4 |
| 20f-4x10-demand100-interfloor | zoned | 16.0 | 37 | 22.9 |
| 20f-4x10-demand100-up-peak | lowest-cost | 12.4 | 26 | 22.3 |
| 20f-4x10-demand100-up-peak | zoned | 17.1 | 188 | 27.0 |

Zoning loses here: with 4 bands and 4 elevators, each passenger has exactly 1 elevator to choose from, so lowest cost inside the band has no choice left to make.

### Express elevators

File `src/elevator_sim/extensions/express.py`. `Config.served_floors` holds one set of floors per elevator (default: every floor). A passenger is offered only the elevators that serve both their origin and destination floors, through one filter (`simulation.eligible`) that every scheduler shares; if none does, the run raises `ValueError` naming the passenger. Invariant 10 checks that no elevator boards or lets off anyone at a floor it does not serve. `express_bank(40, local=2, express=2, split=20)` gives 2 local elevators for floors 1 to 20 and 2 express elevators for floor 1 and floors 21 to 40. Both scenarios drop the trips the express layout cannot carry (7 of 159, between floors 2 to 20 and 21 to 40), so they share their 152 passengers. Command: `uv run elevator-sim compare --scenario 40f-4x10-demand100-up-peak-all-floors --scenario 40f-4x10-demand100-up-peak-express`.

| layout | scheduler | mean wait | max wait | mean total | time units |
|---|---|---|---|---|---|
| all floors | round-robin | 36.7 | 75 | 56.7 | 379 |
| all floors | nearest-car | 45.2 | 183 | 65.2 | 496 |
| all floors | lowest-cost | 22.5 | 47 | 42.5 | 359 |
| express | round-robin | 30.8 | 91 | 50.8 | 390 |
| express | nearest-car | 24.7 | 100 | 44.7 | 355 |
| express | lowest-cost | 21.3 | 73 | 41.3 | 393 |

Express helps the simple schedulers most (nearest car's mean total drops from 65.2 to 44.7). Lowest cost gains 1.2 on the mean but its longest wait grows from 47 to 73, because each passenger can choose between 2 elevators, not 4.

### Fairness against efficiency

File `src/elevator_sim/extensions/fairness.py`, command `uv run elevator-sim fairness`. It runs lowest cost with each maximum wait time and dwell time. Mean total time measures efficiency; p95 wait and longest wait measure fairness. At dwell time 0 the maximum wait time binds only at 20 in interfloor (longest wait 28 to 25, mean total 12.4 to 13.8), so the rows below are at dwell time 3.

| scenario | maximum wait time | mean total | p95 wait | longest wait |
|---|---|---|---|---|
| 20f-4x10-demand100-interfloor | none | 43.3 | 62 | 122 |
| 20f-4x10-demand100-interfloor | 57 | 53.2 | 68 | 108 |
| 20f-4x10-demand100-interfloor | 40 | 49.4 | 66 | 92 |
| 20f-4x10-demand100-interfloor | 30 | 48.4 | 68 | 109 |
| 20f-4x10-demand100-interfloor | 20 | 50.4 | 67 | 117 |
| 20f-4x10-demand100-up-peak | none | 101.0 | 157 | 173 |
| 20f-4x10-demand100-up-peak | 57 | 104.8 | 167 | 176 |
| 20f-4x10-demand100-up-peak | 40 | 108.8 | 171 | 181 |
| 20f-4x10-demand100-up-peak | 30 | 108.4 | 174 | 181 |
| 20f-4x10-demand100-up-peak | 20 | 112.0 | 177 | 188 |

In interfloor traffic the default maximum (57) cuts the longest wait from 122 to 108 for 9.9 more on the mean total, and 40 does best (92); at 30 and 20 the longest wait grows again. In the up-peak the median wait with no maximum is 78, above every maximum tried, so the penalty fires for most passengers and only costs time.

## Results

| scenario | scheduler | passengers | mean wait | max wait | mean total | max total |
|---|---|---|---|---|---|---|
| 20f-4x10-demand100-interfloor | round-robin | 335 | 16.0 | 36 | 22.9 | 54 |
| 20f-4x10-demand100-interfloor | nearest-car | 335 | 6.8 | 34 | 13.7 | 51 |
| 20f-4x10-demand100-interfloor | lowest-cost | 335 | 5.6 | 28 | 12.4 | 38 |
| 20f-4x10-demand100-up-peak | round-robin | 338 | 18.1 | 81 | 28.0 | 95 |
| 20f-4x10-demand100-up-peak | nearest-car | 338 | 23.8 | 109 | 33.6 | 125 |
| 20f-4x10-demand100-up-peak | lowest-cost | 338 | 12.4 | 26 | 22.3 | 45 |
| 20f-1x1-demand080-interfloor | all three | 20 | 7.5 | 32 | 13.9 | 39 |
| 160f-4x10-demand080-interfloor | round-robin | 26 | 102.1 | 292 | 158.4 | 330 |
| 160f-4x10-demand080-interfloor | nearest-car | 26 | 85.6 | 303 | 141.8 | 305 |
| 160f-4x10-demand080-interfloor | lowest-cost | 26 | 55.1 | 129 | 111.4 | 262 |

Dwell time is 0. With one elevator every scheduler makes the same choice, so the rows match. `uv run elevator-sim compare` prints the full table, 57 rows (19 scenarios, 3 schedulers); add `--scheduler zoned` for a fourth.

## What I would improve with more time

- Run each scenario on many seeds and report the spread, not one sample.
- Use real seconds, with acceleration and door open and close times.
- Price waiting on a rising curve instead of a step penalty at the maximum wait time.
- Cache the trial allocation without the new passenger, which every elevator recomputes per request.
- Add energy (floors traveled, starts and stops) as a cost term.

## Time spent

About 3 hours: design and test plan about 1 hour, test-first build about 1.5 hours, renaming to the spec's terms about 0.5 hours.

## Module map

| File | What it holds |
|---|---|
| `src/elevator_sim/models.py` | Data only: requests, passengers, elevators, events, the result of a run |
| `src/elevator_sim/config.py` | Building and elevator bank settings, including the served floors, checked on creation |
| `src/elevator_sim/direction.py` | Collective control, boarding, unloading and dwell time for one elevator |
| `src/elevator_sim/scheduler.py` | Round robin, nearest car, lowest cost, and `make_scheduler` by name |
| `src/elevator_sim/simulation.py` | The clock, and the served-floor filter every scheduler shares |
| `src/elevator_sim/traffic.py` | Synthetic passengers: patterns, demand levels, daily profiles |
| `src/elevator_sim/files.py` | Read the request file, write the two logs |
| `src/elevator_sim/stats.py` | Summary numbers for a finished run |
| `src/elevator_sim/invariants.py` | The 10 rules every run must obey |
| `src/elevator_sim/scenarios.py` | The named scenarios and the comparison table |
| `src/elevator_sim/cli.py` | The `run`, `compare`, `fairness`, `trace` and `serve` commands |
| `src/elevator_sim/trace.py` | Runs as JSON for the live page: time units, each assignment's scores, summary metrics, parameter checks |
| `src/elevator_sim/server.py` | The live page's server on 127.0.0.1: `GET /`, `GET /api/scenarios`, `POST /api/run` |
| `src/elevator_sim/ui/index.html` | The live page, self-contained |
| `src/elevator_sim/extensions/zoning.py` | The zoned scheduler and its band split |
| `src/elevator_sim/extensions/express.py` | Express layouts: `express_bank` and `servable` |
| `src/elevator_sim/extensions/fairness.py` | The fairness against efficiency study and its table |
| `tests/` | One test file per module; `tests/extensions/` holds one per extension |
| `docs/design.md` | The model, step by step |
| `docs/test-plan.md` | The test layers, the scenarios and the rules every run must pass |
