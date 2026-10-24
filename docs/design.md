# Design

This file is the contract every module follows. If code and this file disagree, one of them is a bug.

## Modules: one idea each

Four folders under `src/elevator_sim/`. `core/` is the algorithm and imports nothing outside itself; read it in the order of the table.

| Module | The one idea it holds |
|---|---|
| `core/models.py` | Data only: `Request`, `Passenger`, `Elevator`, `Event`, `Result`, `Direction` |
| `core/config.py` | Building and elevator bank settings, including the floors each elevator serves, checked on creation |
| `core/simulation.py` | The clock: reveal requests, offer each the elevators that serve its trip, assign, log positions, move elevators |
| `core/direction.py` | Direction logic for one elevator: collective control, boarding, dwell time |
| `core/scheduler.py` | The scheduler picks the elevator for a new passenger: round robin, nearest car, lowest cost |
| `benchmark/schedulers.py` | Schedulers by name: `make_scheduler`, `SCHEDULERS`, `NAMES` |
| `benchmark/traffic.py` | Synthetic passengers: traffic patterns, demand levels, daily profiles |
| `benchmark/stats.py` | Summary numbers for a finished run |
| `benchmark/invariants.py` | Checks that a finished run obeyed every rule |
| `benchmark/scenarios.py` | The named extreme scenarios and the comparison report |
| `extensions/zoning.py` | The zoned scheduler: bands of floors above the lobby, lowest cost inside a band |
| `extensions/express.py` | Express layouts for `Config.served_floors`: `express_bank` and `servable` |
| `extensions/fairness.py` | The fairness against efficiency study for lowest cost |
| `app/files.py` | Read the request file, write the two log files |
| `app/cli.py` | The command line: `run`, `compare`, `fairness`, `trace`, `serve` |
| `app/trace.py` | A run as JSON for the live page, and the parameter checks the command line and the server share |
| `app/server.py` | The live page's server: standard library only, bound to 127.0.0.1 |
| `app/code_view.py` | The core functions the live page's Code panel shows, and the line groups each moment lights |
| `app/narration.py` | Spoken clips for the live page, passed through from a Kokoro server on this machine |
| `app/ui/index.html` | The live page |

Dependencies point one way: `core` at the bottom, `benchmark` and `extensions` above it, `app` on top. Inside `core`, `models` and `config` sit at the bottom, `direction` above them, and `scheduler` and `simulation` above that. `zoning` builds on `core/scheduler` and is built by name in `benchmark/schedulers`; `express` sits below `scenarios`, and `fairness` between `scenarios` and `app/cli`.

## One time unit

Time moves in whole time units. One time unit is the time an elevator takes to travel one floor. At time `t`:

1. **Reveal.** Requests with `time == t` become visible, in input order. Nothing later is visible.
2. **Assign.** For each revealed request, the scheduler picks among the elevators that serve both its origin and destination floors (`simulation.eligible`; every elevator, unless `Config.served_floors` says otherwise). If none does, the run raises `ValueError` naming the passenger. The passenger joins that elevator's `waiting` list. Event `assigned` at `t`.
3. **Log.** Row `t` of the elevator positions log records each elevator's floor at time `t`.
4. **Step.** Each elevator, in index order, runs `direction.step(elevator, t, config)`:
   1. **Unload** passengers in the elevator whose destination floor is this floor. Event `arrived` at `t`.
   2. **Choose direction** by collective control, below.
   3. **Board** waiting passengers at this floor whose direction matches the elevator's, in assignment order, until the elevator is full. Event `boarded` at `t`.
   4. **Choose direction** again, because boarding can wake an idle elevator.
   5. **Dwell.** If anyone left or boarded, and the elevator has not dwelled on this visit, it holds for `dwell_time` time units. While it holds, steps 1 to 4 still run each time unit, so a late passenger can board, but the hold does not restart.
   6. **Move.** If the elevator is not holding, `floor += direction`. The new floor shows in row `t + 1`. Moving ends the visit, and so does parking: an idle elevator with no hold left dwells again for its next passenger.
5. **Stop** after the time unit in which every request is revealed and every elevator has no passengers in it and no waiting passengers.

With `dwell_time = 0`, an elevator boards and leaves in the same time unit.

**Times.** wait time = boarded - requested. travel time = arrived - boarded. total time = arrived - requested. A passenger who asks at the floor where an idle elevator stands boards at once, with wait time 0.

