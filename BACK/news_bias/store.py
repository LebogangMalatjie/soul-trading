"""Persistence for the News Bias Engine.

Thin asyncpg helpers. Every method takes an open connection so they are easy to
unit-test with a fake. All are additive and only touch the news_bias tables.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Optional


def _as_json(value, default):
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value) if value else default
    except (TypeError, ValueError):
        return default


# -- news items ------------------------------------------------------------
async def save_news_item(con, *, event_key: str, item: dict) -> None:
    await con.execute(
        """INSERT INTO news_items (event_key, title, source, url, published_at, summary, symbol_scores)
           VALUES ($1,$2,$3,$4,$5,$6,$7::jsonb)""",
        event_key, item.get("title", ""), item.get("source", ""), item.get("url", ""),
        item.get("published_at"), item.get("summary", ""),
        json.dumps(item.get("symbol_scores") or {}),
    )


async def news_items_for_event(con, event_key: str) -> list[dict]:
    rows = await con.fetch(
        "SELECT title, source, url, published_at, summary FROM news_items "
        "WHERE event_key=$1 ORDER BY published_at DESC NULLS LAST LIMIT 50", event_key)
    return [dict(r) for r in rows]


# -- predictions -----------------------------------------------------------
async def save_prediction(con, *, pred: dict, locked: bool = False) -> None:
    await con.execute(
        """INSERT INTO event_predictions
           (event_key, event_type, event_time, symbol, direction, probability_pct, news_score,
            reasons, sources, historical_support, formula, locked)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8::jsonb,$9::jsonb,$10::jsonb,$11,$12)""",
        pred["event_key"], pred["event_type"], pred["event_time"], pred["symbol"],
        pred["direction"], pred["probability_pct"], pred.get("news_score", 0.0),
        json.dumps(pred.get("reasons", [])), json.dumps(pred.get("sources", [])),
        json.dumps(pred.get("historical_support", {})), pred.get("formula", ""), locked,
    )


async def latest_predictions(con, event_key: str) -> list[dict]:
    rows = await con.fetch(
        """SELECT DISTINCT ON (symbol) symbol, direction, probability_pct, news_score,
                  reasons, sources, historical_support, formula, generated_at, locked
           FROM event_predictions WHERE event_key=$1
           ORDER BY symbol, generated_at DESC""", event_key)
    out = []
    for r in rows:
        d = dict(r)
        d["reasons"] = _as_json(d.get("reasons"), [])
        d["sources"] = _as_json(d.get("sources"), [])
        d["historical_support"] = _as_json(d.get("historical_support"), {})
        out.append(d)
    return out


async def fill_prediction_outcome(con, event_key: str, symbol: str,
                                  actual_direction: str, actual_move_points: float) -> None:
    await con.execute(
        """UPDATE event_predictions SET actual_direction=$3, actual_move_points=$4,
                  correct=(direction=$3)
           WHERE event_key=$1 AND symbol=$2 AND correct IS NULL""",
        event_key, symbol, actual_direction, actual_move_points,
    )


async def prediction_accuracy(con, event_type: Optional[str] = None) -> dict:
    if event_type:
        row = await con.fetchrow(
            """SELECT COUNT(*) FILTER (WHERE correct) AS correct,
                      COUNT(*) FILTER (WHERE correct IS NOT NULL) AS total
               FROM event_predictions WHERE event_type=$1""", event_type)
    else:
        row = await con.fetchrow(
            """SELECT COUNT(*) FILTER (WHERE correct) AS correct,
                      COUNT(*) FILTER (WHERE correct IS NOT NULL) AS total
               FROM event_predictions""")
    total = int(row["total"] or 0)
    correct = int(row["correct"] or 0)
    return {"correct": correct, "total": total,
            "accuracy": (correct / total) if total else 0.0}


# -- history ---------------------------------------------------------------
async def upsert_history(con, *, row: dict) -> None:
    await con.execute(
        """INSERT INTO event_history
           (event_type, event_time, symbol, surprise, first_1m_dir, first_1m_points,
            m5_dir, m5_points, m15_dir, m15_points, fakeout_points, spread_points, slippage_points)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)
           ON CONFLICT (event_type, event_time, symbol) DO UPDATE SET
             surprise=EXCLUDED.surprise, first_1m_dir=EXCLUDED.first_1m_dir,
             first_1m_points=EXCLUDED.first_1m_points, m5_dir=EXCLUDED.m5_dir,
             m5_points=EXCLUDED.m5_points, m15_dir=EXCLUDED.m15_dir,
             m15_points=EXCLUDED.m15_points, fakeout_points=EXCLUDED.fakeout_points,
             spread_points=EXCLUDED.spread_points, slippage_points=EXCLUDED.slippage_points""",
        row["event_type"], row["event_time"], row["symbol"], row.get("surprise"),
        row.get("first_1m_dir"), row.get("first_1m_points"), row.get("m5_dir"),
        row.get("m5_points"), row.get("m15_dir"), row.get("m15_points"),
        row.get("fakeout_points"), row.get("spread_points"), row.get("slippage_points"),
    )


async def history_rows(con, event_type: str, symbol: str, limit: int = 200) -> list[dict]:
    rows = await con.fetch(
        """SELECT surprise, first_1m_dir, first_1m_points, m5_dir, m5_points,
                  m15_dir, m15_points, fakeout_points, spread_points
           FROM event_history WHERE event_type=$1 AND symbol=$2
           ORDER BY event_time DESC LIMIT $3""", event_type, symbol, limit)
    return [dict(r) for r in rows]


async def recent_unscored(con, since, limit: int = 200) -> list[dict]:
    """Recent predictions still missing their post-event outcome.

    Used by the catch-up sweep so events that released while the bot was offline
    (or before a session connected) still get scored from historical candles.
    Returns one row per (event_key, symbol) that has ``correct IS NULL``.
    """
    rows = await con.fetch(
        """SELECT DISTINCT ON (event_key, symbol)
                  event_key, event_type, event_time, symbol, direction
           FROM event_predictions
           WHERE correct IS NULL AND event_time >= $1
           ORDER BY event_key, symbol, generated_at DESC
           LIMIT $2""", since, limit)
    return [dict(r) for r in rows]


async def record_reaction(con, *, event_key: str, event_type: str, event_time, symbol: str,
                          first_1m_dir: str, first_1m_points: float,
                          m5_dir=None, m5_points=None, m15_dir=None, m15_points=None,
                          fakeout_points=None, spread_points=None, surprise=None) -> None:
    """Store what the market actually did after ``event_time`` (the release).

    Two writes, both idempotent:
      * ``event_predictions`` gets the real first-candle direction + move, and
        ``correct`` is set ONLY for directional (BUY/SELL) calls whose direction
        matched that candle. NO_TRADE calls and flat candles stay NULL so they
        never inflate the accuracy score.
      * ``event_history`` gets the 1m/5m/15m reaction so future bias has samples.
    """
    await con.execute(
        """UPDATE event_predictions
              SET actual_direction=$3, actual_move_points=$4,
                  correct = CASE
                    WHEN direction IN ('BUY','SELL') AND $3 IN ('BUY','SELL')
                      THEN (direction = $3)
                    ELSE NULL END
            WHERE event_key=$1 AND symbol=$2 AND correct IS NULL""",
        event_key, symbol, first_1m_dir, float(first_1m_points))
    await upsert_history(con, row={
        "event_type": event_type, "event_time": event_time, "symbol": symbol,
        "surprise": surprise, "first_1m_dir": first_1m_dir,
        "first_1m_points": float(first_1m_points),
        "m5_dir": m5_dir, "m5_points": m5_points,
        "m15_dir": m15_dir, "m15_points": m15_points,
        "fakeout_points": fakeout_points, "spread_points": spread_points or 0.0,
    })


# -- plans -----------------------------------------------------------------
async def create_plan(con, *, plan: dict) -> int:
    row = await con.fetchrow(
        """INSERT INTO event_plans
           (event_key, event_type, event_time, symbol, direction, status, dry_run, target_zar,
            target_level, total_lots, required_margin, achieved_target_zar, plan_json,
            feasibility_json, expires_at)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13::jsonb,$14::jsonb,$15)
           RETURNING id""",
        plan["event_key"], plan["event_type"], plan["event_time"], plan["symbol"],
        plan["direction"], plan.get("status", "pending"), plan.get("dry_run", True),
        plan.get("target_zar", 15000.0), plan.get("target_level"), plan.get("total_lots"),
        plan.get("required_margin"), plan.get("achieved_target_zar"),
        json.dumps(plan.get("plan_json", {})), json.dumps(plan.get("feasibility_json", {})),
        plan.get("expires_at"),
    )
    return int(row["id"])


async def set_plan_status(con, plan_id: int, status: str, *, confirmed: bool = False) -> None:
    if confirmed:
        await con.execute(
            "UPDATE event_plans SET status=$2, confirmed_at=now() WHERE id=$1", plan_id, status)
    else:
        await con.execute("UPDATE event_plans SET status=$2 WHERE id=$1", plan_id, status)


async def plan_by_event_symbol(con, event_key: str, symbol: str) -> Optional[dict]:
    row = await con.fetchrow(
        "SELECT * FROM event_plans WHERE event_key=$1 AND symbol=$2 ORDER BY id DESC LIMIT 1",
        event_key, symbol)
    return dict(row) if row else None


async def plan_by_id(con, plan_id: int) -> Optional[dict]:
    row = await con.fetchrow("SELECT * FROM event_plans WHERE id=$1", plan_id)
    return dict(row) if row else None


async def plans_by_status(con, statuses: tuple[str, ...]) -> list[dict]:
    rows = await con.fetch(
        "SELECT * FROM event_plans WHERE status = ANY($1::text[]) ORDER BY event_time",
        list(statuses))
    return [dict(r) for r in rows]


# -- orders ----------------------------------------------------------------
async def create_order(con, *, order: dict) -> int:
    row = await con.fetchrow(
        """INSERT INTO event_orders
           (plan_id, event_key, symbol, broker_symbol, order_type, entry_price, lots,
            stop_loss, take_profit, magic, comment, status)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12) RETURNING id""",
        order["plan_id"], order["event_key"], order["symbol"], order["broker_symbol"],
        order["order_type"], order["entry_price"], order["lots"], order.get("stop_loss"),
        order.get("take_profit"), order["magic"], order.get("comment", ""),
        order.get("status", "pending"),
    )
    return int(row["id"])


async def set_order_broker_id(con, order_id: int, broker_order_id: str) -> None:
    await con.execute(
        "UPDATE event_orders SET broker_order_id=$2, updated_at=now() WHERE id=$1",
        order_id, broker_order_id)


async def set_order_status(con, order_id: int, status: str, *,
                           broker_position_id: Optional[str] = None,
                           filled_price: Optional[float] = None,
                           close_profit: Optional[float] = None,
                           error: Optional[str] = None) -> None:
    await con.execute(
        """UPDATE event_orders SET status=$2, broker_position_id=COALESCE($3, broker_position_id),
                  filled_price=COALESCE($4, filled_price), close_profit=COALESCE($5, close_profit),
                  error=COALESCE($6, error), updated_at=now() WHERE id=$1""",
        order_id, status, broker_position_id, filled_price, close_profit, error)


async def orders_for_plan(con, plan_id: int) -> list[dict]:
    rows = await con.fetch("SELECT * FROM event_orders WHERE plan_id=$1 ORDER BY id", plan_id)
    return [dict(r) for r in rows]


async def orders_by_status(con, statuses: tuple[str, ...]) -> list[dict]:
    rows = await con.fetch(
        "SELECT * FROM event_orders WHERE status = ANY($1::text[]) ORDER BY created_at",
        list(statuses))
    return [dict(r) for r in rows]

