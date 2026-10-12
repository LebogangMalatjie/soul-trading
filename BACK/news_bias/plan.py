"""Order-plan builder around the R15,000 target (Part 4).

Pure functions (no I/O) so the sizing math is unit-tested exactly. The engine
supplies broker facts (SymbolSpec-like), ATR, spreads, fake-out size, stops
level, free margin and the USD->ZAR rate.

Money model (documented):
  money_per_lot_per_point = (point / tick_size) * tick_value   [profit ccy per lot per point]
  total_target_zar = sum_i lots_i * (T - entry_i)/point * money_per_lot_per_point * zar_rate
  We solve for equal ``lots`` per order so the basket reaches ``target_zar`` when
  price reaches ``T`` and every ladder order has filled.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .config import SymbolBiasConfig


@dataclass(slots=True)
class BrokerFacts:
    point: float
    tick_size: float
    tick_value: float           # profit currency per tick per 1.0 lot
    contract_size: float
    min_lot: float
    max_lot: float
    lot_step: float
    stops_level_points: float   # broker SYMBOL_TRADE_STOPS_LEVEL in points
    max_orders: int             # broker max pending orders (fallback if <=0)


@dataclass(slots=True)
class PlanOrder:
    index: int
    order_type: str             # BUY_STOP | SELL_STOP
    entry_price: float
    lots: float
    stop_loss: float
    distance_points: float
    profit_at_target_zar: float


@dataclass(slots=True)
class EventPlan:
    symbol: str
    direction: str              # BUY | SELL
    reference_price: float
    spike_buffer_points: float
    first_entry: float
    target_level: float
    orders: list[PlanOrder] = field(default_factory=list)
    total_lots: float = 0.0
    achieved_target_zar: float = 0.0
    required_margin: float = 0.0
    required_move_points: float = 0.0
    required_move_pct_of_avg: float | None = None
    required_move_pct_of_p80: float | None = None
    orders_needed: int = 0
    worst_case_loss_zar: float = 0.0
    above_p80: bool = False
    feasible: bool = True
    notes: list[str] = field(default_factory=list)


def _round_to_step(value: float, step: float) -> float:
    if step <= 0:
        return value
    decimals = max(0, min(8, -int(math.floor(math.log10(step)))))
    return round(math.floor(value / step + 1e-9) * step, decimals)


def _money_per_lot_per_point(facts: BrokerFacts) -> float:
    """Profit currency earned per 1.0 lot per 1 point of favourable move."""
    if facts.tick_size <= 0:
        return 0.0
    return (facts.point / facts.tick_size) * facts.tick_value


def facts_digits(facts: BrokerFacts) -> int:
    if facts.point <= 0:
        return 2
    return max(0, -int(math.floor(math.log10(facts.point))))


def compute_spike_buffer(
    cfg: SymbolBiasConfig,
    atr14_5m: float,
    avg_release_spread: float,
    stops_level_points: float,
    fakeout_points: float,
    point: float,
) -> float:
    """Minimum entry distance in PRICE units = max of the four components."""
    atr_component = cfg.atr_mult * atr14_5m
    spread_component = cfg.spread_mult * avg_release_spread * point
    stops_component = (stops_level_points + cfg.stops_level_margin_points) * point
    fakeout_component = cfg.fakeout_mult * fakeout_points * point
    return max(atr_component, spread_component, stops_component, fakeout_component)


def build_plan(
    *,
    symbol: str,
    direction: str,                 # BUY | SELL
    reference_price: float,         # live price at T-5m
    facts: BrokerFacts,
    cfg: SymbolBiasConfig,
    engine_cfg,                     # BiasEngineConfig (for target_zar)
    atr14_5m: float,
    atr5_5m: float,
    avg_release_spread: float,
    fakeout_points: float,
    p80_move_points: float,
    avg_move_points: float,
    free_margin: float,
    margin_per_lot: float,
    zar_rate: float,
    fixed_target_points: float | None = None,
) -> EventPlan:
    point = facts.point if facts.point > 0 else 10 ** (-2)
    digits = facts_digits(facts)
    sign = 1.0 if direction == "BUY" else -1.0

    buffer_price = compute_spike_buffer(
        cfg, atr14_5m, avg_release_spread, facts.stops_level_points, fakeout_points, point
    )
    buffer_points = buffer_price / point if point else 0.0

    first_entry = reference_price + sign * buffer_price
    order_type = "BUY_STOP" if direction == "BUY" else "SELL_STOP"

    if fixed_target_points is not None:
        target_level = first_entry + sign * fixed_target_points * point
    else:
        target_level = first_entry + sign * p80_move_points * point

    spacing_price = cfg.ladder_spacing_atr5 * atr5_5m
    max_orders = facts.max_orders if facts.max_orders and facts.max_orders > 0 else 10
    rung_move = spacing_price if spacing_price > 0 else buffer_price
    reach = abs(target_level - first_entry)
    n_orders = max(1, min(max_orders, (int(reach / rung_move) + 1) if rung_move > 0 else 1))

    money_per_lot_per_point = _money_per_lot_per_point(facts)

    entries = [first_entry + sign * i * spacing_price for i in range(n_orders)]

    sl_distance_price = (cfg.sl_points * point) if cfg.sl_points is not None \
        else (cfg.sl_atr_mult * atr14_5m)
    sl_distance_price = max(sl_distance_price, buffer_price)

    plan = EventPlan(
        symbol=symbol, direction=direction, reference_price=reference_price,
        spike_buffer_points=buffer_points, first_entry=first_entry, target_level=target_level,
    )
    if money_per_lot_per_point <= 0 or zar_rate <= 0:
        plan.feasible = False
        plan.notes.append("Cannot size: broker tick value or ZAR rate invalid.")
        return plan

    favourable_points_total = sum(abs(target_level - e) / point for e in entries)
    if favourable_points_total <= 0:
        plan.feasible = False
        plan.notes.append("Cannot size: target level is not beyond the entries.")
        return plan

    raw_lots = engine_cfg.target_zar / (favourable_points_total * money_per_lot_per_point * zar_rate)
    lots = _round_to_step(raw_lots, facts.lot_step)

    if lots > facts.max_lot:
        lots = _round_to_step(facts.max_lot, facts.lot_step)
        plan.notes.append(f"Per-order lots capped at broker max {facts.max_lot}.")
    if 0 < lots < facts.min_lot:
        lots = _round_to_step(facts.min_lot, facts.lot_step)
        plan.notes.append(f"Raised to broker minimum lot {facts.min_lot}.")

    total_margin = lots * n_orders * margin_per_lot
    if margin_per_lot > 0 and free_margin > 0 and total_margin > free_margin:
        affordable = _round_to_step(free_margin / (n_orders * margin_per_lot), facts.lot_step)
        if affordable < facts.min_lot:
            plan.feasible = False
            plan.notes.append(
                f"Insufficient free margin for the minimum ladder "
                f"(need {total_margin:.2f}, have {free_margin:.2f})."
            )
            lots = facts.min_lot
        else:
            lots = affordable
            plan.notes.append("Scaled down to fit free margin; target partially reached.")

    worst_loss = 0.0
    achieved = 0.0
    loss_points = sl_distance_price / point
    for i, entry in enumerate(entries):
        sl = entry - sign * sl_distance_price
        move_points = abs(target_level - entry) / point
        profit_zar = lots * move_points * money_per_lot_per_point * zar_rate
        achieved += profit_zar
        worst_loss += lots * loss_points * money_per_lot_per_point * zar_rate
        plan.orders.append(PlanOrder(
            index=i, order_type=order_type, entry_price=round(entry, digits),
            lots=lots, stop_loss=round(sl, digits),
            distance_points=round(abs(entry - reference_price) / point, 1),
            profit_at_target_zar=round(profit_zar, 2),
        ))

    plan.total_lots = round(lots * n_orders, 2)
    plan.achieved_target_zar = round(achieved, 2)
    plan.required_margin = round(lots * n_orders * margin_per_lot, 2)
    plan.orders_needed = n_orders
    plan.worst_case_loss_zar = round(worst_loss, 2)

    required_move = abs(target_level - reference_price) / point
    plan.required_move_points = round(required_move, 1)
    if avg_move_points > 0:
        plan.required_move_pct_of_avg = round(required_move / avg_move_points, 3)
    if p80_move_points > 0:
        plan.required_move_pct_of_p80 = round(required_move / p80_move_points, 3)
        plan.above_p80 = required_move > p80_move_points
    if plan.above_p80:
        plan.notes.append("Required move exceeds the historical p80 move for this event/symbol.")
    return plan

