# -*- coding: utf-8 -*-
"""
Perfume News Scout — Source definitions.

All sources are free RSS/Atom feeds (no API keys required):
  * Google News RSS  -> targeted searches for controversial/viral perfume news
  * Bing News RSS    -> secondary news coverage
  * Fragrantica RSS  -> unofficial but reliable mirror of fragrantica.com/news
  * Reddit RSS       -> r/fragrance community (best effort, may 403 on cloud IPs)
  * YouTube RSS      -> big fragrance channels (odd behaviour, viral reviewers)

Each feed declares a base polling interval (minutes). The crawler adds jitter
and per-feed backoff so the sources are hit very gently.
"""

from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import quote_plus

GOOGLE_NEWS_BASE = "https://news.google.com/rss/search"
BING_NEWS_BASE = "https://www.bing.com/news/search"
REDDIT_BASE = "https://www.reddit.com"
YOUTUBE_FEED = "https://www.youtube.com/feeds/videos.xml"


@dataclass
class FeedDef:
    key: str                 # unique id, stored in state
    kind: str                # rss | atom
    label: str               # human-readable source name
    url: str                 # final URL to fetch
    base_interval_min: int   # minutes between polite polls
    trusted: bool = False    # True = dedicated fragrance source (skips relevance guard)
    weight_boost: int = 0    # extra score for items coming from this source
    max_items: int = 25      # max entries to keep per fetch


def _gn(query: str, key: str, label: str, interval: int = 90) -> FeedDef:
    url = f"{GOOGLE_NEWS_BASE}?q={quote_plus(query)}&hl=en-US&gl=US&ceid=US:en"
    return FeedDef(key=key, kind="rss", label=label, url=url,
                   base_interval_min=interval)


def _bing(query: str, key: str, label: str, interval: int = 120) -> FeedDef:
    url = f"{BING_NEWS_BASE}?q={quote_plus(query)}&format=RSS"
    return FeedDef(key=key, kind="rss", label=label, url=url,
                   base_interval_min=interval)


def _reddit(sub: str, sort: str = "top", t: str = "day", interval: int = 180) -> FeedDef:
    url = f"{REDDIT_BASE}/r/{sub}/{sort}/.rss?t={t}&limit=25"
    return FeedDef(key=f"reddit:{sub}:{sort}", kind="atom",
                   label=f"Reddit r/{sub}", url=url,
                   base_interval_min=interval, trusted=True, weight_boost=4)


def _youtube(channel_id: str, name: str, interval: int = 240) -> FeedDef:
    url = f"{YOUTUBE_FEED}?channel_id={channel_id}"
    return FeedDef(key=f"yt:{channel_id}", kind="atom", label=f"YouTube: {name}",
                   url=url, base_interval_min=interval, trusted=True, weight_boost=3)


