# Test plan

Every test is written first and seen to fail (red), then the code makes it pass (green). Each layer below has its own test file.

## Layers

| Layer | File | What it proves |
|---|---|---|
| Config | `tests/test_config.py` | Bad settings are refused, defaults match the design |
| Input and output | `tests/test_files.py` | Request files parse, bad rows name their line, logs have the right shape |
| Direction logic | `tests/test_direction.py` | One elevator follows collective control, boards, unloads, respects capacity and dwell time |
| Scheduler | `tests/test_scheduler.py` | Each scheduler picks the elevator the design says, and never changes an elevator |
| Simulation | `tests/test_simulation.py` | The clock, worked examples with exact times, no peeking ahead |
| Traffic | `tests/test_traffic.py` | Patterns, demand levels and profiles produce what they claim |
| Statistics | `tests/test_stats.py` | Min, max, mean and percentiles are right |
| Invariants | `tests/test_invariants.py` | The rule checker catches each kind of broken run |
| Scenarios | `tests/test_scenarios.py` | Every extreme scenario runs to the end and obeys every rule |
| Command line | `tests/test_cli.py` | The command reads a file and writes the two logs and a summary; the earlier flags still work |
| Zoned scheduler | `tests/extensions/test_zoning.py` | The band split, the choice inside a band, and that zoned runs obey every rule |
| Express elevators | `tests/extensions/test_express.py` | The served-floor filter, the error for a trip no elevator serves, both 40-floor scenarios, and no stop at an unserved floor |
| Trace | `tests/test_trace.py` | Traces match `Simulation.run`, each assignment's scores pick the scheduler's elevator, bad parameters are refused, the presets match the named scenarios |
| Server | `tests/test_server.py` | Each route on a free port: 200 and 400 cases, 127.0.0.1 only, and no request log unless both the flag and the environment allow it |
| Fairness study | `tests/extensions/test_fairness.py` | The table shape, and that the default maximum wait time trades mean total time for a shorter longest wait |

## Extremes

The scenario matrix crosses 3 axes. Every cell runs under all 3 schedulers and must pass every invariant.

| Axis | Values |
|---|---|
| Building | small (5 floors), typical (20 floors), tall (60 floors), tallest (160 floors) |
| Elevator bank | smallest (1 elevator, capacity 1), small (2 elevators, capacity 4), typical (4 elevators, capacity 10), largest (10 elevators, capacity 20) |
| Demand | 20%, 50%, 80%, 100%, 120% of handling capacity, plus a variable daily profile |

Not every cell is run: 4 x 4 x 6 x 3 is 288 runs. The scenario tests pick these:

- Each demand level on the typical building with the typical elevator bank.
- Each building with the typical elevator bank at 80% demand.
- Each elevator bank in the typical building at 80% demand.
- The four corners: smallest elevator bank in the tallest building, largest elevator bank in the small building, both at 100%.
- The variable profile: quiet, up-peak at 120%, interfloor at 50%, down-peak at 100%, quiet.
- Express: 40 floors, 4 elevators of 10, 100% up-peak, once with every elevator serving every floor and once with 2 local (1 to 20) and 2 express (1 and 21 to 40). Both drop the trips the express layout cannot carry, so they share their passengers.

Fast runs use a horizon of 200 to 400 time units. Runs marked `slow` use longer horizons, and `pytest -m "not slow"` skips them.

## Invariants every run must obey

1. **Everyone arrives.** Every request is assigned once, boards once and arrives once, at its own destination floor.
2. **Order of events.** requested <= assigned <= boarded <= arrived. Assigned equals requested.
3. **No peeking.** No passenger is assigned before their request time.
4. **Capacity.** No elevator ever holds more passengers than its capacity.
5. **One floor per time unit.** An elevator's floor changes by at most 1 between rows, and stays in `1..floors`.
6. **Boarding and arrival happen where the elevator is.** The event floor equals the elevator's floor in that row.
7. **Direction.** A passenger rides only in their own direction. An elevator with passengers in it never reverses.
8. **Final assignment.** A passenger boards the elevator they were assigned.
9. **No early stop.** The run ends only when every elevator is empty and has no waiting passengers.
10. **Served floors.** An elevator boards or lets off passengers only at floors it serves.

## Expected results, checked as tests

These are behaviors, not tuned numbers. Each one would show a real bug if it failed.

- At 20% demand, every scheduler keeps mean wait time under one full trip of the shaft.
- At 80% and 100% demand in the typical case, lowest cost has a lower mean total time than round robin.
- With dwell time 0, the default maximum wait time never binds: in the 120% up-peak, lowest cost with and without it picks the same elevator for every passenger.
- With dwell time 3, in the typical interfloor case at 100% and 120%, the maximum wait time gives a shorter longest wait time and a longer mean total time than `lowest-cost-nocap`.
- At 120% up-peak demand, every run still ends, and the longest wait time is longer than at 80%. Interfloor traffic is not used here, because interfloor elevators rarely fill and 120% interfloor is not overload.
- One elevator of capacity 1: passengers are served one at a time, in a fixed and checkable order.
- A 160-floor building with 1 elevator still serves a passenger from floor 160 to floor 1, with a total time of at least 159.

## Worked examples with exact times

`tests/test_simulation.py` holds hand-checked examples. Each states the expected wait time and total time for every passenger, so a reader can follow the clock by hand.

1. One elevator, one passenger at the lobby going to floor 5: wait time 0, total time 4.
2. One elevator at floor 1, a passenger at floor 5 going to floor 1: wait time 4, total time 8.
3. The spec's sample, with 2 elevators and 60 floors: passenger1 (1 to 51) and passenger2 (1 to 37) at time 0, passenger3 (20 to 1) at time 10.
4. The two-passenger example from the explainer, checked at the scheduler in `tests/test_scheduler.py`: at time 1, elevator A is at floor 2 going up for P (10 to 2), and elevator B is at floor 13 going up with one passenger in it going to 18. Q asks to go from 9 to 16. Nearest car sends Q to A. Lowest cost sends Q to B, because the incremental cost of Q is 26 on A and 21 on B.
5. Dwell time 2: one passenger at the lobby going to floor 3: board at 0, leave at 2, arrive at 4.
6. Capacity 1, two passengers at the lobby at time 0 going to floors 3 and 5: the first boards at 0, the second waits for the elevator to return.

## How to run

```
uv run pytest                 # everything
uv run pytest -m "not slow"   # fast layer only
```
