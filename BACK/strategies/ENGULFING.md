# Engulfing strategy

The strategy is off by default and paper-only when enabled. Configure it in the
dashboard or through `StrategyConfig.engulfing_enabled` and
`StrategyConfig.engulfing_paper_mode`. Live entries are sent through the existing
broker order path and use the `ENGULF_<timeframe>` order comment.

`DEFAULT_CONFIG` in `engulfing.py` contains the strategy-wide settings and per-symbol
overrides. Starting points are:

| Symbol | Minimum body / ATR | Maximum spread (points) |
| --- | ---: | ---: |
| XAUUSD | 0.55 | 80 |
| XAGUSD | 0.60 | 100 |
| BTCUSD | 0.70 | 2500 |
| US30 | 0.60 | 100 |

XAGUSD starts with a 12-candle swing lookback and 0.25 ATR stop buffer; BTCUSD
uses a 1.3 engulf ratio and four-candle cooldown; US30 also uses a 12-candle
swing lookback. Adjust spread limits to the broker's quoted point size.

The strategy scans 1h and 30m signals. A 1h signal requires matching 4h trend
confirmation, and a 30m signal requires matching 1h trend confirmation. Other
defaults: ATR period 14; minimum engulf body ratio 1.2; EMA 50; swing lookback
10 with a 0.25 ATR proximity tolerance; ATR stop buffer 0.2; maximum stop 2.5
ATR; reward/risk 2:1; 1% equity risk; and a three-candle same-symbol/timeframe
cooldown. Entry is market at the next candle open. The minimum-body, strength,
trend, location, higher-timeframe, session, news, spread, and cooldown gates
each have a `use_*_filter` toggle in `DEFAULT_CONFIG`. Tune spread points to
the broker's `point` definition.

Run unit tests from `BACK` with `python -m unittest discover -s tests`. The MT5
backtest script accepts symbol and timeframe, for example
`python scripts/backtest_engulfing.py XAUUSD 5m --spread-points 2 --slippage-points 1`.
