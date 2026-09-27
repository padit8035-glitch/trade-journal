"""CLI: import a trade CSV, print a performance report.

    python3 __main__.py import trades.csv
    python3 __main__.py report
    python3 __main__.py demo            # synthetic data, no files needed
"""

import argparse
import random
import sys
from datetime import datetime, timedelta

import journal
from analytics import summarize

DB = "journal.db"


def _money(value):
    """Format USD with the sign outside the symbol: -$61.33, not $-61.33."""
    return f"-${abs(value):,.2f}" if value < 0 else f"${value:,.2f}"


def render(summary):
    """Format a summary as the plain-text report the CLI prints."""
    if not summary.get("trades"):
        return "Journal is empty. Import a CSV first:  python3 __main__.py import trades.csv"

    lines = [
        "TRADE JOURNAL - PERFORMANCE REPORT",
        "=" * 44,
        f"  Trades          {summary['trades']}",
        f"  Net PnL      {_money(summary['net_pnl'])}",
        f"  Win rate        {summary['win_rate'] * 100:.1f}%   ({summary['wins']}W / {summary['losses']}L)",
        f"  Expectancy    {_money(summary['expectancy'])} / trade",
        f"  Profit factor   {summary['profit_factor']:.2f}",
        f"  Max drawdown  -{_money(summary['max_drawdown'])}",
        f"  Best / worst  {_money(summary['best'])} / {_money(summary['worst'])}",
        f"  Streaks        {summary['longest_win_streak']} wins / {summary['longest_loss_streak']} losses",
    ]
    if summary["avg_r"] is not None:
        lines.append(f"  Avg R         {summary['avg_r']:+.2f}R   (from {summary['r_count']} trades with a stop)")

    disp = summary["disposition"]
    if disp:
        lines += [
            "",
            "  Disposition effect",
            f"    Winners  {disp['avg_win_r']:+.2f}R avg",
            f"    Losers   {-disp['avg_loss_r']:+.2f}R avg",
            f"    Ratio     {disp['ratio']:.2f}",
        ]
        if disp["flagged"]:
            lines.append("    -> Winners realised smaller than losers. Cutting winners early,")
            lines.append("       letting losers widen. The classic disposition effect.")
        else:
            lines.append("    -> Winners realised at least as large as losers. Holding is consistent.")

    lines += ["", f"  Symbols: {', '.join(summary['symbols'])}"]
    return "\n".join(lines)


def _demo_rows(count=140, seed=7):
    """Deterministic synthetic trades, so the README output is reproducible."""
    rng = random.Random(seed)
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "ARBUSDT"]
    start = datetime(2026, 1, 5, 9, 30)
    rows = []
    for i in range(count):
        symbol = symbols[i % len(symbols)]
        entry = round(rng.uniform(20, 600), 2)
        risk_pct = rng.uniform(0.02, 0.05)
        side = "long" if rng.random() < 0.65 else "short"
        stop = round(entry * (1 - risk_pct) if side == "long" else entry * (1 + risk_pct), 2)
        move = rng.gauss(0.004, 0.022)
        # Direction sign: a long profits when price rises, a short when it falls.
        exit_ = round(entry * (1 + move if side == "long" else 1 - move), 2)
        rows.append(
            {
                "opened_at": (start + timedelta(hours=i * 7)).strftime("%Y-%m-%d %H:%M"),
                "symbol": symbol,
                "side": side,
                "entry": entry,
                "exit": exit_,
                "size": round(rng.uniform(0.5, 3.0), 2),
                "stop": stop,
                "fees": round(rng.uniform(0.2, 1.2), 2),
                "notes": "",
            }
        )
    return rows


def _cmd_demo(conn):
    for row in _demo_rows():
        conn.execute(
            'INSERT INTO trades (opened_at, symbol, side, entry, "exit", size, stop, fees, notes)'
            " VALUES (:opened_at, :symbol, :side, :entry, :exit, :size, :stop, :fees, :notes)",
            row,
        )
    conn.commit()
    print("Loaded 140 synthetic trades (seed=7, not real money).\n")
    print(render(summarize(journal.all_trades(conn))))


def main(argv=None):
    parser = argparse.ArgumentParser(prog="trade-journal", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_imp = sub.add_parser("import", help="load trades from a CSV")
    p_imp.add_argument("csv", help="path to the trade CSV")
    p_imp.add_argument("--db", default=DB)

    p_rep = sub.add_parser("report", help="print the performance report")
    p_rep.add_argument("--db", default=DB)

    p_demo = sub.add_parser("demo", help="run on synthetic data")
    p_demo.add_argument("--db", default=":memory:")

    args = parser.parse_args(argv)

    if args.cmd == "demo":
        _cmd_demo(journal.connect(args.db))
        return 0

    conn = journal.connect(args.db)
    if args.cmd == "import":
        try:
            inserted, errors = journal.import_csv(conn, args.csv)
        except (OSError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        print(f"Imported {inserted} trade(s) into {args.db}")
        for _row_no, reason in errors:
            # journal.py already prefixes the row number, so it is self-contained.
            # Print it as-is rather than adding "row N:" a second time.
            print(f"  skipped {reason}")
        # Any skipped row is a data-quality problem worth a non-zero exit so
        # scripts and CI notice, even when most rows imported cleanly.
        return 1 if errors else 0

    print(render(summarize(journal.all_trades(conn))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