## Collective control (`choose_direction`)

Collective control is the direction logic. Computer science calls the same rule LOOK, from disk scheduling. Stops (`Elevator.stops()`) are the destination floors of passengers in the elevator (`inside`) plus the origin floors of waiting passengers (`waiting`).

- **Moving elevator:** keep the direction if a stop lies strictly ahead, or a passenger waiting here wants this direction. Otherwise reverse if any stop exists. Otherwise go idle.
- **Idle elevator:** if passengers wait here, take the direction of the earliest-assigned one. Otherwise head toward the nearest stop, with ties going to the earliest-assigned passenger. Otherwise stay idle.
- An elevator with passengers in it never reverses, because every one of their destination floors lies ahead.
- An idle elevator with no stops stays where it is.

## Schedulers

Interface (`Scheduler`): `assign(passenger, elevators, now) -> elevator index`. A scheduler must not change any elevator. Ties go to the lowest index.

- **round-robin:** elevators in turn: 0, 1, 2, and so on.
- **nearest-car:** the fewest floors the elevator must travel to reach the passenger's origin floor while moving in the passenger's direction. It follows the elevator's current direction to its farthest stop, and ignores the time spent at stops. Elevator at floor `f`, passenger at `s` going `pd`, `top = max(f, s, stops)`, `bot = min(f, s, stops)`:
  - idle: `|f - s|`
  - moving up: `s - f` if `pd` is up and `s >= f`; `(top - f) + (top - s)` if `pd` is down; else `(top - f) + (top - bot) + (s - bot)`
  - moving down: the mirror image.
- **lowest-cost:** a trial allocation on each elevator, twice, with and without the new passenger, using `direction.run_until_idle` on copies. The trial allocation uses the same code that moves the real elevator. Its cost (`trial_cost`) is the sum, over every passenger on that elevator, of total time plus `penalty * max(0, wait - max_wait)`. The elevator with the smallest `incremental_cost` (with minus without) wins. Defaults: `max_wait = 3 * (floors - 1)` (`Config.default_max_wait`), which is 57 for 20 floors, and `penalty = 1000` per time unit past the maximum wait time. `max_wait = None` turns the maximum wait time off.
- **zoned** (`extensions/zoning.py`): the floors above the lobby split into equal bands, one per elevator; with fewer floors above the lobby than elevators, each floor is a band and equal groups of elevators share one. A passenger's band holds their non-lobby floor: the destination for trips up from the lobby, the origin for trips down to it, the destination for interfloor trips. Among the offered elevators of that band, the lowest `incremental_cost` wins; if the served-floor filter left none of them, lowest cost picks among all offered.

## Express elevators

`Config.served_floors` holds one set of floors per elevator; `None`, the default, means every floor. An elevator never boards or lets off anyone at a floor outside its set, because it is only offered passengers whose origin and destination floors it serves. It may still pass those floors. `express_bank(floors, local, express, split)` builds the usual layout: local elevators serve 1 to `split`, express elevators serve 1 and `split + 1` to `floors`.

## Demand

**100% demand** is the elevator bank's handling capacity (`Config.handling_capacity`): `elevators * capacity / (2 * (floors - 1))` passengers per time unit. It is a simplified estimate: the rate the elevator bank could carry if every elevator ran full on end-to-end round trips with no stops. Arrivals in each time unit follow a Poisson distribution with mean `demand * handling_capacity`.

Real throughput differs from this estimate in both directions. Interfloor trips are shorter than end to end, so an elevator can carry more, and 120% interfloor is not overload. Peaks fill the elevators on one leg and dwell time costs time, so 120% up-peak is overload: wait times grow until arrivals stop, then drain.

**Patterns:**

- **up-peak:** 85% of trips go from the lobby (floor 1) to a random upper floor. The rest are random pairs.
- **down-peak:** the mirror image: 85% go from a random upper floor to the lobby.
- **interfloor:** random pairs, origin and destination floors different.

**Profiles** chain segments of (duration, demand, pattern), so demand can change during a run. Random numbers come from `random.Random(seed)`, so a seed always gives the same passengers. Passenger IDs are `p1`, `p2`, and so on, in time order.

## Files

