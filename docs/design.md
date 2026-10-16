# Design

This file is the contract every module follows. If code and this file disagree, one of them is a bug.

## Modules: one idea each

| Module | The one idea it holds |
|---|---|
| `models.py` | Data only: `Request`, `Passenger`, `Elevator`, `Event`, `Result`, `Direction` |
| `config.py` | Building and elevator bank settings, checked on creation |
| `direction.py` | Direction logic for one elevator: collective control, boarding, dwell time |
| `scheduler.py` | The scheduler picks the elevator for a new passenger: round robin, nearest car, lowest cost |
| `simulation.py` | The clock: reveal requests, assign them, log positions, move elevators |
| `traffic.py` | Synthetic passengers: traffic patterns, demand levels, daily profiles |
| `files.py` | Read the request file, write the two log files |
| `stats.py` | Summary numbers for a finished run |
| `invariants.py` | Checks that a finished run obeyed every rule |
| `scenarios.py` | The named extreme scenarios and the comparison report |
| `cli.py` | The command line |

Dependencies point one way: `models` and `config` at the bottom, `direction` above them, `scheduler` and `simulation` above that, `scenarios` and `cli` on top.

## One time unit

Time moves in whole time units. One time unit is the time an elevator takes to travel one floor. At time `t`:

1. **Reveal.** Requests with `time == t` become visible, in input order. Nothing later is visible.
2. **Assign.** For each revealed request, the scheduler picks an elevator. The passenger joins that elevator's `waiting` list. Event `assigned` at `t`.
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
