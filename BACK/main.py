"""Soul Trading - FastAPI entry point.

Run (single worker only - state lives in-process):
    uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1

Required env: DATABASE_URL, METAAPI_TOKEN, SOUL_ACCESS_KEY, SOUL_SHUTDOWN_KEY
Optional env: METAAPI_REGION, ANTHROPIC_API_KEY, LLM_PROVIDER, LLM_API_KEY,
              LLM_BASE_URL, LLM_BACKEND_MODULE, LLM_BACKEND_ATTR, LLM_MODEL,
              AI_META_LAYER_PATH, AI_META_CONFIG,
              ALLOWED_ORIGINS (comma separated), ALLOWED_ORIGIN_REGEX, MAX_SESSIONS, TICK_SECONDS
"""
from __future__ import annotations

import logging
import asyncio
import ipaddress
import os
import secrets
import time
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

import engine as eng
from engine import BrokerError, EngineError, Settings, TradingEngine, UserSession
from schemas import (
    AILearningStatus, AccountSummary, ConnectRequest, ConnectResponse, EventBias, OpenPosition, ShutdownResponse,
    StrategyConfig, StrategyConfigUpdate, Symbol, SymbolControlMode, SymbolStatus, SymbolToggleRequest,
    SystemStatus, TradeLog,
)
from symbols_config import SYMBOLS, config_for

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("soul.api")

# Read from the environment (not committed to source control). Startup fails if missing/weak.
SOUL_SHUTDOWN_KEY = os.environ.get("SOUL_SHUTDOWN_KEY", "")
if len(SOUL_SHUTDOWN_KEY) < 24:
    raise RuntimeError("SOUL_SHUTDOWN_KEY must be set and at least 24 characters long")

_failed_attempts: deque[float] = deque()
MAX_FAILS, FAIL_WINDOW = 5, 60.0


def _check_shutdown_key(supplied: str) -> None:
    now = time.monotonic()
    while _failed_attempts and now - _failed_attempts[0] > FAIL_WINDOW:
        _failed_attempts.popleft()
    if len(_failed_attempts) >= MAX_FAILS:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many failed attempts")
    if not secrets.compare_digest(supplied.encode(), SOUL_SHUTDOWN_KEY.encode()):
        _failed_attempts.append(now)
        log.warning("emergency-shutdown: invalid key attempt")
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid shutdown key")


@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = TradingEngine(Settings.from_env())
    await engine.start()
    app.state.engine = engine
    try:
        yield
    finally:
        await engine.stop()


app = FastAPI(title="Soul Trading", version="1.0.0", lifespan=lifespan)

origins = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,                                       # e.g. https://soul-trading.vercel.app
    allow_origin_regex=os.environ.get("ALLOWED_ORIGIN_REGEX") or None,  # e.g. https://soul-trading-.*\.vercel\.app
    allow_credentials=False,                                     # bearer tokens, not cookies
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Soul-Shutdown-Key"],
)

bearer = HTTPBearer(auto_error=False)


def get_engine(request: Request) -> TradingEngine:
    return request.app.state.engine


async def current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    engine: TradingEngine = Depends(get_engine),
) -> UserSession:
    s = engine.user_for_token(creds.credentials) if creds else None
    if not s:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token",
                            headers={"WWW-Authenticate": "Bearer"})
    return s


# --------------------------------------------------------------------------- #
# Health
# --------------------------------------------------------------------------- #
@app.get("/health")
async def health(engine: TradingEngine = Depends(get_engine)) -> dict:
    return {"ok": True, "auto_trading_enabled": eng.is_auto_trading_enabled(),
            "sessions": len(engine.sessions)}


# --------------------------------------------------------------------------- #
# Auth
# --------------------------------------------------------------------------- #
@app.post("/api/v1/auth/connect", response_model=ConnectResponse)
async def connect(body: ConnectRequest, engine: TradingEngine = Depends(get_engine)) -> ConnectResponse:
    if not engine.verify_access_key(body.access_key.get_secret_value()):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid access key")
    try:
        token, session, info = await engine.connect_user(body.credentials, body.config)
    except EngineError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    except BrokerError as e:
        log.warning("connect failed: %s", e)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Broker connection failed") from e
    return ConnectResponse(access_token=token, expires_in=eng.TOKEN_TTL_SECONDS, user_id=session.user_id,
                           account=info, config=session.config)


