# FX relative-strength selection

EUR/GBP is an analysis-only anchor. Its closed H4 21/50 SMA stack determines
whether EUR is stronger or weaker than GBP; a neutral or unavailable anchor
blocks both USD-pair entries.

During 08:00-12:00 New York local time (DST-aware), the bot evaluates configured
EUR/USD and GBP/USD charts. A bullish EUR/GBP bias permits EUR/USD longs or
GBP/USD shorts; a bearish bias permits EUR/USD shorts or GBP/USD longs. Each
candidate must agree with its own H4 21/50 SMA macro stack and form a structure
break, low-volume pullback to the SMA zone or broken level, and directional
engulfing/rejection confirmation on M15 or H1. If both qualify, only the higher
scoring available pair is selected for a new entry.

The bot does not currently consume a separate DXY feed. It uses EUR/GBP
relative strength and the H4 trend of each USD pair to rank candidates. If
broker candles do not contain tick volume, the low-volume filter fails closed
and the pair is not traded.
