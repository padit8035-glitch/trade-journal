"""Performance metrics.

Every function is pure: a trade (dict-like row) in, numbers out. No I/O, so
the math is testable without a database and the CV claim "tested metrics" is
literally true.
"""


def pnl_usd(trade):
    """Signed net PnL in USD. Fees are always a cost, never a credit."""
    direction = 1 if trade["side"] == "long" else -1
    return (trade["exit"] - trade["entry"]) * trade["size"] * direction - trade["fees"]


def risk_usd(trade):
    """USD put at risk by the initial stop, or None when no stop was recorded."""
    if trade["stop"] is None:
        return None
    return abs(trade["entry"] - trade["stop"]) * trade["size"]


def r_multiple(trade):
    """Realised PnL in units of initial risk. None without a stop -> excluded from R stats."""
    risk = risk_usd(trade)
    if not risk:
        return None
    return pnl_usd(trade) / risk


def max_drawdown(pnls):
    """Largest peak-to-trough drop of the cumulative PnL curve, in USD (>= 0)."""
    equity = peak = worst = 0.0
    for pnl in pnls:
        equity += pnl
        peak = max(peak, equity)
        worst = max(worst, peak - equity)
    return worst


def streaks(pnls):
    """(longest winning run, longest losing run) in consecutive trades."""
    win = loss = best_win = best_loss = 0
    for pnl in pnls:
        if pnl > 0:
            win, loss = win + 1, 0
            best_win = max(best_win, win)
        else:
            loss, win = loss + 1, 0
            best_loss = max(best_loss, loss)
    return best_win, best_loss


def disposition(win_rs, loss_rs):
    """Compare average R of winners against average R of losers.

    Textbooks call avg R(winners) < |avg R(losers)| the disposition effect:
    realising winners early while giving losers room to widen. Requires trades
    that carry a stop; returns None when there is nothing to compare.
    """
    if not win_rs or not loss_rs:
        return None
    avg_win = sum(win_rs) / len(win_rs)
    avg_loss = abs(sum(loss_rs) / len(loss_rs))
    return {
        "avg_win_r": avg_win,
        "avg_loss_r": avg_loss,
        "ratio": (avg_win / avg_loss) if avg_loss else float("inf"),
        "flagged": avg_win < avg_loss,
    }


def summarize(trades):
    """Full performance summary. Returns {"trades": 0} for an empty journal."""
    trades = sorted(trades, key=lambda t: (t["opened_at"], t["id"]))
    count = len(trades)
    if not count:
        return {"trades": 0}

    pnls = [pnl_usd(t) for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    gross_win, gross_loss = sum(wins), -sum(losses)

    rs = [r for r in map(r_multiple, trades) if r is not None]
    best_win_run, best_loss_run = streaks(pnls)

    return {
        "trades": count,
        "net_pnl": sum(pnls),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": len(wins) / count,
        "expectancy": sum(pnls) / count,
        "profit_factor": (gross_win / gross_loss) if gross_loss else float("inf"),
        "max_drawdown": max_drawdown(pnls),
        "best": max(pnls),
        "worst": min(pnls),
        "avg_r": (sum(rs) / len(rs)) if rs else None,
        "r_count": len(rs),
        "longest_win_streak": best_win_run,
        "longest_loss_streak": best_loss_run,
        "disposition": disposition([r for r in rs if r > 0], [r for r in rs if r < 0]),
        "symbols": sorted({t["symbol"] for t in trades}),
    }