# ---------------------------------------------------------------------------
# Google News query sets — each one targets a different "spicy" angle.
# "when:14d" keeps results fresh; the freshness component of the score
# decides what is actually usable.
# ---------------------------------------------------------------------------
GOOGLE_QUERIES = [
    # 1. Scandals / lawsuits / outrage
    ("(perfume OR fragrance OR cologne) (scandal OR lawsuit OR sues OR accused "
     "OR exposed OR backlash OR boycott OR outrage) when:14d",
     "gn:scandal", "Google News — حاشیه و رسوایی"),

    # 2. Bans / recalls / regulations (IFRA, EU, allergy)
    ("(perfume OR fragrance) (banned OR banned-fragrance OR recall OR recalls "
     "OR IFRA OR regulation OR restricted OR allergen OR warning) when:14d",
     "gn:bans", "Google News — ممنوعیت و سلامت"),

    # 3. Discontinued / reformulated (huge engagement in the fragrance community)
    ("(perfume OR fragrance OR cologne) (discontinued OR reformulated OR "
     "reformulation OR \"out of production\") when:14d",
     "gn:discontinued", "Google News — دیسکانتینیود/ریفورموله"),

    # 4. Sales records / sold-out / viral moments
    ("(perfume OR fragrance OR cologne) (best-selling OR bestseller OR \"sold out\" "
     "OR \"record sales\" OR \"million bottles\" OR viral OR tiktok OR trending) when:14d",
     "gn:sales-viral", "Google News — فروش و وایرال"),

    # 5. Weird / unbelievable facts
    ("(perfume OR fragrance OR cologne) (weird OR bizarre OR strange OR unbelievable "
     "OR \"most expensive\" OR rarest OR secret OR \"never knew\" OR myth) when:14d",
     "gn:weird", "Google News — عجیب و باورنکردنی"),

    # 6. Brand mistakes / flops / pulled campaigns
    ("(perfume OR fragrance) (mistake OR apology OR apologizes OR flop OR flops "
     "OR blunder OR \"pulled ad\" OR withdrawn OR criticized) when:14d",
     "gn:blunder", "Google News — اشتباه برندها"),

    # 7. Perfumers / founders / CEOs behaving oddly
    ("(perfumer OR \"fragrance founder\" OR \"fragrance brand\" OR \"perfume brand\") "
     "(arrested OR fired OR quits OR drama OR weird OR controversy OR death OR dies) when:14d",
     "gn:people", "Google News — رفتار عجیب افراد"),

    # 8. Celebrity perfumes (Kardashians, Rihanna, …)
    ("(perfume OR fragrance) (Kardashian OR Rihanna OR \"Billie Eilish\" OR "
     "\"Ariana Grande\" OR \"David Beckham\" OR Kanye OR \"Cristiano Ronaldo\" OR "
     "Zara OR \"Kim Kardashian\") when:14d",
     "gn:celebrity", "Google News — عطر سلبریتی‌ها"),
]

BING_QUERIES = [
    ("(perfume OR fragrance) (scandal OR banned OR discontinued OR viral OR "
     "\"most expensive\" OR lawsuit OR recall)",
     "bing:spicy", "Bing News — موضوعات داغ"),
    ("(perfume OR cologne) (record OR bestseller OR \"sold out\" OR dupe OR counterfeit)",
     "bing:sales", "Bing News — فروش و دوپ"),
]

# Fragrantica news via an unofficial but daily-updated RSS mirror (GitHub Pages).
FRAGRANTICA_FEED = FeedDef(
    key="fragrantica:news", kind="rss", label="Fragrantica News",
    url="https://mrs-baotus.github.io/fragrantica-rss/news.xml",
    base_interval_min=120, trusted=True, weight_boost=6, max_items=30,
)

# Community pulse — best effort (Reddit often blocks cloud IPs; errors are tolerated).
REDDIT_FEEDS = [
    _reddit("fragrance", sort="top", t="day", interval=180),
    _reddit("fragrance", sort="hot", t="hour", interval=240),
]

# Big fragrance YouTube channels (odd behaviour, viral moments, bold claims).
# Easy to extend: add ("CHANNEL_ID", "Name") below.
YOUTUBE_CHANNELS = [
    ("UCzKrJ5NSA9o7RHYRG12kHZw", "Jeremy Fragrance"),
    ("UC6dLuMKBIj906bKTsgP3a5Q", "Jeremy Fragrance Germany"),
]
YOUTUBE_FEEDS = [_youtube(cid, name) for cid, name in YOUTUBE_CHANNELS]


def all_feeds() -> list[FeedDef]:
    feeds: list[FeedDef] = []
    for q, key, label in GOOGLE_QUERIES:
        feeds.append(_gn(q, key, label))
    for q, key, label in BING_QUERIES:
        feeds.append(_bing(q, key, label))
    feeds.append(FRAGRANTICA_FEED)
    feeds.extend(REDDIT_FEEDS)
    feeds.extend(YOUTUBE_FEEDS)
    return feeds