@app.post("/api/v1/auth/disconnect", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect(s: UserSession = Depends(current_user), engine: TradingEngine = Depends(get_engine)) -> None:
    await engine.disconnect_user(s.user_id)


@app.get("/api/v1/auth/bootstrap")
async def bootstrap(request: Request) -> dict[str, str | int]:
    """Return non-secret local MT5 account details to this machine only."""
    client = request.client
    if client is None or not ipaddress.ip_address(client.host).is_loopback:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Local machine only")
    login = os.environ.get("MT5_LOGIN", "").strip()
    server = os.environ.get("MT5_SERVER", "").strip()
    return {
        "login": int(login) if login.isdigit() else "",
        "server": server,
    }


@app.get("/api/v1/auth/local-account", response_model=AccountSummary)
async def local_account(request: Request, engine: TradingEngine = Depends(get_engine)) -> AccountSummary:
    """Read the locally logged-in MT5 account for the dashboard on this machine only."""
    client = request.client
    if client is None or not ipaddress.ip_address(client.host).is_loopback:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Local machine only")
    if engine.settings.broker != "mt5":
        raise HTTPException(status.HTTP_409_CONFLICT, "Local MT5 account is unavailable in this broker mode")

    login = os.environ.get("MT5_LOGIN", "").strip()
    server = os.environ.get("MT5_SERVER", "").strip()
    broker = eng.MT5LocalBroker(
        int(login) if login.isdigit() else 0,
        server,
        engine.settings.mt5_path,
    )
    try:
        account = await broker.account_info()
        open_positions = await broker.positions()
        realized_today = await broker.realized_pnl_today()
    except BrokerError as e:
        log.warning("local MT5 account summary unavailable: %s", e)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "MT5 account unavailable; open and log in to the local MT5 terminal") from e
    return eng.account_summary(account, open_positions, realized_today)


# --------------------------------------------------------------------------- #
# Bot control / data
# --------------------------------------------------------------------------- #
@app.get("/api/v1/bot/status", response_model=SystemStatus)
async def bot_status(s: UserSession = Depends(current_user),
                     engine: TradingEngine = Depends(get_engine)) -> SystemStatus:
    upcoming = engine.calendar.upcoming()
    ai_learning = None
    if engine.ai_meta is not None:
        try:
            ai = await asyncio.to_thread(engine.ai_meta.status)
            ai_learning = AILearningStatus(
                status=ai["status"],
                reason=ai["reason"],
                learning_bar=ai["learning_bar"],
                threshold=ai["threshold"],
                trades_analyzed=ai["trades_analyzed"],
                model_version=ai["model_version"],
                wf_passed=ai["wf_passed"],
            )
        except Exception:
            log.exception("AI meta-layer status unavailable")
            ai_learning = AILearningStatus(
                status="error", reason="AI learning status is temporarily unavailable.",
                learning_bar=0, threshold=0, trades_analyzed=0,
            )
    return SystemStatus(
        auto_trading_enabled=eng.is_auto_trading_enabled(), active_sessions=len(engine.sessions),
        current_session=eng.current_session(),
        next_event_type=upcoming[0].event_type if upcoming else None,
        next_event_time=upcoming[0].time if upcoming else None,
        latest_event_bias=engine.latest_bias,
        ai_learning=ai_learning)


@app.get("/api/v1/bot/account", response_model=AccountSummary)
async def account_summary(
    s: UserSession = Depends(current_user),
    engine: TradingEngine = Depends(get_engine),
) -> AccountSummary:
    try:
        account = await s.broker.account_info()
        positions = await s.broker.positions()
        if isinstance(s.broker, eng.MT5LocalBroker):
            realized_today = await s.broker.realized_pnl_today()
        else:
            now_local = datetime.now().astimezone()
            start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
            start = start_local.astimezone(timezone.utc)
            realized_today = await engine.db.realized_pnl_since(s.user_id, start)
    except BrokerError as e:
        log.warning("[%s] account summary unavailable: %s", s.user_id, e)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Broker account data unavailable") from e
    return eng.account_summary(account, positions, realized_today)


