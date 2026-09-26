# -*- coding: utf-8 -*-
"""
Perfume News Scout — Telegram delivery.

Sends the daily digest through the user's own bot (@atr_ads_bot or any other
bot they own). Requires TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID.

chat_id can be:
  * a numeric user/chat id  (e.g. 123456789)
  * @channelusername        (bot must be admin with "Post Messages")

Run `python scout.py --whoami` after messaging the bot once to discover ids.
"""

import time
from typing import Optional

import requests

API_BASE = "https://api.telegram.org"
MAX_LEN = 4000  # Telegram hard limit is 4096; keep a safety margin


class TelegramError(RuntimeError):
    pass


def _call(token: str, method: str, payload: Optional[dict] = None,
          timeout: int = 30) -> dict:
    url = f"{API_BASE}/bot{token}/{method}"
    last_err: Optional[str] = None
    for attempt in range(1, 4):
        try:
            resp = requests.post(url, json=payload or {}, timeout=timeout)
            data = resp.json()
            if data.get("ok"):
                return data
            code = data.get("error_code")
            desc = data.get("description", "unknown error")
            if code == 429:
                wait = data.get("parameters", {}).get("retry_after", 5)
                time.sleep(wait + 1)
                last_err = f"rate limited ({wait}s)"
                continue
            raise TelegramError(f"[{code}] {desc}")
        except TelegramError:
            raise
        except Exception as exc:
            last_err = str(exc)
            time.sleep(2 * attempt)
    raise TelegramError(f"Telegram call failed after retries: {last_err}")


def verify(token: str) -> dict:
    data = _call(token, "getMe")
    return data.get("result", {})


def send_text(token: str, chat_id: str, text: str) -> None:
    """Send long text, splitting on line boundaries if needed."""
    chunks = _split(text)
    for i, chunk in enumerate(chunks):
        _call(token, "sendMessage", {
            "chat_id": chat_id,
            "text": chunk,
            "disable_web_page_preview": True,
        })
        if i < len(chunks) - 1:
            time.sleep(1.2)  # stay under per-chat rate limits


def _split(text: str) -> list[str]:
    if len(text) <= MAX_LEN:
        return [text]
    chunks: list[str] = []
    current = ""
    for line in text.split("\n"):
        if len(current) + len(line) + 1 > MAX_LEN:
            if current:
                chunks.append(current)
            # hard-split pathological lines
            while len(line) > MAX_LEN:
                chunks.append(line[:MAX_LEN])
                line = line[MAX_LEN:]
            current = line
        else:
            current = f"{current}\n{line}" if current else line
    if current:
        chunks.append(current)
    return chunks


def whoami(token: str) -> str:
    """List chats that recently messaged the bot, to help find chat_id."""
    data = _call(token, "getUpdates", {"limit": 50})
    lines = ["چت‌هایی که اخیراً به ربات پیام داده‌اند:", ""]
    seen = {}
    for upd in data.get("result", []):
        msg = upd.get("message") or upd.get("edited_message") or {}
        chat = msg.get("chat") or {}
        cid = chat.get("id")
        if cid is None:
            continue
        seen[cid] = chat
    if not seen:
        lines.append("(هیچ پیامی پیدا نشد — اول یک بار به ربات پیام بده، بعد دوباره اجرا کن)")
    for cid, chat in seen.items():
        kind = chat.get("type", "?")
        username = chat.get("username", "")
        name = chat.get("first_name", "") or chat.get("title", "")
        lines.append(f"• id={cid}  نوع={kind}  نام={name}  یوزرنیم=@{username}")
    lines.append("")
    lines.append("chat_id خودت را در TELEGRAM_CHAT_ID بگذار (برای کانال: @نام‌کانال).")
    return "\n".join(lines)
