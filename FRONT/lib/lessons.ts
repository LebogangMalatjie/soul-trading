/* Strategy knowledge base: in-depth, per-symbol teaching content.
   Mirrors the real logic in BACK/strategies/*.py so the tutor never lies. */
export type Lesson = {
  name: string;
  edge: string;
  watch: string[];
  entry: string;
  exit: string;
  session: string;
  risk: string;
};

export const LESSONS: Record<string, Lesson> = {
  EURUSD: {
    name: "Asian fade · Overlap breakout · Liquidity sweep",
    edge: "Trades the three personalities of EURUSD: quiet-Asia mean reversion, London/NY-overlap breakouts, and stop-hunt reversals.",
    watch: [
      "Asian range = high/low of the 00:00-06:00 UTC candles.",
      "At 06:00-08:00 UTC, price hugging the Asian edge (within 0.15× ATR).",
      "In the 13:00-17:00 UTC overlap, a close beyond the prior 20-bar range with a body > 0.35× ATR.",
      "A wick that pokes above/below the last 20-bar high/low then closes back inside (the sweep).",
    ],
    entry: "Fade at the Asian edge; take breakouts in the overlap; take the reversal when the sweep fails to hold.",
    exit: "Stop at 1.5-1.8× ATR depending on the mode. Profit-percentage ladder trails winners.",
    session: "Asian 00:00-08:00 UTC · London/NY overlap 13:00-17:00 UTC",
    risk: "Sweeps are frequent in Asia; the 0.15× ATR buffer filters the noise.",
  },
  USDJPY: {
    name: "EMA trend pullback",
    edge: "Rides JPY trends but only buys/sells the dip, so it avoids chasing extended moves.",
    watch: [
      "EMA20 vs EMA50 sets the trend (fast above slow = up).",
      "Price pulls back to tag the EMA20, then reclaims it on a close in the trend direction.",
      "The final candle must be bullish for BUY / bearish for SELL.",
    ],
    entry: "BUY when EMA20>EMA50 and price taps EMA20 then closes back above it. SELL is the mirror.",
    exit: "Stop 1.8× ATR. Profit-ladder trailing.",
    session: "Asian 00:00-08:00 UTC · Tokyo/NY 07:00-16:00 UTC",
    risk: "Whipsaws when the two EMAs are flat/entangled - the trend filter skips those.",
  },
  GBPUSD: {
    name: "London-open range breakout",
    edge: "London open injects real flow; breaking the first London hour tends to continue.",
    watch: [
      "Opening range = the first London hour, 08:00-09:00 London (DST-aware).",
      "A close beyond that range's high or low with a body > 0.3× ATR.",
    ],
    entry: "BUY on a close above the opening-range high, SELL below the low, only after 09:00 London.",
    exit: "Stop 1.8× ATR. Profit-ladder trailing.",
    session: "London 07:00-12:00 UTC",
    risk: "False breaks happen; the momentum-body filter (0.3× ATR) reduces them.",
  },
  USDCHF: {
    name: "Bollinger/RSI mean reversion",
    edge: "Franc ranges in calm conditions; overextended band tags with RSI confirmation snap back.",
    watch: [
      "Close below the lower Bollinger band with RSI < 30 (BUY) or above the upper with RSI > 70 (SELL).",
      "Trend guard: the 50-EMA slope must be gentle (under 1.0× ATR over 5 bars).",
    ],
    entry: "BUY the lower-band oversold tag; SELL the upper-band overbought tag - only when not trending hard.",
    exit: "Fixed target back toward the mean (the 20-band midline). Stop 1.4× ATR.",
    session: "London 07:00-16:00 UTC",
    risk: "Skipped entirely in strong trends - that's intentional, reversion loses there.",
  },
  AUDUSD: {
    name: "Asian range + risk filter",
    edge: "Fades the AUD Asian range but only when risk sentiment agrees, adding a macro layer.",
    watch: [
      "Asian range = high/low of the 00:00-04:00 UTC candles.",
      "Price at the range edge (within 0.15× ATR) in the 04:00-08:00 UTC window.",
      "Risk sentiment must be non-zero: risk-on favours BUY at the low; risk-off favours SELL at the high.",
    ],
    entry: "BUY at the Asian low only if risk-on; SELL at the Asian high only if risk-off.",
    exit: "Stop 1.5× ATR. Profit-ladder trailing.",
    session: "Asian 00:00-08:00 UTC",
    risk: "If risk sentiment is 0 (unclear), it stands down rather than guess.",
  },
  USDCAD: {
    name: "Trend + USOIL inverse filter",
    edge: "CAD is oil-sensitive, so USDCAD trends are confirmed by oil moving the opposite way.",
    watch: [
      "EMA20 > EMA50 (up) or below (down).",
      "USOIL momentum must be opposite: falling oil confirms a USDCAD BUY, rising oil confirms a SELL.",
      "Price pulls back to EMA20 and closes back on the trend side.",
    ],
    entry: "BUY on an up-trend pullback only while oil is soft; SELL on a down-trend pullback only while oil is firm.",
    exit: "Stop 1.8× ATR. Profit-ladder trailing.",
    session: "NY 13:00-21:00 UTC",
    risk: "No trade if oil momentum is flat - the correlation is the whole thesis.",
  },
  NZDUSD: {
    name: "Asian range scalping",
    edge: "Tight, fast fades at the Asian range edges - smaller targets, more frequency.",
    watch: [
      "Asian range = high/low of the 00:00-03:00 UTC candles.",
      "Price within 0.1× ATR of the edge in the 03:00-07:00 UTC window.",
    ],
    entry: "SELL at the upper edge, BUY at the lower edge - a tight 0.1× ATR buffer.",
    exit: "Stop = 1.0× ATR (tight). Profit-ladder trailing.",
    session: "Asian 00:00-07:00 UTC",
    risk: "Lowest risk-per-trade (0.15%) precisely because stops are tight.",
  },
  EURGBP: {
    name: "Mean reversion (fixed target)",
    edge: "This cross ranges hard; band extremes with RSI give clean fixed-target pops.",
    watch: ["Close below the lower band with RSI < 32, or above the upper band with RSI > 68."],
    entry: "BUY the lower-band oversold tag; SELL the upper-band overbought tag.",
    exit: "Fixed target to the mean. Stop 1.3× ATR.",
    session: "London 07:00-16:00 UTC",
    risk: "Low volatility pair - small risk (0.15%) matches its small moves.",
  },
  EURJPY: {
    name: "Trend + risk-sentiment momentum",
    edge: "A risk-proxy cross; it only trend-trades when price momentum and risk mood line up.",
    watch: [
      "EMA20 vs EMA50 sets trend.",
      "Short-term momentum and risk-sentiment must agree with the trend.",
      "Price pulls back to EMA20 and closes back on the trend side.",
    ],
    entry: "BUY an up-trend pullback only when momentum>0 and risk>0; SELL the mirror when both < 0.",
    exit: "Stop 1.8× ATR. Profit-ladder trailing.",
    session: "Asian 00:00-08:00 UTC · London 07:00-16:00 UTC",
    risk: "Wider spreads than the majors; max spread is set a touch higher (30).",
  },
  GBPJPY: {
    name: "Volatility-squeeze breakout",
    edge: "'The Beast' - it waits for the bands to squeeze, then trades the violent expansion.",
    watch: [
      "Bollinger band width must shrink versus the prior bar (a squeeze).",
      "Prior width above ~1.2% is rejected - only real squeezes qualify.",
      "A close beyond the band in the squeeze direction.",
    ],
    entry: "BUY the upside squeeze breakout, SELL the downside - only while the squeeze is tightening.",
    exit: "Wide ATR stop (2.8× ATR) to survive the whips. ATR-based exit mode.",
    session: "London 07:00-16:00 UTC",
    risk: "Highest spread tolerance (35) and wide stops - this one breathes hard.",
  },
  US100: {
    name: "NY-open breakout + VWAP",
    edge: "Nasdaq trends off the NY open; a breakout above/below VWAP confirms real participation.",
    watch: [
      "NY opening range = the 09:00-10:00 New York candles.",
      "A close beyond that range AND on the correct side of VWAP (above VWAP for BUY).",
    ],
    entry: "BUY on a close above the opening-range high while above VWAP; SELL the mirror below VWAP.",
    exit: "Stop 2.0× ATR. Profit-ladder trailing.",
    session: "NY 13:00-21:00 UTC",
    risk: "Guarded so it never trades the same direction as US30 at the same time.",
  },
  US500: {
    name: "Trend pullback + VWAP reversion",
    edge: "S&P dip-buying in trend, plus a VWAP mean-reversion mode when price stretches from value.",
    watch: [
      "Uptrend: pullback to EMA20 that reclaims it while staying above VWAP (BUY).",
      "Or price dips below VWAP but the trend is still up - VWAP mean reversion (BUY).",
      "Mirror for SELL in a downtrend.",
    ],
    entry: "BUY the trend pullback that holds VWAP; or the VWAP reversion aligned to trend. SELL the mirror.",
    exit: "Stop 1.6-1.8× ATR. Profit-ladder trailing.",
    session: "NY 13:00-21:00 UTC",
    risk: "Two entry flavours - it prefers whichever has VWAP agreement.",
  },
  GER40: {
    name: "Frankfurt/London open + gap fill",
    edge: "DAX gaps at the European open; it trades both the opening-range break and the gap-fill back.",
    watch: [
      "European opening range = 07:00-08:00 UTC candles.",
      "Gap fill: a big open away from the prior close (>0.4× ATR) that starts reverting toward it.",
      "Or a close beyond the opening-range high/low.",
    ],
    entry: "Take the gap-fill toward the prior close first if it qualifies; otherwise the opening-range breakout.",
    exit: "Stop 1.8-2.0× ATR. Profit-ladder trailing.",
    session: "Frankfurt/London 07:00-16:00 UTC",
    risk: "Gap-fill is prioritised because the DAX open often over-extends then reverts.",
  },
  USOIL: {
    name: "Momentum breakout (+ EIA blackout)",
    edge: "Trends in bursts; it rides breakouts but stands aside around the weekly EIA inventory print.",
    watch: [
      "A close beyond the prior 20-bar range with a body > 0.25× ATR.",
      "NO trading Wednesday 10:00-11:00 ET (EIA) or when the engine flags an event blackout.",
    ],
    entry: "BUY the upside momentum breakout, SELL the downside - only outside the EIA window.",
    exit: "Stop 2.0× ATR. Profit-ladder trailing.",
    session: "NY 13:00-21:00 UTC",
    risk: "The EIA blackout is non-negotiable - it simply returns no signal then.",
  },
  ETHUSD: {
    name: "Squeeze / BTC lead-lag / weekend",
    edge: "Crypto regimes shift; it fades dead-volatility ranges, trades BTC-led breakouts, and uses weekend momentum.",
    watch: [
      "Low-volatility mode (ATR/price < 0.15%): fade band extremes back to the mean.",
      "Breakout mode: a close beyond the 20-bar range, confirmed by BTC momentum OR a weekend.",
      "BTC lead-lag: ETH follows BTC - BTC momentum must agree with the break.",
    ],
    entry: "In quiet tape, fade the band. In trending tape, take the BTC-confirmed break. Weekends add momentum weight.",
    exit: "Range mode: fixed target to the mean, stop 1.5× ATR. Breakout: 2.2× ATR stop.",
    session: "Continuous (24/7) · weekend logic active Sat/Sun UTC",
    risk: "Widest spread tolerance (100) of all - crypto gapping is normal.",
  },
  BTCUSD: {
    name: "Squeeze breakout (existing)",
    edge: "The original BTC volatility-squeeze strategy that anchors the crypto side.",
    watch: ["Volatility compression then expansion (squeeze).", "A decisive close in the breakout direction."],
    entry: "BUY/Sell the squeeze breakout in the expansion direction.",
    exit: "Profit-percentage ladder trailing stop.",
    session: "Continuous (24/7)",
    risk: "Wide spread tolerance (120) to survive BTC's gap-prone sessions.",
  },
  XAUUSD: {
    name: "Metals strategy (existing)",
    edge: "The original gold engine - session-based entries with the profit-percentage ladder.",
    watch: [
      "Session-aligned setup on gold with macro + mid + trigger scoring.",
      "Engulfing candle votes and higher-timeframe alignment add confidence.",
    ],
    entry: "Takes qualifying gold setups across sessions once the confidence score clears the threshold.",
    exit: "Profit-percentage ladder trailing stop - the signature gold exit.",
    session: "Continuous (24/5)",
    risk: "Highest risk-per-trade (0.5%) as the flagship instrument.",
  },
  XAGUSD: {
    name: "Metals strategy (existing)",
    edge: "Silver twin of the gold engine, same scoring, tuned to silver's larger swings.",
    watch: [
      "Same session + engulfing + HTF framework as gold.",
      "Silver's wider ranges mean thresholds behave a touch differently.",
    ],
    entry: "Qualifying silver setups that clear the confidence threshold.",
    exit: "Profit-percentage ladder trailing stop.",
    session: "Continuous (24/5)",
    risk: "Risk-per-trade 0.5%; silver moves harder than gold so watch the spread filter.",
  },
  US30: {
    name: "US30 strategy (existing)",
    edge: "The original Dow engine - NY-session index trading with engulfing + HTF confirmation.",
    watch: [
      "NY-session Dow setups with macro + mid + trigger scoring.",
      "Engulfing candle votes and higher-timeframe alignment.",
    ],
    entry: "Qualifying NY-session Dow setups that clear the threshold.",
    exit: "Profit-percentage ladder trailing stop.",
    session: "NY 13:00-21:00 UTC",
    risk: "Risk-per-trade 0.5%; US100 is guarded against matching its direction.",
  },
};
