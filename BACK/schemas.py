"""Soul Trading - Pydantic models (auth, config, trade logs, confidence metrics)."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, SecretStr


# --------------------------------------------------------------------------- #
# Enums
# --------------------------------------------------------------------------- #
class Symbol(str, Enum):
    US30 = "US30"
    XAUUSD = "XAUUSD"
    XAGUSD = "XAGUSD"
    BTCUSD = "BTCUSD"
    EURUSD = "EURUSD"
    GBPUSD = "GBPUSD"
    EURGBP = "EURGBP"
    USDJPY = "USDJPY"
    USDCHF = "USDCHF"
    AUDUSD = "AUDUSD"
    USDCAD = "USDCAD"
    NZDUSD = "NZDUSD"
    EURJPY = "EURJPY"
    GBPJPY = "GBPJPY"
    US100 = "US100"
    US500 = "US500"
    GER40 = "GER40"
    USOIL = "USOIL"
    ETHUSD = "ETHUSD"


class Timeframe(str, Enum):
    M1 = "1m"   # execution
    M5 = "5m"   # mid
    M15 = "15m"  # macro
    M30 = "30m"
    H1 = "1h"
    H4 = "4h"

    @property
    def minutes(self) -> int:
        return {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "1h": 60, "4h": 240}[self.value]


class TradingSession(str, Enum):
    ASIAN = "asian"
    LONDON = "london"
    NEW_YORK = "new_york"


class Direction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    NEUTRAL = "NEUTRAL"


class EventType(str, Enum):
    NFP = "NFP"
    CPI = "CPI"
    PPI = "PPI"
    FOMC = "FOMC"


class TradeSource(str, Enum):
    TECHNICAL = "technical"
    EVENT = "event"
    ENGULFING = "engulfing"


class TradeStatus(str, Enum):
    OPEN = "open"
    CLOSED = "closed"


# --------------------------------------------------------------------------- #
# Authentication / broker
# --------------------------------------------------------------------------- #
class BrokerCredentials(BaseModel):
    """MT5 account identity.

    The MetaTrader5 Python package is Windows-only, so on a Linux AWS instance the
    engine talks to the broker through a cloud bridge (MetaApi) using a pre-provisioned
    `metaapi_account_id`. `password` is optional, held only in memory (SecretStr is
    masked in repr/logs) and is never persisted - it exists for a self-hosted Windows
    bridge adapter.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    login: int = Field(gt=0, description="MT5 account number")
    server: str = Field(min_length=2, max_length=100, description="MT5 server name")
    password: Optional[SecretStr] = Field(default=None, repr=False)
    metaapi_account_id: Optional[str] = Field(default=None, min_length=8, max_length=64)


class AccountInfo(BaseModel):
    login: int
    server: str = ""
    currency: str = "USD"
    balance: float
    equity: float
    free_margin: float
    leverage: int = 100


class AccountSummary(BaseModel):
    currency: str
    balance: float
    equity: float
    free_margin: float
    floating_profit: float
    floating_loss: float
    net_floating_pnl: float
    realized_today: float = 0.0
    open_positions: int


class SymbolSpec(BaseModel):
    symbol: str
    contract_size: float = Field(gt=0)
    min_lot: float = Field(gt=0)
    max_lot: float = Field(gt=0)
    lot_step: float = Field(gt=0)
    digits: int = 2
    point: float = 0.0
    tick_size: float = 0.0
    tick_value: float = 0.0


# --------------------------------------------------------------------------- #
# Strategy configuration
# --------------------------------------------------------------------------- #
class StrategyParams(BaseModel):
    """Parameters the retrospective learner is allowed to tune (bounded)."""

    sl_atr_mult: float = Field(default=1.5, ge=0.8, le=3.0)
    tp_rr: float = Field(default=1.5, ge=0.8, le=3.0)
    min_signal_score: float = Field(default=65.0, ge=50.0, le=90.0)


class StrategyConfig(BaseModel):
    enabled: bool = True
    scalping: bool = Field(default=True, description="Enable the scalping trading mode")
    day_trading_enabled: bool = Field(default=False, description="Enable the day-trading mode")
    risk_percent: float = Field(default=0.5, gt=0, le=2.0, description="% of balance risked per trade")
    max_open_trades: int = Field(
        default=3, ge=1, le=10,
        description="Legacy setting retained for API compatibility; trading is limited per symbol.",
    )
    min_lot_risk_tolerance: float = Field(
        default=2.0, ge=1.0, le=5.0,
        description="Use 0.01 lots when broker minimum risk exceeds risk_amount*tolerance, if supported",
    )
    symbols: list[Symbol] = Field(default_factory=lambda: [
        Symbol.US30, Symbol.XAUUSD, Symbol.XAGUSD, Symbol.BTCUSD,
        Symbol.EURUSD, Symbol.GBPUSD, Symbol.EURGBP,
    ])
    pinned_symbols: list[Symbol] = Field(default_factory=list)
    symbol_map: dict[str, str] = Field(
        default_factory=dict,
        description="Optional exact broker names, e.g. {'US30': 'US30m'}; MT5 also auto-detects unique prefix/suffix variants",
    )
    event_trading_enabled: bool = True
    event_min_confidence: float = Field(default=60.0, ge=0, le=100)
    event_risk_multiplier: float = Field(default=0.5, ge=0.1, le=1.0)
    engulfing_enabled: bool = False
    engulfing_paper_mode: bool = True
    params: StrategyParams = Field(default_factory=StrategyParams)

    @property
    def trading_mode(self) -> str:
        modes = []
        if self.scalping:
            modes.append("scalping")
        if self.day_trading_enabled:
            modes.append("day trading")
        return " + ".join(modes) if modes else "no technical modes"

    def broker_symbol(self, symbol: Symbol) -> str:
        return self.symbol_map.get(symbol.value, symbol.value)


class StrategyConfigUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: Optional[bool] = None
    scalping: Optional[bool] = None
    day_trading_enabled: Optional[bool] = None
    risk_percent: Optional[float] = Field(default=None, gt=0, le=2.0)
    max_open_trades: Optional[int] = Field(
        default=None, ge=1, le=10,
        description="Legacy setting retained for API compatibility; trading is limited per symbol.",
    )
    event_trading_enabled: Optional[bool] = None
    event_min_confidence: Optional[float] = Field(default=None, ge=0, le=100)
    event_risk_multiplier: Optional[float] = Field(default=None, ge=0.1, le=1.0)
    engulfing_enabled: Optional[bool] = None
    engulfing_paper_mode: Optional[bool] = None
    symbols: Optional[list[Symbol]] = None
    pinned_symbols: Optional[list[Symbol]] = None


class OpenPosition(BaseModel):
    symbol: str
    side: Direction
    volume: float
    entry: float
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    floating_profit: float
    strategy: str = "Unknown"


class SymbolControlMode(str, Enum):
    ACTIVE = "active"
    MANAGE_ONLY = "manage_only"
    OFF = "off"


class SymbolToggleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
    mode: SymbolControlMode
    close_open_positions: bool = False


class SymbolStatus(BaseModel):
    symbol: Symbol
    broker_symbol: str
    strategy: str
    enabled: bool
    mode: SymbolControlMode
    open_positions: int
    today_pnl: float
    halted_by_kill_switch: bool = False


class ConnectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    access_key: SecretStr = Field(description="Deployment access key (SOUL_ACCESS_KEY)")
    credentials: BrokerCredentials
    config: StrategyConfig = Field(default_factory=StrategyConfig)


class ConnectResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user_id: str
    account: AccountInfo
    config: StrategyConfig


# --------------------------------------------------------------------------- #
# Confidence / event bias
# --------------------------------------------------------------------------- #
class ConfidenceMetric(BaseModel):
    symbol: Symbol
    direction: Direction
    confidence: float = Field(ge=0, le=100, description="0-100 %")
    sentiment_score: float = Field(ge=-1, le=1, description="+1 = hawkish / USD-positive")
    headline_count: int = Field(ge=0)
    rationale: str
    event_type: Optional[EventType] = None
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class EventBias(BaseModel):
    event_type: EventType
    event_title: str
    event_time: datetime
    metrics: list[ConfidenceMetric]


# --------------------------------------------------------------------------- #
# Trade logs
# --------------------------------------------------------------------------- #
class TradeReview(BaseModel):
    summary: str
    failure_category: str = "unclassified"
    headlines: list[str] = Field(default_factory=list)
    suggested: dict[str, float] = Field(default_factory=dict)
    applied: dict[str, float] = Field(default_factory=dict)
    reviewed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TradeLog(BaseModel):
    id: Optional[int] = None
    user_id: str
    position_id: str
    symbol: Symbol
    side: Direction
    volume: float
    open_price: float
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    open_time: datetime
    status: TradeStatus = TradeStatus.OPEN
    close_price: Optional[float] = None
    close_time: Optional[datetime] = None
    profit: Optional[float] = None
    close_reason: Optional[str] = None
    session: TradingSession
    scalping: bool
    source: TradeSource = TradeSource.TECHNICAL
    strategy: Optional[str] = None
    signal_score: Optional[float] = None
    max_hold_minutes: Optional[int] = None
    review: Optional[TradeReview] = None


# --------------------------------------------------------------------------- #
# System
# --------------------------------------------------------------------------- #
class ShutdownResponse(BaseModel):
    auto_trading_enabled: bool
    sessions_processed: int
    positions_closed: int
    positions_failed: list[str] = Field(default_factory=list)
    fully_flat: bool
    triggered_at: datetime


class AILearningStatus(BaseModel):
    status: str
    reason: str
    learning_bar: float
    threshold: float
    trades_analyzed: int
    model_version: Optional[str] = None
    wf_passed: bool = False


class SystemStatus(BaseModel):
    auto_trading_enabled: bool
    active_sessions: int
    current_session: TradingSession
    next_event_type: Optional[EventType] = None
    next_event_time: Optional[datetime] = None
    latest_event_bias: Optional[EventBias] = None
    ai_learning: Optional[AILearningStatus] = None
