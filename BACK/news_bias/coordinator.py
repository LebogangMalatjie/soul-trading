"""NewsBiasEngine coordinator: wires the pure modules to broker + DB + scheduler.

Owns the per-event lifecycle but performs NO work unless ``config.enabled`` is
True, and everything stays dry-run until that flag is on. Decoupled from
TradingEngine: the engine constructs one and hooks its jobs into the shared
APScheduler. Nothing here places an order without an explicit confirm().
"""
from __future__ import annotations

from datetime import datetime, timezone

from . import store
from .bias import build_bias
from .config import BiasEngineConfig, EVENT_SYMBOL_MAP
from .gather import gather_context
from .history import _percentile, compute_stats
from .plan import BrokerFacts, build_plan
from .scheduler import build_schedule
from .sources import CalendarEvent, CalendarSource, NewsSource


class NewsBiasEngine:
    def __init__(self, *, config: BiasEngineConfig, calendar: CalendarSource,
                 news: NewsSource, db, get_session, is_auto_trading, note, log=None):
        self.config = config
        self.calendar = calendar
        self.news = news
        self.db = db                      # engine.Database (has .pool)
        self._get_session = get_session   # () -> UserSession | None
        self._is_auto_trading = is_auto_trading
        self._note = note                 # (level, text, symbol) -> None
        self._log = log
        self._plans: dict[str, dict] = {}          # event_key -> {symbol: plan dict}
        self._confirmed: set[tuple[str, str]] = set()
        self._skipped: set[tuple[str, str]] = set()

    def _logf(self, msg, *args):
        if self._log:
            try:
                self._log(msg, *args)
            except Exception:  # noqa: BLE001
                pass

    async def upcoming_events(self, now: datetime | None = None) -> list[CalendarEvent]:
        now = now or datetime.now(timezone.utc)
        try:
            return await self.calendar.high_impact_events(now)
        except Exception:  # noqa: BLE001
            return []

    async def process_event(self, ev: CalendarEvent) -> None:
        """Gather news, build per-symbol bias, and build (not place) the plan."""
        if not self.config.enabled:
            return
        symbols = EVENT_SYMBOL_MAP.get(ev.event_type, ())
        if not symbols:
            return
        gathered = await gather_context(
            ev, self.news, lookback_hours=self.config.context_lookback_hours)
        session = self._get_session()
        con = None
        acquire = None
        if self.db and self.db.pool:
            acquire = await self.db.pool.acquire()
            con = acquire
        try:
            if con is not None:
                for item in gathered.items:
                    await store.save_news_item(con, event_key=ev.key, item={
                        "title": item.title, "source": item.source, "url": item.url,
                        "published_at": item.published_at, "summary": item.summary,
                    })
            for symbol in symbols:
                try:
                    await self._bias_one(ev, symbol, gathered, con, session)
                except Exception as exc:  # noqa: BLE001 - one symbol never blocks others
                    self._logf("news-bias bias failed %s %s: %r", ev.key, symbol, exc)
                    continue
        finally:
            if acquire is not None:
                await self.db.pool.release(acquire)

    async def _bias_one(self, ev, symbol, gathered, con, session) -> None:
        stats_rows = []
        if con is not None:
            stats_rows = await store.history_rows(con, ev.event_type, symbol)
        stats = compute_stats(stats_rows)
        news_score = gathered.per_symbol_score.get(symbol, 0.0)
        result = build_bias(
            event_key=ev.key, event_type=ev.event_type, symbol=symbol,
            news_score=news_score,
            news_reasons=gathered.per_symbol_reasons.get(symbol, []),
            news_sources=gathered.per_symbol_sources.get(symbol, []),
            stats=stats,
            min_probability_pct=self.config.min_probability_pct,
            min_history_sample=self.config.min_history_sample,
            news_available=gathered.available,
        )
        if con is not None:
            await store.save_prediction(con, pred={
                "event_key": ev.key, "event_type": ev.event_type, "event_time": ev.time,
                "symbol": symbol, "direction": result.direction,
                "probability_pct": result.probability_pct, "news_score": result.news_score,
                "reasons": result.reasons, "sources": result.sources,
                "historical_support": result.historical_support, "formula": result.formula,
            })
        self._note("event", f"{ev.event_type} {symbol}: {result.direction} "
                            f"{result.probability_pct:.0f}%", symbol)
        if result.direction in ("BUY", "SELL") and session is not None:
            await self._build_plan_for(ev, symbol, result.direction, session, con)

    async def _build_plan_for(self, ev, symbol, direction, session, con) -> None:
        cfg_sym = self.config.for_symbol(symbol)
        broker = session.broker
        broker_symbol = session.config.broker_symbol(symbol)
        try:
            quote = await broker.price(broker_symbol)
            spec = await broker.symbol_spec(broker_symbol)
            stops_level = await broker.symbol_stops_level(broker_symbol)
        except Exception as exc:  # noqa: BLE001
            self._logf("news-bias plan inputs unavailable %s %s: %r", symbol, ev.key, exc)
            return
        reference = (quote.bid + quote.ask) / 2 if quote else 0.0
        point = spec.point if spec.point > 0 else 10 ** (-spec.digits)

        atr14 = atr5 = point * 20
        try:
            from engine import Timeframe, atr as engine_atr, closed_only
            c5 = closed_only(await session.candles(symbol, Timeframe.M5, force=True),
                             Timeframe.M5, datetime.now(timezone.utc))
            if c5:
                atr14 = atr5 = engine_atr(c5) or atr14
        except Exception:  # noqa: BLE001
            pass

        facts = BrokerFacts(
            point=point, tick_size=spec.tick_size or point, tick_value=spec.tick_value,
            contract_size=spec.contract_size, min_lot=spec.min_lot, max_lot=spec.max_lot,
            lot_step=spec.lot_step, stops_level_points=float(stops_level), max_orders=0,
        )
        history = (await store.history_rows(con, ev.event_type, symbol)) if con is not None else []
        spreads = [abs(float(r["spread_points"])) for r in history if r.get("spread_points")]
        fakes = [abs(float(r["fakeout_points"])) for r in history if r.get("fakeout_points")]
        moves = [abs(float(r["first_1m_points"])) for r in history if r.get("first_1m_points")]
        avg_spread = sum(spreads) / len(spreads) if spreads else 0.0
        fakeout = sum(fakes) / len(fakes) if fakes else 0.0
        p80 = _percentile(moves, 80.0)
        avg_move = sum(moves) / len(moves) if moves else 0.0

        try:
            margin_per_lot = await broker.symbol_margin(symbol, direction, facts.min_lot, reference)
        except Exception:  # noqa: BLE001
            margin_per_lot = 0.0
        try:
            info = await broker.account_info()
            free_margin = info.free_margin
        except Exception:  # noqa: BLE001
            free_margin = 0.0
        zar_rate = await self._zar_rate(broker)

        plan = build_plan(
            symbol=symbol, direction=direction, reference_price=reference, facts=facts,
            cfg=cfg_sym, engine_cfg=self.config, atr14_5m=atr14, atr5_5m=atr5,
            avg_release_spread=avg_spread, fakeout_points=fakeout, p80_move_points=p80,
            avg_move_points=avg_move, free_margin=free_margin, margin_per_lot=margin_per_lot,
            zar_rate=zar_rate,
        )
        schedule = build_schedule(
            ev.time, regen_offsets=self.config.regen_offsets,
            lock_offset_minutes=self.config.lock_offset_minutes,
            place_offset_minutes=self.config.place_offset_minutes,
            confirm_cutoff_seconds=self.config.confirm_cutoff_seconds,
            pending_expiry_minutes=cfg_sym.pending_expiry_minutes,
        )
        plan_dict = {
            "event_key": ev.key, "event_type": ev.event_type, "event_time": ev.time,
            "symbol": symbol, "direction": direction, "status": "pending",
            "dry_run": self.config.dry_run, "target_zar": self.config.target_zar,
            "target_level": plan.target_level, "total_lots": plan.total_lots,
            "required_margin": plan.required_margin,
            "achieved_target_zar": plan.achieved_target_zar,
            "plan_json": {"orders": [
                {"order_type": o.order_type, "entry_price": o.entry_price, "lots": o.lots,
                 "stop_loss": o.stop_loss, "broker_symbol": broker_symbol,
                 "profit_at_target_zar": o.profit_at_target_zar,
                 "distance_points": o.distance_points}
                for o in plan.orders
            ]},
            "feasibility_json": {
                "required_move_points": plan.required_move_points,
                "required_move_pct_of_avg": plan.required_move_pct_of_avg,
                "required_move_pct_of_p80": plan.required_move_pct_of_p80,
                "orders_needed": plan.orders_needed,
                "worst_case_loss_zar": plan.worst_case_loss_zar,
                "above_p80": plan.above_p80, "feasible": plan.feasible, "notes": plan.notes,
                "spike_buffer_points": plan.spike_buffer_points, "reference_price": reference,
            },
            "expires_at": schedule.expire_time,
        }
        if con is not None:
            plan_dict["id"] = await store.create_plan(con, plan=plan_dict)
        self._plans.setdefault(ev.key, {})[symbol] = plan_dict
        self._note("event", f"{ev.event_type} {symbol} plan: {plan.orders_needed} orders, "
                            f"~R{plan.achieved_target_zar:,.0f} target", symbol)

    async def _zar_rate(self, broker) -> float:
        try:
            price = await broker.price("USDZAR")
            if price and (price.bid or price.ask):
                return float((price.bid + price.ask) / 2)
        except Exception:  # noqa: BLE001
            pass
        return self.config.zar_fallback_rate

    # -- confirm / skip / placement (called by the API endpoints) ----------
    def plan_for(self, event_key: str, symbol: str) -> dict | None:
        return self._plans.get(event_key, {}).get(symbol)

    def all_plans(self) -> dict[str, dict]:
        return self._plans

    async def confirm(self, event_key: str, symbol: str) -> str:
        """Arm a plan and place its orders now (or at T-5 by the scheduler)."""
        plan = self.plan_for(event_key, symbol)
        if not plan:
            return "no_plan"
        if not self._is_auto_trading():
            return "kill_switch"
        self._confirmed.add((event_key, symbol))
        self._skipped.discard((event_key, symbol))
        session = self._get_session()
        if session is None:
            return "no_session"
        from . import executor
        con = await self.db.pool.acquire() if self.db and self.db.pool else None
        try:
            result = await executor.place_plan(
                session.broker, con, plan, engine_cfg=self.config,
                auto_trading_enabled=self._is_auto_trading)
        finally:
            if con is not None:
                await self.db.pool.release(con)
        self._note("event", f"{symbol} confirmed: placed {result.placed}, "
                            f"failed {result.failed}", symbol)
        return "placed" if result.placed else ("dry_run" if result.skipped_kill_switch is False
                                               and self.config.dry_run else "nothing")

    async def skip(self, event_key: str, symbol: str) -> str:
        plan = self.plan_for(event_key, symbol)
        self._skipped.add((event_key, symbol))
        self._confirmed.discard((event_key, symbol))
        if plan and self.db and self.db.pool:
            con = await self.db.pool.acquire()
            try:
                await store.set_plan_status(con, plan["id"], "skipped")
            finally:
                await self.db.pool.release(con)
        self._note("event", f"{symbol} skipped by user.", symbol)
        return "skipped"

    def is_confirmed(self, event_key: str, symbol: str) -> bool:
        return (event_key, symbol) in self._confirmed

    def is_skipped(self, event_key: str, symbol: str) -> bool:
        return (event_key, symbol) in self._skipped

    async def monitor_all(self) -> None:
        """Basket take-profit + expiry sweep; called from the engine tick."""
        if not self.config.enabled or not self._is_auto_trading():
            return
        session = self._get_session()
        if session is None:
            return
        from . import executor
        now = datetime.now(timezone.utc)
        zar_rate = await self._zar_rate(session.broker)
        for event_key, by_symbol in list(self._plans.items()):
            for symbol, plan in list(by_symbol.items()):
                if (event_key, symbol) in self._skipped:
                    continue
                if plan.get("status") not in ("executed", "confirmed"):
                    continue
                try:
                    expire_at = plan.get("expires_at")
                    if expire_at is not None and _as_dt(expire_at) and _as_dt(expire_at) < now:
                        await executor.expire_plan(
                            session.broker, None, plan, engine_cfg=self.config,
                            auto_trading_enabled=self._is_auto_trading)
                        continue
                    if self.db and self.db.pool:
                        con = await self.db.pool.acquire()
                        try:
                            await executor.monitor_basket(
                                session.broker, con, plan, engine_cfg=self.config,
                                auto_trading_enabled=self._is_auto_trading, zar_rate=zar_rate)
                        finally:
                            await self.db.pool.release(con)
                    else:
                        await executor.monitor_basket(
                            session.broker, _NullConn(), plan, engine_cfg=self.config,
                            auto_trading_enabled=self._is_auto_trading, zar_rate=zar_rate)
                except Exception as exc:  # noqa: BLE001
                    self._logf("news-bias monitor failed %s %s: %r", event_key, symbol, exc)
                    continue


class _NullConn:
    """Stand-in when the DB is offline; store calls that need it are guarded."""

    async def execute(self, *a, **k):
        return None

    async def fetch(self, *a, **k):
        return []

    async def fetchrow(self, *a, **k):
        return None


def _as_dt(value):
    from datetime import datetime as _dt
    if isinstance(value, _dt):
        return value
    return None


# -- module-level singleton used by the engine ----------------------------
_ENGINE: NewsBiasEngine | None = None


def get_engine() -> NewsBiasEngine | None:
    return _ENGINE


def set_engine(engine: NewsBiasEngine | None) -> None:
    global _ENGINE
    _ENGINE = engine



