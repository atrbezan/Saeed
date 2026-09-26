# -*- coding: utf-8 -*-
"""
🕵️ Perfume News Scout — ایجنت شکارچی خبرهای عطر
=================================================

Continuously scans English-language fragrance content (news, community,
YouTube), scores every item for controversy / weirdness / viral potential,
keeps a permanent archive so nothing is ever repeated, and sends the TOP 5
ready-to-shoot content briefs to Telegram every day.

Runs comfortably on:
  * GitHub Actions (zero cost, no server) — see .github/workflows/scout.yml
  * Any tiny VPS / Raspberry Pi / Termux   ->  python scout.py
  * One-off runs (cron)                    ->  python scout.py --single-run

Usage:
  python scout.py                  # daemon: crawl forever + daily digest
  python scout.py --single-run     # one crawl pass (+ digest if it's time)
  python scout.py --digest-now     # crawl then force-send today's digest
  python scout.py --preview        # build today's digest, print it, send nothing
  python scout.py --test-telegram  # send a test message to the configured chat
  python scout.py --whoami         # list chats that messaged the bot

Environment variables:
  TELEGRAM_BOT_TOKEN    token of your bot (e.g. @atr_ads_bot)
  TELEGRAM_CHAT_ID      your chat id or @channel
  SCOUT_STATE_FILE      archive file        (default scout_state.json)
  SCOUT_DIGEST_HOUR     Tehran hour         (default 9)
  SCOUT_DIGEST_MINUTE   Tehran minute       (default 30)
  SCOUT_MIN_SCORE       minimum score       (default 25)
  SCOUT_MAX_FEEDS       feeds per run       (default 6)
  SCOUT_POLL_MINUTES    loop sleep minutes  (default 30)
  SCOUT_LLM_API_KEY     optional OpenAI-compatible key for polished briefs
"""

import argparse
import logging
import os
import random
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Optional
from urllib.parse import parse_qs, unquote, urlparse

import requests

from scout_archive import Archive, url_hash
from scout_briefs import build_brief, build_evergreen_brief, fa_num, llm_polish
from scout_evergreen import EVERGREEN_FACTS
from scout_scorer import (clean_google_title, fingerprint, is_about_fragrance,
                          jaccard, score_item, strip_html)
from scout_sources import all_feeds
from scout_telegram import TelegramError, send_text, verify, whoami

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("scout")

TEHRAN_OFFSET = timedelta(hours=3, minutes=30)  # IR has no DST since 2022

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 SaeedScout/1.0")


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
class ScoutConfig:
    def __init__(self):
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
        self.state_file = os.getenv("SCOUT_STATE_FILE", "scout_state.json")
        self.digest_hour = int(os.getenv("SCOUT_DIGEST_HOUR", "9"))
        self.digest_minute = int(os.getenv("SCOUT_DIGEST_MINUTE", "30"))
        self.min_score = int(os.getenv("SCOUT_MIN_SCORE", "25"))
        self.max_feeds = int(os.getenv("SCOUT_MAX_FEEDS", "6"))
        self.poll_minutes = int(os.getenv("SCOUT_POLL_MINUTES", "30"))

    @property
    def telegram_ready(self) -> bool:
        return bool(self.bot_token and self.chat_id)


def tehran_now() -> datetime:
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Asia/Tehran"))
    except Exception:
        return datetime.now(timezone.utc) + TEHRAN_OFFSET


# ---------------------------------------------------------------------------
# Jalali date for the digest header
# ---------------------------------------------------------------------------
JALALI_MONTHS = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
                 "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"]
WEEKDAYS_FA = ["شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه"]