- **Input** `requests.csv`: header `time,id,source,dest`, as in the spec: `source` is the origin floor and `dest` the destination floor. Rows are sorted by time, keeping input order within one time. Blank lines are skipped. A bad row raises `ValueError` naming the line: missing column, non-integer value, negative time, origin floor equal to destination floor, or duplicate ID. `Simulation.run` rejects floors outside `1..floors`.
- **Output** `positions.csv`, the elevator positions log: header `time,elevator1,...,elevatorN`, one row per time unit from 0 to the end.
- **Output** `events.csv`: header `time,passenger,elevator,floor,event`. Elevators are numbered from 1. `event` is `assigned`, `boarded` or `arrived`. Rows are in the order things happened.

Inside the code, elevators are numbered from 0. Output files add 1.

## Trace format

`elevator-sim trace` and `POST /api/run` return the same JSON: `{"format": 1, "traces": [...]}`, one trace per scheduler, all on the same passengers. Elevators are numbered from 0. Each trace holds:

- `scheduler`, and `config`: `floors`, `elevators`, `capacity`, `dwell_time`, `served_floors` (one sorted list per elevator, or `null`), `max_wait` (the one the scheduler uses, or `null`).
- `passengers`: `id`, `time`, `source`, `dest`, `elevator`, `boarded`, `arrived`, `wait`, `total`.
- `units`, one per time unit `t`: `floors` is row `t` of the elevator positions log (the floor at the start of the unit); `dirs`, `inside` and `waiting` are each elevator's direction, riders and waiting passengers after the step; `events` lists `[kind, passenger, elevator, floor]` in the order they happened.
- `assignments`, one per passenger in assignment order: `t`, `passenger`, `offered` (the elevators that serve the trip), `rule`, `scores` (one per elevator, `null` if not scored, `"stuck"` for an infinite cost), `pick`.
  - `rule` `turn` (round robin): `turn` is the counter; the score is how many turns until each elevator's go.
  - `rule` `floors` (nearest car): the score is `floors_to_reach`.
  - `rule` `cost` (lowest cost, zoned): the score is `incremental_cost`; `trials` holds, for each scored elevator, both trial allocations (`with` and `without`) with their `sum` and one row per passenger, `[id, boarded, arrived, cost]`. Zoned adds `band`, and scores only the elevators of that band.
- `summary`: `passengers`, `time_units`, `wait` and `total` (each `mean`, `p95`, `max`; `null` with no passengers), `served_per_elevator`.

Each recorded pick is checked against the scheduler's own choice. Limits keep one request small: 2 to 60 floors, 1 to 10 elevators, capacity 1 to 20, dwell time 0 to 5, demand 0% to 200%, run length 1 to 1000, at most 1000 passengers and 3 schedulers, 5000 time units and 20 seconds per run. Past a limit the run raises `ValueError` with the reason.

## Live page API

`elevator-sim serve [--port 8080]` binds to 127.0.0.1 only and uses the standard library. It writes no request log. `--log-requests` together with `ELEVATOR_SIM_LOG=local` (or `dev`, `test`) logs the method, route and status of each request, never the body.

| Route | Returns |
|---|---|
| `GET /` | The page, `src/elevator_sim/app/ui/index.html` |
| `GET /api/scenarios` | The named scenarios, the schedulers, the presets, the patterns, the defaults and the limits |
| `GET /api/code` | The core functions the Code panel shows, read from the source at request time, and the lines each moment lights |
| `GET /api/say?text=` | A spoken clip of up to 400 characters from the Kokoro server at `ELEVATOR_SIM_VOICE_URL` (default `http://127.0.0.1:8350`, local hosts only); 503 if none answers |
| `POST /api/run` | Traces in the format above |

`POST /api/run` takes a JSON object with one passenger source: `scenario` (a name; only `dwell_time` may change), `requests` (request file text, or a list of `{time, id, source, dest}`), or neither (generate with `demand` in percent, `pattern`, `seed`, `run_length`). Building settings are `floors`, `elevators`, `capacity`, `dwell_time` and `layout` (`all`, or `express`: half the elevators local below the middle floor, half express above it). `schedulers` lists 1 to 3 names; `max_wait` is `default`, `off` or a whole number, and applies to lowest cost and zoned. Bad input returns 400 with `{"error": "..."}`, the same message `Config`, the request parser and the limits give. A body over 200,000 bytes returns 413; more than 2 runs at once returns 429.
