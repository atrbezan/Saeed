# -*- coding: utf-8 -*-
"""
Perfume News Scout — persistent archive & deduplication.

Everything lives in one small JSON file (committed back to the repo by the
GitHub Actions workflow) so the agent never sends the same story twice, even
though every run happens on a brand-new ephemeral machine.

State contents:
  seen         : url-hash -> {fp, title, src, seen_at, score}   (the archive)
  seen_order   : FIFO list of url-hashes used to cap the archive size
  sent_ids     : url-hashes already featured in a digest
  sent_fps     : fingerprints of sent stories (catches same-story/other-outlet)
  evergreen_sent: ids of built-in evergreen facts already used
  feeds        : per-feed scheduling/backoff metadata
  last_digest  : {date, sent_at}
  stats        : counters
"""

import hashlib
import json
import os
import random
import time
from datetime import datetime, timezone
from typing import Optional

from scout_scorer import fingerprint, jaccard

MAX_SEEN = 4000
MAX_SENT = 1200
MAX_SENT_FPS = 600
DEDUP_JACCARD = 0.70      # two titles >= this similarity are the same story
SIMILAR_SENT_JACCARD = 0.60


def url_hash(url: str) -> str:
    return hashlib.sha1(url.strip().lower().encode("utf-8")).hexdigest()[:16]


class Archive:
    def __init__(self, path: str):
        self.path = path
        self.data: dict = {
            "version": 1,
            "seen": {},
            "seen_order": [],
            "sent_ids": [],
            "sent_fps": {},
            "evergreen_sent": [],
            "feeds": {},
            "last_digest": {},
            "stats": {"total_collected": 0, "digests_sent": 0},
        }
        self.load()

    # ------------------------------------------------------------------ IO
    def load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as fh:
                    loaded = json.load(fh)
                if isinstance(loaded, dict) and loaded.get("version") == 1:
                    # merge over defaults so new keys appear on old files
                    self.data.update(loaded)
            except Exception as exc:  # corrupted file -> start fresh, keep going
                print(f"[archive] WARNING: could not read {self.path}: {exc}")

    def save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self.data, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, self.path)

    # ------------------------------------------------------------ ingestion
    def is_duplicate(self, url: str, title_fp: list[str]) -> bool:
        h = url_hash(url)
        if h in self.data["seen"]:
            return True
        for item in self.data["seen"].values():
            if jaccard(title_fp, item.get("fp", [])) >= DEDUP_JACCARD:
                return True
        return False

    def add_item(self, url: str, title: str, title_fp: list[str], source: str,
                 score: int, category: str, publisher: str,
                 published_iso: Optional[str]) -> Optional[dict]:
        """Register a new item. Returns the stored record, or None if duplicate."""
        if self.is_duplicate(url, title_fp):
            return None
        h = url_hash(url)
        record = {
            "id": h,
            "url": url,
            "title": title[:300],
            "fp": title_fp,
            "src": source,
            "pub": publisher,
            "cat": category,
            "score": score,
            "published": published_iso,
            "seen_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        self.data["seen"][h] = record
        self.data["seen_order"].append(h)
        self.data["stats"]["total_collected"] += 1
        # cap archive size (FIFO)
        while len(self.data["seen_order"]) > MAX_SEEN:
            old = self.data["seen_order"].pop(0)
            self.data["seen"].pop(old, None)
        return record

    # -------------------------------------------------------------- digest
    def was_sent(self, item_id: str, title_fp: list[str]) -> bool:
        if item_id in self.data["sent_ids"]:
            return True
        for fp in self.data["sent_fps"].values():
            if jaccard(title_fp, fp) >= SIMILAR_SENT_JACCARD:
                return True
        return False

    def mark_sent(self, items: list[dict]):
        for it in items:
            iid = it["id"]
            if iid not in self.data["sent_ids"]:
                self.data["sent_ids"].append(iid)
            self.data["sent_fps"][iid] = it.get("fp", [])
        self.data["sent_ids"] = self.data["sent_ids"][-MAX_SENT:]
        fps = self.data["sent_fps"]
        if len(fps) > MAX_SENT_FPS:
            for key in list(fps.keys())[: len(fps) - MAX_SENT_FPS]:
                fps.pop(key, None)
        self.data["stats"]["digests_sent"] += 1

    # ---------------------------------------------------- evergreen facts
    def evergreen_used(self, fact_id: str) -> bool:
        return fact_id in self.data["evergreen_sent"]

    def mark_evergreen_used(self, fact_id: str):
        if fact_id not in self.data["evergreen_sent"]:
            self.data["evergreen_sent"].append(fact_id)

    # ------------------------------------------------------ feed schedule
    def feed_due(self, feed_key: str, base_interval_min: int) -> bool:
        meta = self.data["feeds"].get(feed_key, {})
        next_ok = meta.get("next_ok", 0)
        return time.time() >= next_ok

    def feed_next_candidates(self, feeds: list, max_feeds: int) -> list:
        """Pick due feeds; if none are due, pick the ones closest to due."""
        due = [f for f in feeds if self.feed_due(f.key, f.base_interval_min)]
        if not due:
            due = sorted(feeds, key=lambda f: self.data["feeds"].get(f.key, {}).get("next_ok", 0))
        return due[:max_feeds]

    def feed_finished(self, feed_key: str, base_interval_min: int, success: bool,
                      new_items: int = 0):
        meta = self.data["feeds"].setdefault(feed_key, {"fails": 0})
        if success:
            meta["fails"] = 0
            mult = 1.0
            # adaptive: a feed that keeps returning nothing new is polled slower
            meta.setdefault("quiet_runs", 0)
            if new_items == 0:
                meta["quiet_runs"] += 1
                mult = min(2.0 ** min(meta["quiet_runs"], 2), 3.0)
            else:
                meta["quiet_runs"] = 0
            jitter = random.uniform(0.85, 1.25)
            meta["next_ok"] = time.time() + base_interval_min * 60 * jitter * mult
        else:
            meta["fails"] = meta.get("fails", 0) + 1
            backoff = 2 ** min(meta["fails"], 4)   # up to 16x on repeated failure
            meta["next_ok"] = time.time() + base_interval_min * 60 * backoff
        meta["last_run"] = datetime.now(timezone.utc).isoformat(timespec="seconds")

    # -------------------------------------------------------- last digest
    def last_digest_date(self) -> str:
        return self.data.get("last_digest", {}).get("date", "")

    def set_last_digest(self, date_str: str):
        self.data["last_digest"] = {
            "date": date_str,
            "sent_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
