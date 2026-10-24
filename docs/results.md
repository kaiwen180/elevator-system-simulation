# Results

Every table comes from `uv run elevator-sim compare` or `uv run elevator-sim fairness`, seed 1, dwell time 0 unless the row says otherwise. Times are in time units: one time unit is one floor of travel.

## Main scenarios

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

With one elevator every scheduler makes the same choice, so the rows match. `uv run elevator-sim compare` prints all 57 rows (19 scenarios, 3 schedulers); add `--scheduler zoned` for a fourth.

## Zone-based scheduler

`uv run elevator-sim compare --scenario 20f-4x10-demand100-interfloor --scenario 20f-4x10-demand100-up-peak --scheduler lowest-cost --scheduler zoned`

| scenario | scheduler | mean wait | max wait | mean total |
|---|---|---|---|---|
| 20f-4x10-demand100-interfloor | lowest-cost | 5.6 | 28 | 12.4 |
| 20f-4x10-demand100-interfloor | zoned | 16.0 | 37 | 22.9 |
| 20f-4x10-demand100-up-peak | lowest-cost | 12.4 | 26 | 22.3 |
| 20f-4x10-demand100-up-peak | zoned | 17.1 | 188 | 27.0 |

Zoning loses here: with 4 bands and 4 elevators, each passenger has 1 elevator to choose from, so lowest cost inside the band has no choice left to make.

## Express elevators

`uv run elevator-sim compare --scenario 40f-4x10-demand100-up-peak-all-floors --scenario 40f-4x10-demand100-up-peak-express`. Both scenarios drop the 7 of 159 trips the express layout cannot carry, so they share 152 passengers.

| layout | scheduler | mean wait | max wait | mean total | time units |
|---|---|---|---|---|---|
| all floors | round-robin | 36.7 | 75 | 56.7 | 379 |
| all floors | nearest-car | 45.2 | 183 | 65.2 | 496 |
| all floors | lowest-cost | 22.5 | 47 | 42.5 | 359 |
| express | round-robin | 30.8 | 91 | 50.8 | 390 |
| express | nearest-car | 24.7 | 100 | 44.7 | 355 |
| express | lowest-cost | 21.3 | 73 | 41.3 | 393 |

Express helps the simple schedulers most: nearest car's mean total drops from 65.2 to 44.7. Lowest cost gains 1.2 on the mean, but its longest wait grows from 47 to 73, because each passenger can choose between 2 elevators, not 4.

## Fairness against efficiency

`uv run elevator-sim fairness`: lowest cost with each maximum wait time, at dwell time 3. Mean total time measures efficiency; p95 wait and longest wait measure fairness. At dwell time 0 the maximum wait time binds only at 20 in interfloor (longest wait 28 to 25, mean total 12.4 to 13.8).

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
