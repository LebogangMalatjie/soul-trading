CREATE TABLE IF NOT EXISTS symbol_controls (
    symbol TEXT PRIMARY KEY,
    enabled BOOLEAN NOT NULL,
    mode TEXT NOT NULL CHECK (mode IN ('active', 'manage_only', 'off')),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by TEXT NOT NULL
);

INSERT INTO symbol_controls (symbol, enabled, mode, updated_by)
VALUES
    ('XAUUSD', TRUE, 'active', 'migration'),
    ('XAGUSD', TRUE, 'active', 'migration'),
    ('US30', TRUE, 'active', 'migration'),
    ('BTCUSD', TRUE, 'active', 'migration'),
    ('EURUSD', FALSE, 'off', 'migration'),
    ('USDJPY', FALSE, 'off', 'migration'),
    ('GBPUSD', FALSE, 'off', 'migration'),
    ('USDCHF', FALSE, 'off', 'migration'),
    ('AUDUSD', FALSE, 'off', 'migration'),
    ('USDCAD', FALSE, 'off', 'migration'),
    ('NZDUSD', FALSE, 'off', 'migration'),
    ('EURGBP', FALSE, 'off', 'migration'),
    ('EURJPY', FALSE, 'off', 'migration'),
    ('GBPJPY', FALSE, 'off', 'migration'),
    ('US100', FALSE, 'off', 'migration'),
    ('US500', FALSE, 'off', 'migration'),
    ('GER40', FALSE, 'off', 'migration'),
    ('USOIL', FALSE, 'off', 'migration'),
    ('ETHUSD', FALSE, 'off', 'migration')
ON CONFLICT (symbol) DO NOTHING;
