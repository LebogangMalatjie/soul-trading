-- News Event Bias Engine (additive). Safe to run alongside 001.
-- Applied idempotently at startup (see engine SCHEMA_SQL) and via this file.

-- Raw context items gathered around an event (last 24-72h).
CREATE TABLE IF NOT EXISTS news_items (
    id BIGSERIAL PRIMARY KEY,
    event_key TEXT NOT NULL,              -- "<event_type>:<unix_ts>" matches EconEvent.key
    title TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT '',
    url TEXT NOT NULL DEFAULT '',
    published_at TIMESTAMPTZ,
    summary TEXT NOT NULL DEFAULT '',
    symbol_scores JSONB,                  -- {"XAUUSD": {"dir":"BUY","score":0.4}, ...}
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS news_items_event ON news_items (event_key, published_at DESC);

-- Per-event/symbol bias predictions (logged at T-30/T-15/T-6, locked at T-5).
CREATE TABLE IF NOT EXISTS event_predictions (
    id BIGSERIAL PRIMARY KEY,
    event_key TEXT NOT NULL,
    event_type TEXT NOT NULL,
    event_time TIMESTAMPTZ NOT NULL,
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL,              -- BUY | SELL | NO_TRADE
    probability_pct DOUBLE PRECISION NOT NULL DEFAULT 0,
    news_score DOUBLE PRECISION NOT NULL DEFAULT 0,
    reasons JSONB NOT NULL DEFAULT '[]'::jsonb,
    sources JSONB NOT NULL DEFAULT '[]'::jsonb,
    historical_support JSONB NOT NULL DEFAULT '{}'::jsonb,
    formula TEXT NOT NULL DEFAULT '',     -- human-readable probability formula + inputs
    generated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    locked BOOLEAN NOT NULL DEFAULT FALSE,
    actual_direction TEXT,                -- filled in after the event for calibration
    actual_move_points DOUBLE PRECISION,
    correct BOOLEAN
);
CREATE INDEX IF NOT EXISTS event_predictions_event ON event_predictions (event_key, symbol);
CREATE INDEX IF NOT EXISTS event_predictions_type ON event_predictions (event_type, event_time DESC);

-- Historical first-candle / 5m / 15m reactions per event type + symbol (backfilled from MT5 1m).
CREATE TABLE IF NOT EXISTS event_history (
    id BIGSERIAL PRIMARY KEY,
    event_type TEXT NOT NULL,
    event_time TIMESTAMPTZ NOT NULL,
    symbol TEXT NOT NULL,
    surprise DOUBLE PRECISION,            -- actual - forecast (signed)
    first_1m_dir TEXT,                    -- BUY | SELL | FLAT
    first_1m_points DOUBLE PRECISION,
    m5_dir TEXT,
    m5_points DOUBLE PRECISION,
    m15_dir TEXT,
    m15_points DOUBLE PRECISION,
    fakeout_points DOUBLE PRECISION,      -- opposite-direction spike in first minute
    spread_points DOUBLE PRECISION,       -- avg spread around release
    slippage_points DOUBLE PRECISION,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (event_type, event_time, symbol)
);
CREATE INDEX IF NOT EXISTS event_history_lookup ON event_history (event_type, symbol, event_time DESC);

-- The built order plan (created at T-5, executed only after CONFIRM).
CREATE TABLE IF NOT EXISTS event_plans (
    id BIGSERIAL PRIMARY KEY,
    event_key TEXT NOT NULL,
    event_type TEXT NOT NULL,
    event_time TIMESTAMPTZ NOT NULL,
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL,              -- BUY | SELL
    status TEXT NOT NULL DEFAULT 'pending',   -- pending | confirmed | skipped | expired | executed | done | cancelled
    dry_run BOOLEAN NOT NULL DEFAULT TRUE,
    target_zar DOUBLE PRECISION NOT NULL DEFAULT 15000,
    target_level DOUBLE PRECISION,
    total_lots DOUBLE PRECISION,
    required_margin DOUBLE PRECISION,
    achieved_target_zar DOUBLE PRECISION,
    plan_json JSONB NOT NULL DEFAULT '{}'::jsonb,   -- full ladder: levels, lots, sl, tp, distances
    feasibility_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    confirmed_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS event_plans_event ON event_plans (event_key, symbol);
CREATE INDEX IF NOT EXISTS event_plans_status ON event_plans (status, event_time DESC);

-- Individual orders belonging to a plan (pending + filled), tagged by magic/comment.
CREATE TABLE IF NOT EXISTS event_orders (
    id BIGSERIAL PRIMARY KEY,
    plan_id BIGINT NOT NULL REFERENCES event_plans(id) ON DELETE CASCADE,
    event_key TEXT NOT NULL,
    symbol TEXT NOT NULL,
    broker_symbol TEXT NOT NULL,
    order_type TEXT NOT NULL,             -- BUY_STOP | SELL_STOP
    entry_price DOUBLE PRECISION NOT NULL,
    lots DOUBLE PRECISION NOT NULL,
    stop_loss DOUBLE PRECISION,
    take_profit DOUBLE PRECISION,
    magic BIGINT NOT NULL,
    comment TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',   -- pending | filled | closed | cancelled | rejected | expired
    broker_order_id TEXT,
    broker_position_id TEXT,
    filled_price DOUBLE PRECISION,
    close_profit DOUBLE PRECISION,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS event_orders_plan ON event_orders (plan_id);
CREATE INDEX IF NOT EXISTS event_orders_status ON event_orders (status, created_at DESC);
