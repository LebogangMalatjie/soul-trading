"""Historical MT5 backtest: python scripts/backtest_engulfing.py XAUUSD 5m."""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from strategies.engulfing import DEFAULT_CONFIG, build_trade_request  # noqa: E402

TIMEFRAMES = {"1m": "TIMEFRAME_M1", "5m": "TIMEFRAME_M5", "15m": "TIMEFRAME_M15"}


def simulate(frame: pd.DataFrame, symbol_info, symbol: str, timeframe: str,
             spread_points: float, slippage_points: float) -> list[float]:
    point = float(symbol_info.point)
    config = {
        **DEFAULT_CONFIG,
        "paper_mode": True,
        "use_session_filter": False,
        "use_news_filter": False,
        "use_higher_timeframe_confirmation": False,
        "max_spread_points": max(float(DEFAULT_CONFIG["max_spread_points"]), spread_points),
    }
    results: list[float] = []
    free_index = 0
    slip = slippage_points * point
    spread = spread_points * point

    for i in range(16, len(frame) - 1):
        if i < free_index:
            continue
        history = frame.iloc[:i + 1].copy()
        request = build_trade_request(
            history, symbol=symbol, timeframe=timeframe, config=config,
            spread_points=spread_points, allowed_session=True, in_news_blackout=False,
        )
        if not request or not request["accepted"]:
            continue

        buy = request["direction"] == "BUY"
        sign = 1 if buy else -1
        entry = float(frame.iloc[i]["open"]) + (spread / 2 + slip) * sign
        sl = float(request["sl"])
        risk = abs(entry - sl)
        if risk <= 0:
            continue
        tp = entry + sign * risk * float(config["rr_ratio"])
        exit_price = None
        for j in range(i, len(frame)):
            bar = frame.iloc[j]
            stop_hit = float(bar["low"]) <= sl if buy else float(bar["high"]) >= sl
            target_hit = float(bar["high"]) >= tp if buy else float(bar["low"]) <= tp
            if stop_hit:
                exit_price, free_index = sl - sign * slip, j + 1
                break
            if target_hit:
                exit_price, free_index = tp - sign * slip, j + 1
                break
        if exit_price is None:
            exit_price = float(frame.iloc[-1]["close"]) - sign * (spread / 2 + slip)
            free_index = len(frame)
        pnl = (exit_price - entry) * sign
        results.append(pnl / risk)
    return results


def metrics(trades: list[float]) -> dict[str, float]:
    wins = [result for result in trades if result > 0]
    losses = [result for result in trades if result < 0]
    total = peak = max_drawdown = 0.0
    for result in trades:
        total += result
        peak = max(peak, total)
        max_drawdown = max(max_drawdown, peak - total)
    gross_profit, gross_loss = sum(wins), abs(sum(losses))
    return {
        "trades": len(trades),
        "win_rate_pct": len(wins) / len(trades) * 100 if trades else 0.0,
        "average_r": sum(trades) / len(trades) if trades else 0.0,
        "profit_factor": gross_profit / gross_loss if gross_loss else math.inf if gross_profit else 0.0,
        "max_drawdown_r": max_drawdown,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("symbol")
    parser.add_argument("timeframe", choices=TIMEFRAMES)
    parser.add_argument("--bars", type=int, default=10000)
    parser.add_argument("--spread-points", type=float, default=2.0)
    parser.add_argument("--slippage-points", type=float, default=1.0)
    parser.add_argument("--terminal-path", default=None)
    args = parser.parse_args()

    try:
        import MetaTrader5 as mt5
    except ImportError:
        parser.error("MetaTrader5 is required on Windows: install it into the backend environment.")
    initialized = mt5.initialize(path=args.terminal_path) if args.terminal_path else mt5.initialize()
    if not initialized:
        print(f"MT5 initialization failed: {mt5.last_error()}", file=sys.stderr)
        return 1
    try:
        info = mt5.symbol_info(args.symbol)
        if info is None:
            print(f"Unknown MT5 symbol: {args.symbol}", file=sys.stderr)
            return 1
        rates = mt5.copy_rates_from_pos(args.symbol, getattr(mt5, TIMEFRAMES[args.timeframe]), 0, args.bars)
        if rates is None or len(rates) < 100:
            print(f"Insufficient MT5 history: {mt5.last_error()}", file=sys.stderr)
            return 1
        frame = pd.DataFrame(rates)
        frame["time"] = pd.to_datetime(frame["time"], unit="s", utc=True)
        result = simulate(frame, info, args.symbol, args.timeframe,
                          args.spread_points, args.slippage_points)
        report = metrics(result)
        print(f"{args.symbol} {args.timeframe} — spread {args.spread_points:g} points, "
              f"slippage {args.slippage_points:g} points")
        print(f"Trades: {report['trades']}")
        print(f"Win rate: {report['win_rate_pct']:.2f}%")
        print(f"Average R: {report['average_r']:.3f}")
        print(f"Profit factor: {report['profit_factor']:.3f}")
        print(f"Max drawdown: {report['max_drawdown_r']:.3f}R")
        return 0
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
