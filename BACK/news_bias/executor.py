"""Execution for the News Bias Engine (Part 4D/5/6).

Places/cancels the pending ladder, monitors the basket take-profit (close all
and cancel unfilled once combined floating profit reaches the ZAR target),
expires unfilled orders, and honours the kill switch before every action.

Each event/symbol is wrapped defensively by the caller; here a single failed
order is logged and skipped so it never stops the rest of the ladder.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

from . import store
from .config import BiasEngineConfig


def event_magic(event_key: str, symbol: str) -> int:
    """Stable per-event/symbol magic number for tagging + cleanup."""
    digest = hashlib.blake2s(f"{event_key}|{symbol}".encode(), digest_size=4).digest()
    return int.from_bytes(digest, "big") % 2_000_000_000


@dataclass(slots=True)
class PlacementResult:
    placed: int
    failed: int
    skipped_kill_switch: bool
    errors: list[str]


async def place_plan(broker, con, plan: dict, *, engine_cfg: BiasEngineConfig,
                     auto_trading_enabled) -> PlacementResult:
    """Place every pending order in the plan's ladder. Kill switch wins."""
    if not auto_trading_enabled():
        return PlacementResult(0, 0, True, ["kill switch active; nothing placed"])
    if engine_cfg.dry_run or plan.get("dry_run", True):
        return PlacementResult(0, 0, False, ["dry-run: plan logged, no orders placed"])

    ladder = (plan.get("plan_json") or {}).get("orders", [])
    plan_id = plan["id"]
    event_key = plan["event_key"]
    symbol = plan["symbol"]
    magic = event_magic(event_key, symbol)
    expiration = plan.get("expires_at")

    placed = failed = 0
    errors: list[str] = []
    for leg in ladder:
        try:
            order_id = await store.create_order(con, order={
                "plan_id": plan_id, "event_key": event_key, "symbol": symbol,
                "broker_symbol": leg.get("broker_symbol", symbol),
                "order_type": leg["order_type"], "entry_price": leg["entry_price"],
                "lots": leg["lots"], "stop_loss": leg.get("stop_loss"),
                "take_profit": leg.get("take_profit"), "magic": magic,
                "comment": f"nb:{event_key[:18]}",
            })
        except Exception as exc:  # noqa: BLE001
            failed += 1
            errors.append(f"row create failed: {exc}")
            continue
        if not auto_trading_enabled():
            await store.set_order_status(con, order_id, "cancelled",
                                         error="kill switch fired mid-placement")
            break
        try:
            broker_id = await broker.place_pending_order(
                leg.get("broker_symbol", symbol), leg["order_type"], leg["entry_price"],
                leg["lots"], leg.get("stop_loss") or 0.0, leg.get("take_profit") or 0.0,
                magic, f"nb:{event_key[:18]}", expiration=expiration,
            )
            await store.set_order_broker_id(con, order_id, broker_id)
            placed += 1
        except Exception as exc:  # noqa: BLE001 - one failed leg must not stop the rest
            failed += 1
            errors.append(str(exc))
            await store.set_order_status(con, order_id, "rejected", error=str(exc))
            continue

    if placed:
        await store.set_plan_status(con, plan_id, "executed")
    return PlacementResult(placed, failed, False, errors)


async def cancel_plan(broker, con, plan: dict) -> int:
    """Cancel every still-pending order for a plan; returns count cancelled."""
    orders = await store.orders_for_plan(con, plan["id"])
    cancelled = 0
    for o in orders:
        if o["status"] != "pending" or not o.get("broker_order_id"):
            continue
        try:
            await broker.cancel_order(o["broker_order_id"])
            await store.set_order_status(con, o["id"], "cancelled")
            cancelled += 1
        except Exception:  # noqa: BLE001
            continue
    return cancelled


async def basket_positions(broker, plan: dict) -> list[dict]:
    """Positions belonging to this plan, matched by magic number."""
    magic = event_magic(plan["event_key"], plan["symbol"])
    positions = await broker.positions()
    return [p for p in positions if int(p.get("magic", 0) or 0) == magic]


async def monitor_basket(broker, con, plan: dict, *, engine_cfg: BiasEngineConfig,
                         auto_trading_enabled, zar_rate: float) -> str:
    """Close the whole basket once floating profit >= target; else keep holding.

    Returns 'target_hit' | 'holding' | 'kill_switch' | 'flat'. ``zar_rate``
    converts account-currency profit to ZAR (1.0 when the account is already ZAR).
    """
    if not auto_trading_enabled():
        return "kill_switch"
    ours = await basket_positions(broker, plan)
    if not ours:
        return "flat"
    profit_zar = sum(float(p.get("floating_profit", 0.0)) for p in ours) * zar_rate
    if profit_zar >= engine_cfg.target_zar:
        for p in ours:
            try:
                await broker.close_position(str(p.get("id")))
            except Exception:  # noqa: BLE001
                continue
        await cancel_plan(broker, con, plan)          # cancel any unfilled rungs
        await store.set_plan_status(con, plan["id"], "done")
        return "target_hit"
    return "holding"


async def expire_plan(broker, con, plan: dict, *, engine_cfg: BiasEngineConfig,
                      auto_trading_enabled) -> str:
    """At expiry: cancel unfilled orders; apply the fallback to filled ones."""
    cancelled = await cancel_plan(broker, con, plan)
    fallback = engine_cfg.for_symbol(plan["symbol"]).fallback
    if auto_trading_enabled() and fallback == "trail":
        # Hand filled positions to the existing ladder trailing stop: leave them
        # open; the engine's normal position loop manages them.
        pass
    else:
        for p in await basket_positions(broker, plan):
            try:
                await broker.close_position(str(p.get("id")))
            except Exception:  # noqa: BLE001
                continue
    await store.set_plan_status(con, plan["id"], "expired")
    return f"expired (cancelled {cancelled})"

