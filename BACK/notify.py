"""Telegram notifications for Soul Trading (additive, fail-safe).

Reads TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID from the environment. The token is
never hardcoded and never committed (it lives in the git-ignored .env). If either
is missing, or any send fails, notifications are silently skipped and the trading
engine keeps running - a notification failure must never break trading.

Usage:
    from notify import telegram
    await telegram.send("Hello from Soul")                 # plain text
    await telegram.trade_opened(...)                        # rich trade card
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx

_API = "https://api.telegram.org"


def _env(name: str) -> str:
    return (os.environ.get(name, "") or "").strip()


def is_configured() -> bool:
    return bool(_env("TELEGRAM_BOT_TOKEN") and _env("TELEGRAM_CHAT_ID"))


class TelegramNotifier:
    def __init__(self) -> None:
        self.token = _env("TELEGRAM_BOT_TOKEN")
        self.chat_id = _env("TELEGRAM_CHAT_ID")
        # Optional: a second chat/channel for signals (defaults to chat_id).
        self.signal_chat_id = _env("TELEGRAM_SIGNAL_CHAT_ID") or self.chat_id
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def enabled(self) -> bool:
        return bool(self.token and self.chat_id)

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=5.0))
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            try:
                await self._client.aclose()
            except Exception:  # noqa: BLE001
                pass
            self._client = None

    async def _send(self, text: str, chat_id: Optional[str] = None) -> bool:
        if not self.enabled:
            return False
        target = chat_id or self.chat_id
        url = f"{_API}/bot{self.token}/sendMessage"
        try:
            r = await self._http().post(url, json={
                "chat_id": target, "text": text, "parse_mode": "HTML",
                "disable_web_page_preview": True,
            })
            if r.status_code != 200:
                # Don't spam logs with the token; status + description only.
                try:
                    desc = r.json().get("description", r.text[:120])
                except Exception:  # noqa: BLE001
                    desc = r.text[:120]
                _log(f"telegram send failed ({r.status_code}): {desc}")
                return False
            return True
        except Exception as exc:  # noqa: BLE001 - never let notifications break trading
            _log(f"telegram send error: {exc!r}")
            return False

    # -- public helpers ----------------------------------------------------
    async def send(self, text: str) -> bool:
        return await self._send(text)

    async def send_signal(self, text: str) -> bool:
        """Send to the signals channel/chat (falls back to the main chat)."""
        return await self._send(text, self.signal_chat_id)


def _log(msg: str) -> None:
    try:
        import logging
        logging.getLogger("soul.notify").warning("%s", msg)
    except Exception:  # noqa: BLE001
        pass


def _fmt_price(value: Optional[float], digits: int = 5) -> str:
    if value is None:
        return "--"
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return str(value)


def _sastnow() -> datetime:
    """South African Standard Time = UTC+2 year-round (no daylight saving)."""
    return datetime.now(timezone(timedelta(hours=2)))


def _footer() -> str:
    """Shared footer: SAST timestamp + creator credit."""
    return (f"<i>🕐 {_sastnow().strftime('%Y-%m-%d %H:%M')} SAST</i>\n"
            f"<i>Soul Trading · created by Lebogang Malatjie</i>")


# Module-level singleton (lazy; safe to import anywhere).
telegram = TelegramNotifier()


# -- rich message builders (pure, easy to test) ---------------------------
def format_trade_opened(*, symbol: str, side: str, lots: float, entry: Optional[float],
                        stop: Optional[float], tp: Optional[float], strategy: str = "",
                        reason: str = "", digits: int = 5, source: str = "") -> str:
    arrow = "🟢 BUY" if side.upper() == "BUY" else "🔴 SELL"
    lines = [
        f"<b>{arrow} · {symbol}</b>",
        "",
        f"🎯 <b>Entry:</b> {_fmt_price(entry, digits)}",
        f"🛑 <b>Stop:</b> {_fmt_price(stop, digits)}",
        f"✅ <b>Take profit:</b> {_fmt_price(tp, digits)}",
        f"📦 <b>Lots:</b> {lots}",
    ]
    if strategy:
        lines.append(f"🧠 <b>Strategy:</b> {strategy}")
    if source:
        lines.append(f"🏷️ <b>Source:</b> {source}")
    if reason:
        lines += ["", f"💬 <b>Why:</b> {reason}"]
    lines += ["", _footer()]
    return "\n".join(lines)


def format_trade_closed(*, symbol: str, side: str, lots: float, entry: Optional[float],
                        close: Optional[float], profit: Optional[float], reason: str = "",
                        digits: int = 5) -> str:
    pnl = float(profit) if profit is not None else 0.0
    emo = "✅" if pnl >= 0 else "❌"
    sign = "+" if pnl >= 0 else ""
    lines = [
        f"<b>{emo} CLOSED · {symbol}</b>  ({side.upper()} {lots} lots)",
        "",
        f"▶️ <b>Entry:</b> {_fmt_price(entry, digits)}",
        f"⏹️ <b>Close:</b> {_fmt_price(close, digits)}",
        f"💰 <b>P/L:</b> {sign}{pnl:.2f}",
    ]
    if reason:
        lines += ["", f"💬 <b>Why closed:</b> {reason}"]
    lines += ["", _footer()]
    return "\n".join(lines)