@app.get("/api/v1/bot/config", response_model=StrategyConfig)
async def get_config(s: UserSession = Depends(current_user)) -> StrategyConfig:
    return s.config


@app.patch("/api/v1/bot/config", response_model=StrategyConfig)
async def patch_config(body: StrategyConfigUpdate, s: UserSession = Depends(current_user),
                       engine: TradingEngine = Depends(get_engine)) -> StrategyConfig:
    return await engine.update_config(s, body)


@app.get("/api/v1/bot/explain")
async def explain(after: int = 0, s: UserSession = Depends(current_user)) -> list[dict]:
    """Soul Explainer feed: why trades were taken or avoided. Poll with ?after=<last id>."""
    return [e for e in s.explain if e["id"] > after]


@app.get("/api/v1/bot/setups")
async def setups(s: UserSession = Depends(current_user),
                 engine: TradingEngine = Depends(get_engine)) -> list[dict]:
    """Rank live setups and pinned/open positions for the dashboard."""
    return engine.ranked_setups(s)


@app.get("/api/v1/bot/positions", response_model=list[OpenPosition])
async def positions(s: UserSession = Depends(current_user)) -> list[OpenPosition]:
    try:
        raw = await s.broker.positions()
    except BrokerError as e:
        log.warning("position fetch failed: %s", e)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Broker positions unavailable") from e
    result = []
    for p in raw:
        trade = s.open_trades.get(str(p["id"]))
        if trade:
            strategy = trade.strategy
            if not strategy:
                strategy = (
                    "Economic event" if trade.source == eng.TradeSource.EVENT else
                    "Engulfing" if trade.source == eng.TradeSource.ENGULFING else
                    eng.strategy_name(trade.symbol, trade.open_time)
                )
        else:
            comment = str(p.get("comment") or "")
            strategy = comment.removeprefix("soul:").strip() or "Unknown"
        result.append(OpenPosition(
            symbol=p["symbol"], side=p["side"], volume=p["volume"], entry=p["entry"],
            stop_loss=p["stop_loss"], take_profit=p["take_profit"],
            floating_profit=p["floating_profit"], strategy=strategy,
        ))
    return result


@app.get("/api/v1/trades", response_model=list[TradeLog])
async def trades(limit: int = 50, s: UserSession = Depends(current_user),
                 engine: TradingEngine = Depends(get_engine)) -> list[TradeLog]:
    return await engine.db.list_trades(s.user_id, max(1, min(limit, 200)))


@app.get("/api/v1/events/bias", response_model=EventBias | None)
async def latest_bias(_: UserSession = Depends(current_user),
                      engine: TradingEngine = Depends(get_engine)) -> EventBias | None:
    return engine.latest_bias


@app.get("/api/v1/symbols", response_model=list[SymbolStatus])
async def symbols_status(
    s: UserSession = Depends(current_user),
    engine: TradingEngine = Depends(get_engine),
) -> list[SymbolStatus]:
    available = await engine.refresh_symbol_controls()
    try:
        positions = await s.broker.positions()
    except BrokerError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Broker positions unavailable") from exc
    today_utc = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    try:
        realized_by_symbol = await engine.db.realized_pnl_by_symbol_since(s.user_id, today_utc)
    except Exception as exc:
        log.exception("symbol P&L unavailable")
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "Symbol P&L is temporarily unavailable") from exc
    rows = []
    for symbol, config in SYMBOLS.items():
        if available:
            enabled, mode = engine.symbol_control(symbol)
        else:
            enabled, mode = False, SymbolControlMode.MANAGE_ONLY
        expected = "".join(ch for ch in config.broker_symbol.casefold() if ch.isalnum())
        open_count = sum(
            1 for position in positions
            if (actual := "".join(ch for ch in str(position.get("symbol", "")).casefold()
                                  if ch.isalnum()))
            and (actual == expected or actual.startswith(expected) or actual.endswith(expected))
        )
        floating_today = sum(
            float(position.get("floating_profit", 0.0)) for position in positions
            if (actual := "".join(ch for ch in str(position.get("symbol", "")).casefold()
                                  if ch.isalnum()))
            and (actual == expected or actual.startswith(expected) or actual.endswith(expected))
        )
        today_pnl = realized_by_symbol.get(symbol.value, 0.0)
        today_pnl += floating_today
        rows.append(SymbolStatus(
            symbol=symbol,
            broker_symbol=s.config.broker_symbol(symbol),
            strategy=config.strategy,
            enabled=enabled,
            mode=mode,
            open_positions=open_count,
            today_pnl=today_pnl,
            halted_by_kill_switch=not eng.is_auto_trading_enabled(),
        ))
    return rows


