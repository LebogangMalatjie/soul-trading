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
