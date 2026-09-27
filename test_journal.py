"""Runnable checks: python3 test_journal.py  (no test framework, plain asserts).

Covers the two things that would silently produce wrong numbers: the PnL sign
convention and the drawdown/streak walks.
"""

import os
import tempfile

import analytics
import journal


def trade(**kw):
    """A long trade by default, so each test only states what it cares about."""
    base = {
        "id": 1,
        "opened_at": "2026-01-01 00:00:00",
        "symbol": "BTCUSDT",
        "side": "long",
        "entry": 100.0,
        "exit": 110.0,
        "size": 2.0,
        "stop": 95.0,
        "fees": 0.0,
    }
    base.update(kw)
    return base


def check_pnl_direction():
    # Long that gained: 10 x 2 = +20. Short on the same move is the mirror image.
    assert analytics.pnl_usd(trade()) == 20.0
    assert analytics.pnl_usd(trade(side="short")) == -20.0
    # A short that fell from 100 to 90 is a profit.
    assert analytics.pnl_usd(trade(side="short", exit=90.0)) == 20.0
    # Fees always reduce PnL, even on a winner.
    assert analytics.pnl_usd(trade(fees=5.0)) == 15.0
    # Loss: long 100 -> 95 with size 2 = -10.
    assert analytics.pnl_usd(trade(exit=95.0)) == -10.0


def check_r_multiple():
    # Risk = |100 - 95| x 2 = 10. PnL 20 -> +2R. Loser 95 -> -10 -> -1R.
    assert analytics.risk_usd(trade()) == 10.0
    assert analytics.r_multiple(trade()) == 2.0
    assert analytics.r_multiple(trade(exit=95.0)) == -1.0
    # No stop means no R. Excluded from R stats, never treated as 0R.
    assert analytics.risk_usd(trade(stop=None)) is None
    assert analytics.r_multiple(trade(stop=None)) is None


def check_max_drawdown():
    # Peak 20, then down to -10 => 30 of drawdown.
    assert analytics.max_drawdown([10, 10, -30]) == 30.0
    # Monotonically rising: no drawdown at all.
    assert analytics.max_drawdown([5, 5, 5]) == 0.0
    # Empty journal: flat.
    assert analytics.max_drawdown([]) == 0.0
    # Every trade loses: equity falls 10 then 20, so the trough is 20 below the
    # starting peak of 0. Drawdown is measured from initial equity, not from the
    # first trade, so it is still positive and never negative.
    assert analytics.max_drawdown([-10, -10]) == 20.0
    assert analytics.max_drawdown([-10]) == 10.0


def check_streaks():
    assert analytics.streaks([1, 1, 1, -1, -1]) == (3, 2)
    assert analytics.streaks([-1, 1, -1, 1, -1]) == (1, 1)
    assert analytics.streaks([]) == (0, 0)


def check_disposition():
    # Winners averaged below the magnitude of losers => flagged.
    flagged = analytics.disposition([0.5, 0.7], [-1.0, -1.0])
    assert flagged["flagged"] is True
    assert abs(flagged["ratio"] - 0.6) < 1e-9
    # Winners held longer than losers => not flagged.
    healthy = analytics.disposition([1.5, 1.5], [-1.0, -1.0])
    assert healthy["flagged"] is False
    # Need both sides to say anything at all.
    assert analytics.disposition([], [-1.0]) is None


def check_summarize():
    empty = analytics.summarize([])
    assert empty == {"trades": 0}

    trades = [
        trade(id=1, opened_at="2026-01-01 00:00:00", exit=110.0),   # +20
        trade(id=2, opened_at="2026-01-02 00:00:00", exit=95.0),    # -10
        trade(id=3, opened_at="2026-01-03 00:00:00", exit=120.0),   # +40
    ]
    s = analytics.summarize(trades)
    assert s["trades"] == 3
    assert s["net_pnl"] == 50.0
    assert s["wins"] == 2 and s["losses"] == 1
    assert abs(s["win_rate"] - 2 / 3) < 1e-9
    assert abs(s["expectancy"] - 50 / 3) < 1e-9
    assert abs(s["profit_factor"] - 60 / 10) < 1e-9
    assert s["max_drawdown"] == 10.0
    assert s["best"] == 40.0 and s["worst"] == -10.0
    assert s["symbols"] == ["BTCUSDT"]


def check_unsorted_input_is_ordered_first():
    """summarize() must sort by open time, so drawdown is chronologically real."""
    trades = [
        trade(id=1, opened_at="2026-01-03 00:00:00", exit=120.0),   # +40 first in list
        trade(id=2, opened_at="2026-01-01 00:00:00", exit=95.0),    # -10 actually earliest
        trade(id=3, opened_at="2026-01-02 00:00:00", exit=110.0),   # +20 middle
    ]
    s = analytics.summarize(trades)
    # Chronological: -10, +20, +40 -> peak 0 then 60, no drawdown.
    assert s["max_drawdown"] == 10.0, "input order must not change the drawdown"
    assert s["longest_win_streak"] == 2


def check_csv_rejects_bad_rows():
    """The trust boundary: bad rows are refused and reported, not inserted."""
    good = "opened_at,symbol,side,entry,exit,size,stop,fees\n2026-01-01 00:00,BTCUSDT,long,100,110,2,95,0.5\n"
    bad_rows = (
        "2026-01-02 00:00,ETHUSDT,sideways,100,110,2,95,0\n"    # invalid side
        "not-a-date,ETHUSDT,long,100,110,2,95,0\n"             # unparseable date
        "2026-01-03 00:00,ETHUSDT,long,0,110,2,95,0\n"         # entry must be > 0
        "2026-01-04 00:00,ETHUSDT,long,100,abc,2,95,0\n"        # exit not numeric
        "2026-01-05 00:00,,long,100,110,2,95,0\n"               # missing symbol
    )
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "t.csv")
        with open(path, "w") as fh:
            fh.write(good + bad_rows)
        conn = journal.connect(os.path.join(tmp, "j.db"))
        inserted, errors = journal.import_csv(conn, path)
        assert inserted == 1, inserted
        assert len(errors) == 5, errors
        assert all("row" in reason for _, reason in errors)
        # Only the good row made it into the DB.
        assert len(journal.all_trades(conn)) == 1


def check_csv_requires_columns():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "bad.csv")
        with open(path, "w") as fh:
            fh.write("symbol,side\nBTCUSDT,long\n")
        conn = journal.connect(os.path.join(tmp, "j.db"))
        try:
            journal.import_csv(conn, path)
        except ValueError as exc:
            assert "missing required column" in str(exc)
        else:
            raise AssertionError("expected a ValueError for a missing-column CSV")


def main():
    checks = [v for k, v in sorted(globals().items()) if k.startswith("check_")]
    for check in checks:
        check()
        print(f"  ok  {check.__name__}")
    print(f"\n{len(checks)} checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
