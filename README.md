# Soul Trading symbol controls

## Adding a symbol

1. Add its name to `Symbol` in `BACK/schemas.py`.
2. Add a disabled-by-default `SymbolConfig` entry in `BACK/symbols_config.py`, including its broker name, UTC sessions, timeframes, spread/risk limits, position limit, and exit mode.
3. Implement the `StrategyPlugin` contract in `BACK/strategies/` and register the instance in `BACK/strategies/__init__.py`.
4. Add a disabled row for it to `BACK/migrations/001_symbol_controls.sql`. Use broker symbol mapping in the user's `StrategyConfig` when the broker uses a suffix.
5. Add focused tests for its signal conditions, symbol-control behavior, and any required correlation/event guards.

New registry entries default to `paper_mode=True` and controls default to `off`. Keep live order submission behind the existing engine order path and safety gates.

## Symbol toggles

The authenticated `GET /api/v1/symbols` endpoint reports each symbol's control state, broker name, strategy, open positions, and today's realized plus floating P&L. `POST /api/v1/symbols/{symbol}/toggle` takes `enabled`, `mode` (`active`, `manage_only`, or `off`), and `close_open_positions`.

`active` permits entries when the global kill switch and other risk gates allow them. `manage_only` blocks entries while leaving open positions in the engine's normal position-processing loop. `off` also blocks entries; open positions remain untouched unless `close_open_positions` is true. Four losing closed trades for a symbol in one UTC day automatically switch it to `manage_only`; that automatic cooldown clears at the next UTC day. The global emergency kill switch overrides every symbol.

Apply the additive SQL in `BACK/migrations/001_symbol_controls.sql` to Supabase before deploying. The service also creates the table idempotently at startup.

## Rollback

To stop a symbol immediately, switch it to `off` (or `manage_only` to explicitly keep managing positions); choose close-open-positions only when closing them is intended. To roll back code, deploy the prior known-good application revision. The migration is additive; leave `symbol_controls` in place during code rollback so the saved controls remain available if the feature is redeployed. Do not drop the table as part of routine rollback.

## News Event Bias Engine

A confirm-gated engine around high-impact economic events (NFP, CPI, FOMC, PPI, GDP, retail sales, jobless claims, central-bank speeches, geopolitical headlines). It gathers news context, produces a per-symbol bias with a documented probability, checks it against historical first-candle reactions, builds an order plan sized to a combined R15,000 (configurable) basket target, and **places nothing until you click CONFIRM** in the dashboard. The global emergency kill switch overrides everything here.

It is purely additive and does not touch the existing technical strategies, trailing stops, the legacy news front-running path, notifications, or the kill switch. Telegram/WhatsApp delivery is intentionally deferred.

### Enable / configure (environment)
- `NEWS_BIAS_ENABLED` — master switch. Default `false`. Set to `1`/`true` to arm the engine.
- `NEWS_BIAS_DRY_RUN` — default `true`. While true, plans are logged but **no orders are placed**. Set to `0`/`false` only when you are ready to trade the basket live.
- `NEWS_BIAS_TARGET_ZAR` — the combined basket profit target in ZAR. Default `15000`.
- Local MT5 pending orders require `BROKER=mt5` (the MetaApi path does not implement pending orders).

Editable defaults live in `BACK/news_bias/config.py`: the event→symbol map, per-symbol spike-buffer params (`atr_mult`, `spread_mult`, `stops_level_margin_points`, `fakeout_mult`, `ladder_spacing_atr5`), stop-loss and expiry/fallback, regeneration offsets (T-30/T-15/T-6), the T-5 lock, the T-60s confirm cutoff, and the minimum probability/history thresholds.

### How a trade happens
1. The scheduler regenerates the bias at T-30/T-15/T-6 and locks it at T-5.
2. At lock, an order plan is built per symbol: BUY bias → BUY STOPs above price; SELL bias → SELL STOPs below. The first order sits at least the spike buffer away (max of ATR, prior-release spread, broker stops level, and the typical fake-out). Lot sizes are solved so the filled basket reaches the ZAR target at the target level, rounded to the lot step, capped at max volume, and scaled down (with a note) if free margin is short.
3. From T-6m the dashboard card shows a **flashing green CONFIRM** and a crimson SKIP. CONFIRM arms and places the ladder (immediately if you confirm after T-5, before the event). SKIP, or no action by T-60s, places nothing.
4. A per-tick monitor closes the whole basket and cancels unfilled rungs once combined floating profit reaches the target; unfilled orders expire after the configured window; the kill switch stops and closes everything.

### Endpoints (reuse the existing bearer auth)
- `GET /api/v1/news-events/upcoming` — next events with per-symbol bias, plan, and feasibility.
- `GET /api/v1/news-events/{event_key}/plan?symbol=X` — the full plan for one event/symbol.
- `POST /api/v1/news-events/{event_key}/confirm?symbol=X` — arm + place (blocked while the kill switch is active).
- `POST /api/v1/news-events/{event_key}/skip?symbol=X` — skip.
- `GET /api/v1/news-events/history` — running prediction accuracy for calibration.

### Data sources
Swappable adapters in `BACK/news_bias/sources.py`: `ForexFactoryCalendar` (free JSON calendar) and `GoogleNewsSource` (free RSS), both behind a common interface with an in-memory TTL cache. Swap in another provider by implementing `CalendarSource`/`NewsSource` — no engine changes needed.

### Tests
`BACK/tests/test_news_bias.py` covers the bias formula and NO_TRADE gating, historical hit-rate/percentile math, BUY/SELL stop placement, the four-part minimum-distance buffer, R15,000 sizing (including lot-step rounding, max-volume capping, and the margin-shortfall case), scheduler timing, and event magic numbers. Run with `python -m unittest discover -s tests` from `BACK/`.

### Rollback
Leave `NEWS_BIAS_ENABLED` unset/`false` (the engine does nothing and the API returns 503). The `002_news_bias.sql` tables are additive; leave them in place during a code rollback. Do not drop them as part of routine rollback.