@app.post("/api/v1/symbols/{symbol}/toggle", response_model=SymbolStatus)
async def toggle_symbol(
    symbol: Symbol,
    body: SymbolToggleRequest,
    s: UserSession = Depends(current_user),
    engine: TradingEngine = Depends(get_engine),
) -> SymbolStatus:
    try:
        await engine.toggle_symbol(
            s, symbol, body.enabled, body.mode, body.close_open_positions,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    except BrokerError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "Symbol controls are unavailable while the database is disconnected") from exc
    try:
        positions = await s.broker.positions()
        today_utc = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        pnl = await engine.db.realized_symbol_pnl_since(s.user_id, symbol.value, today_utc)
    except BrokerError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Broker positions unavailable") from exc
    except Exception as exc:
        log.exception("symbol status could not be refreshed after toggle")
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "Symbol status temporarily unavailable") from exc
    config = config_for(symbol)
    expected = "".join(ch for ch in s.config.broker_symbol(symbol).casefold() if ch.isalnum())
    count = sum(
        1 for position in positions
        if (actual := "".join(ch for ch in str(position.get("symbol", "")).casefold()
                              if ch.isalnum()))
        and (actual == expected or actual.startswith(expected) or actual.endswith(expected))
    )
    floating_today = sum(
        float(position.get("floating_profit", 0.0)) for position in positions
        if (actual := "".join(ch for ch in str(position.get("symbol", "")).casefold()
                              if ch.isalnum()))
        and (actual == expected or actual.startswith(expected) or actual.endswith(expected))
    )
    enabled, mode = engine.symbol_control(symbol)
    return SymbolStatus(
        symbol=symbol, broker_symbol=s.config.broker_symbol(symbol), strategy=config.strategy,
        enabled=enabled, mode=mode,         open_positions=count, today_pnl=pnl + floating_today,
        halted_by_kill_switch=not eng.is_auto_trading_enabled(),
    )


# --------------------------------------------------------------------------- #
# GLOBAL KILL-SWITCH
# --------------------------------------------------------------------------- #
@app.post("/api/v1/system/emergency-shutdown", response_model=ShutdownResponse)
async def emergency_shutdown(
    engine: TradingEngine = Depends(get_engine),
    x_soul_shutdown_key: str = Header(default="", alias="X-Soul-Shutdown-Key"),
) -> ShutdownResponse:
    """Overrides everything: AUTO_TRADING_ENABLED -> False, then market-closes ALL open
    positions on ALL active broker sessions. Requires header X-Soul-Shutdown-Key."""
    _check_shutdown_key(x_soul_shutdown_key)
    log.critical("EMERGENCY SHUTDOWN TRIGGERED")
    return await engine.emergency_shutdown()


@app.post("/api/v1/system/resume")
async def resume(
    engine: TradingEngine = Depends(get_engine),
    x_soul_shutdown_key: str = Header(default="", alias="X-Soul-Shutdown-Key"),
) -> dict:
    """Re-arm auto-trading after a shutdown (same key required)."""
    _check_shutdown_key(x_soul_shutdown_key)
    engine.resume_trading()
    return {"auto_trading_enabled": eng.is_auto_trading_enabled()}