def gregorian_to_jalali(gy: int, gm: int, gd: int) -> tuple[int, int, int]:
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    if gy > 1600:
        jy, gy = 979, gy - 1600
    else:
        jy, gy = 0, gy - 621
    gy2 = gy + 1 if gm > 2 else gy
    days = (365 * gy + (gy2 + 3) // 4 - (gy2 + 99) // 100
            + (gy2 + 399) // 400 - 80 + gd + g_d_m[gm - 1])
    jy += 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm, jd = 1 + days // 31, 1 + days % 31
    else:
        jm, jd = 7 + (days - 186) // 30, 1 + (days - 186) % 30
    return jy, jm, jd


def fa_date(dt: datetime) -> str:
    jy, jm, jd = gregorian_to_jalali(dt.year, dt.month, dt.day)
    return f"{WEEKDAYS_FA[(dt.weekday() + 1) % 7]} {fa_num(jd)} {JALALI_MONTHS[jm - 1]} {fa_num(jy)}"


# ---------------------------------------------------------------------------
# HTTP + feed parsing (stdlib only: RSS 2.0 / Atom / RDF)
# ---------------------------------------------------------------------------
def fetch_url(url: str, timeout: int = 25) -> Optional[str]:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/rss+xml, application/atom+xml, application/xml, "
                  "text/xml, */*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    resp = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
    resp.raise_for_status()
    return resp.content.decode("utf-8", errors="replace")


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower() if "}" in tag else tag.lower()


def _text(el) -> str:
    return "".join(el.itertext()).strip() if el is not None else ""


def _parse_date(raw: str) -> Optional[datetime]:
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        dt = parsedate_to_datetime(raw)  # RFC822 (RSS)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        pass
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _unbing(link: str) -> str:
    """Bing wraps links in apiclick.aspx?...&url=<real url> — unwrap it."""
    if "bing.com/news/apiclick.aspx" in link:
        qs = parse_qs(urlparse(link).query)
        if qs.get("url"):
            return unquote(qs["url"][0])
    return link


def parse_feed(xml_text: str) -> list[dict]:
    """Parse RSS/Atom/RDF into [{title, link, published, summary}]."""
    xml_text = re.sub(r"^\ufeff", "", xml_text)
    # some feeds ship illegal control chars
    xml_text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", xml_text)
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        log.warning("XML parse error: %s", exc)
        return []

    entries: list[dict] = []
    root_tag = _local(root.tag)

    if root_tag == "feed":  # Atom
        for entry in root:
            if _local(entry.tag) != "entry":
                continue
            item = {"title": "", "link": "", "published": None, "summary": ""}
            for child in entry:
                tag = _local(child.tag)
                if tag == "title":
                    item["title"] = strip_html(_text(child))
                elif tag == "link":
                    href = child.attrib.get("href", "")
                    rel = child.attrib.get("rel", "alternate")
                    if href and (rel == "alternate" or not item["link"]):
                        item["link"] = href
                elif tag in ("published", "updated") and item["published"] is None:
                    item["published"] = _parse_date(_text(child))
                elif tag in ("summary", "content") and not item["summary"]:
                    item["summary"] = strip_html(_text(child))[:600]
            if item["title"]:
                entries.append(item)
        return entries

    # RSS 2.0 / RDF
    item_tag = "item"
    for item_el in root.iter():
        if _local(item_el.tag) == item_tag:
            item = {"title": "", "link": "", "published": None, "summary": ""}
            for child in item_el:
                tag = _local(child.tag)
                if tag == "title":
                    item["title"] = strip_html(_text(child))
                elif tag == "link" and _text(child):
                    item["link"] = _text(child).strip()
                elif tag == "pubdate" or tag == "date":
                    item["published"] = _parse_date(_text(child))
                elif tag == "description" and not item["summary"]:
                    item["summary"] = strip_html(_text(child))[:600]
            if item["title"] and not item["link"]:
                # some feeds put the URL in guid
                for child in item_el:
                    if _local(child.tag) == "guid":
                        txt = _text(child).strip()
                        if txt.startswith("http"):
                            item["link"] = txt
                            break
            if item["title"]:
                entries.append(item)
    return entries


# ---------------------------------------------------------------------------
# Crawl pass
# ---------------------------------------------------------------------------
def crawl(archive: Archive, cfg: ScoutConfig, max_feeds: Optional[int] = None) -> int:
    feeds = all_feeds()
    batch = archive.feed_next_candidates(feeds, max_feeds or cfg.max_feeds)
    total_new = 0

    for i, feed in enumerate(batch):
        if i > 0:
            time.sleep(random.uniform(2.0, 5.0))  # be gentle with servers
        log.info("fetching %s", feed.label)
        try:
            text = fetch_url(feed.url)
            items = parse_feed(text)[: feed.max_items]
        except Exception as exc:
            log.warning("fetch failed for %s: %s", feed.label, exc)
            archive.feed_finished(feed.key, feed.base_interval_min, success=False)
            continue

        new_here = 0
        now = datetime.now(timezone.utc)
        for item in items:
            title_raw = item["title"]
            summary = item.get("summary", "")
            publisher = ""
            if feed.key.startswith("gn:") or feed.key.startswith("bing:"):
                title_clean, publisher = clean_google_title(title_raw)
            else:
                title_clean = title_raw

            if not is_about_fragrance(title_clean, summary, feed.trusted):
                continue

            link = _unbing(item.get("link", ""))  # unwrap Bing apiclick redirects
            fp = fingerprint(title_clean)
            if archive.is_duplicate(link or title_clean, fp):
                continue

            score, cat, tags = score_item(title_clean, summary, feed.weight_boost,
                                          item.get("published"), now)
            published_iso = item["published"].isoformat(timespec="seconds") \
                if item.get("published") else None
            rec = archive.add_item(
                url=link or title_clean,
                title=title_clean, title_fp=fp, source=feed.label,
                score=score, category=cat, publisher=publisher,
                published_iso=published_iso,
            )
            if rec:
                new_here += 1
                log.info("  +%3d [%s] %s", score, cat, title_clean[:80])

        total_new += new_here
        archive.feed_finished(feed.key, feed.base_interval_min,
                              success=True, new_items=new_here)

    log.info("crawl done: %d new items (archive size: %d)",
             total_new, len(archive.data["seen"]))
    return total_new


# ---------------------------------------------------------------------------
# Digest build & send
# ---------------------------------------------------------------------------
def _fresh_enough(rec: dict, days: int = 21) -> bool:
    try:
        seen_at = datetime.fromisoformat(rec["seen_at"])
        return (datetime.now(timezone.utc) - seen_at) <= timedelta(days=days)
    except Exception:
        return True


def select_topics(archive: Archive, cfg: ScoutConfig, count: int = 5) -> list[dict]:
    candidates = []
    for rec in archive.data["seen"].values():
        if rec.get("score", 0) < cfg.min_score:
            continue
        if not _fresh_enough(rec):
            continue
        if archive.was_sent(rec["id"], rec.get("fp", [])):
            continue
        candidates.append(rec)

    candidates.sort(key=lambda r: r.get("score", 0), reverse=True)

    picked: list[dict] = []
    for rec in candidates:
        if len(picked) >= count:
            break
        fp = rec.get("fp", [])
        if any(jaccard(fp, p.get("fp", [])) >= 0.45 for p in picked):
            continue  # same story from another outlet
        picked.append(rec)
    return picked


def build_digest(archive: Archive, cfg: ScoutConfig, count: int = 5,
                 use_llm: bool = True) -> tuple[list[str], list[dict], list[str]]:
    """Returns (messages, picked_live_records, used_evergreen_ids)."""
    now_fa = fa_date(tehran_now())
    topics = select_topics(archive, cfg, count)

    messages: list[str] = []
    messages.append(
        f"🗞 شکارچی خبرهای دنیای عطر — {now_fa}\n"
        f"سلام! امروز {fa_num(count)} موضوع ناب برای تولید محتوا برات پیدا کردم 👇\n"
        f"(آرشیو: {fa_num(len(archive.data['seen']))} خبر پایش‌شده | "
        f"تا حالا {fa_num(archive.data['stats']['digests_sent'])} دایجست ارسال شده)"
    )

    briefs: list[str] = []
    idx = 1
    for rec in topics:
        item = {
            "title": rec["title"], "url": rec.get("url", ""), "cat": rec.get("cat"),
            "publisher": rec.get("pub", ""), "score": rec.get("score", 0),
        }
        brief = build_brief(item, idx, count)
        if use_llm:
            polished = llm_polish(brief, rec["title"])
            if polished:
                brief = polished
        briefs.append(brief)
        idx += 1

    # backfill with evergreen facts if the live news didn't produce enough
    missing = count - len(topics)
    eg_used: list[str] = []
    if missing > 0:
        unused = [f for f in EVERGREEN_FACTS
                  if not archive.evergreen_used(f["id"])]
        random.shuffle(unused)
        for fact in unused[:missing]:
            briefs.append(build_evergreen_brief(fact, idx, count))
            eg_used.append(fact["id"])
            idx += 1

    messages.extend(briefs)
    messages.append(
        "💡 نکته: هر موضوع رو می‌تونی به ۱ ریلز ۶۰ ثانیه‌ای یا ۱ ویدیوی بلندتر "
        "تبدیل کنی. فردا ۵ موضوع تازه می‌فرستم — موفق باشی! 💪"
    )
    return messages, topics, eg_used


def digest_due(cfg: ScoutConfig, archive: Archive) -> bool:
    now = tehran_now()
    today = now.strftime("%Y-%m-%d")
    if archive.last_digest_date() == today:
        return False
    target = now.replace(hour=cfg.digest_hour, minute=cfg.digest_minute,
                         second=0, microsecond=0)
    return now >= target


def send_digest(archive: Archive, cfg: ScoutConfig, force: bool = False,
                preview: bool = False) -> bool:
    if not (force or digest_due(cfg, archive)):
        log.info("digest not due yet (Tehran time: %s)",
                 tehran_now().strftime("%H:%M"))
        return False

    messages, picked, eg_used = build_digest(archive, cfg)

    if preview:
        print("\n" + "=" * 70)
        for m in messages:
            print(m)
            print("-" * 70)
        print("(preview mode — nothing sent, no state changes)")
        return True

    if not cfg.telegram_ready:
        log.warning("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set — "
                    "digest built but NOT sent. Items stay unsent for later.")
        print("\n".join("\n" + "-" * 60 + "\n" + m for m in messages))
        return False

    try:
        bot = verify(cfg.bot_token)
        log.info("sending digest via @%s to %s", bot.get("username"), cfg.chat_id)
        for m in messages:
            send_text(cfg.bot_token, cfg.chat_id, m)
        archive.mark_sent(picked)
        for eid in eg_used:
            archive.mark_evergreen_used(eid)
        archive.set_last_digest(tehran_now().strftime("%Y-%m-%d"))
        archive.save()
        log.info("digest sent ✔ (%d live + %d evergreen topics)",
                 len(picked), len(eg_used))
        return True
    except TelegramError as exc:
        log.error("Telegram send failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Perfume News Scout")
    ap.add_argument("--single-run", action="store_true",
                    help="one crawl pass (+ digest if due), then exit")
    ap.add_argument("--digest-now", action="store_true",
                    help="crawl, then force today's digest immediately")
    ap.add_argument("--preview", action="store_true",
                    help="build & print today's digest without sending")
    ap.add_argument("--test-telegram", action="store_true")
    ap.add_argument("--whoami", action="store_true")
    args = ap.parse_args()

    cfg = ScoutConfig()

    if args.whoami:
        if not cfg.bot_token:
            sys.exit("TELEGRAM_BOT_TOKEN is not set.")
        print(whoami(cfg.bot_token))
        return

    if args.test_telegram:
        if not cfg.telegram_ready:
            sys.exit("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID are not set.")
        bot = verify(cfg.bot_token)
        send_text(cfg.bot_token, cfg.chat_id,
                  "✅ اتصال شکارچی خبر عطر برقرار شد!\n"
                  f"ربات: @{bot.get('username')}\n"
                  "از فردا هر روز ۵ موضوع ناب دریافت می‌کنی.")
        print("OK — test message sent.")
        return

    archive = Archive(cfg.state_file)

    if args.preview:
        crawl(archive, cfg)
        build_digest_preview(archive, cfg)
        return

    if args.digest_now:
        crawl(archive, cfg)
        send_digest(archive, cfg, force=True)
        archive.save()
        return

    if args.single_run:
        crawl(archive, cfg)
        send_digest(archive, cfg)
        archive.save()
        return

    # --- daemon mode ---------------------------------------------------
    log.info("starting scout daemon (digest at %02d:%02d Tehran)",
             cfg.digest_hour, cfg.digest_minute)
    while True:
        try:
            crawl(archive, cfg)
            send_digest(archive, cfg)
            archive.save()
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            log.exception("loop error: %s", exc)
        sleep_s = cfg.poll_minutes * 60 + random.uniform(-120, 180)
        log.info("sleeping %.0f min", sleep_s / 60)
        time.sleep(max(60, sleep_s))


def build_digest_preview(archive: Archive, cfg: ScoutConfig):
    messages, _, _ = build_digest(archive, cfg, use_llm=False)
    print("\n" + "=" * 70)
    for m in messages:
        print(m)
        print("-" * 70)


if __name__ == "__main__":
    main()
