# Elevator system simulation

A simulation of elevator system dispatch. Passengers enter a destination floor before they board, the system assigns an elevator at once, and the assignment is final. The simulation compares three schedulers on total time per passenger: wait time plus travel time.

## Run

Requires Python 3.12 or later and [uv](https://docs.astral.sh/uv/).

```
uv sync
uv run elevator-sim run examples/requests.csv --elevators 2 --out out
uv run elevator-sim compare
uv run pytest
```

`run` reads a request file (`time,id,source,dest`), writes `positions.csv` and `events.csv` to `out/`, and prints wait, travel and total time statistics. `compare` runs the built-in scenarios under each scheduler and prints a table.

## Schedulers

- **round-robin:** elevators in turn.
- **nearest-car:** the elevator with the fewest floors to reach the passenger, moving their way.
- **lowest-cost:** for each elevator, run a copy forward with and without the new passenger, and pick the elevator that adds the least total time for everyone on it.

Each elevator serves its stops in floor order and reverses when no stop is left ahead (collective control). Time moves in whole units of one floor of travel, and the simulation never looks at requests made later than now.

## More

- [docs/design.md](docs/design.md): the model, step by step.
- [docs/test-plan.md](docs/test-plan.md): the tests, the extreme scenarios and the rules every run must pass.
