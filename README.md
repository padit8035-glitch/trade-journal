# trade-journal

A dependency-free CLI that turns a raw trade log into the performance numbers
that actually matter: expectancy, profit factor, R-multiples, maximum drawdown,
and a **disposition-effect check** for traders who realise their winners early
and let losers widen.

Python 3.10+ standard library only. No `pip install`, no virtualenv, no
lockfile, nothing to break on a dependency bump.

## Quick start

```bash
git clone https://github.com/padit8035-glitch/trade-journal
cd trade-journal

python3 __main__.py demo                  # synthetic data, no files touched
python3 __main__.py import sample_trades.csv
python3 __main__.py report
```

## Example output

```
Loaded 140 synthetic trades (seed=7, not real money).

TRADE JOURNAL - PERFORMANCE REPORT
============================================
  Trades          140
  Net PnL      $274.35
  Win rate        56.4%   (79W / 61L)
  Expectancy    $1.96 / trade
  Profit factor   1.66
  Max drawdown  -$104.38
  Best / worst  $66.36 / -$61.33
  Streaks        9 wins / 5 losses
  Avg R         +0.08R   (from 140 trades with a stop)

  Disposition effect
    Winners  +0.52R avg
    Losers   -0.48R avg
    Ratio     1.08
    -> Winners realised at least as large as losers. Holding is consistent.

  Symbols: ARBUSDT, BTCUSDT, ETHUSDT, SOLUSDT```

> The bundled data is **synthetic** (seeded PRNG, seed=7) and does not represent
> real trading results.

## CSV format

`--` means optional. Only the first six columns are required.

| Column | Required | Example |
| --- | --- | --- |
| `opened_at` | yes | `2026-01-05 09:30` (also `2026-01-05`, `2026/01/05`, `05/01/2026`) |
| `symbol` | yes | `BTCUSDT` |
| `side` | yes | `long` or `short` |
| `entry` | yes | `104.20` |
| `exit` | yes | `111.80` |
| `size` | yes | `1.5` |
| `stop` | no | `99.00` — needed for R-multiple metrics |
| `fees` | no | `0.40` |
| `notes` | no | `breakout retest` |

Rows are validated on import. Invalid rows are skipped and reported by line
number rather than inserted silently:

```
Imported 1 trade(s) into b.db
  skipped row 3: side='sideways' must be 'long' or 'short'
  skipped row 4: entry must be > 0, got 0.0
  skipped row 5: exit='abc' is not a number```

## Metrics

| Metric | Definition |
| --- | --- |
| **Net PnL** | Sum of `(exit - entry) * size`, direction-adjusted, minus fees. |
| **Win rate** | Winning trades / total. Meaningless alone — read it with expectancy. |
| **Expectancy** | Average PnL per trade. The single number that decides whether a strategy is viable. |
| **Profit factor** | Gross profit / gross loss. Above 1.0 is profitable; below 1.0 burns capital. |
| **Max drawdown** | Largest peak-to-trough fall of the cumulative PnL curve, measured from starting equity. |
| **R-multiple** | PnL divided by the amount the initial stop risked. Lets you compare a 2x-larger loser on a tight stop against a small loser on a wide one. |
| **Disposition effect** | Flags when average winner R is smaller than average loser R — realising profits early while giving losses room to run. |

Trades without a `stop` are excluded from R-based statistics rather than being
counted as `0R`, which would silently distort the averages.

## Design

```
journal.py     SQLite storage + CSV import. The only place that validates input.
analytics.py   Pure functions: trade in, numbers out. No I/O, no database.
__main__.py    CLI. Import, report, demo.
test_journal.py  9 assert-based checks, no test framework.
```

Keeping `analytics.py` free of I/O is deliberate: the metrics can be tested
without a database, and the risk calculation is obvious to read.

## Tests

```bash
python3 test_journal.py
```

```
ok  check_csv_rejects_bad_rows
  ok  check_csv_requires_columns
  ok  check_disposition
  ok  check_max_drawdown
  ok  check_pnl_direction
  ok  check_r_multiple
  ok  check_streaks
  ok  check_summarize
  ok  check_unsorted_input_is_ordered_first

9 checks passed
```

CI runs these on Python 3.10, 3.11, and 3.12 with no install step.

## License

MIT
