# -*- coding: utf-8 -*-
"""
Perfume News Scout — scoring & classification.

Scores every collected item for "content potential": controversy, weirdness,
records, bans, mistakes, viral moments. Pure keyword/heuristic scoring so the
agent runs anywhere with zero API costs.

Also provides title fingerprinting + Jaccard similarity used for deduplication.
"""

import re
from datetime import datetime, timezone
from typing import Optional

HTML_TAG_RE = re.compile(r"<[^>]+>")
TOKEN_RE = re.compile(r"[a-z0-9'’&$€£]+")

STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with",
    "at", "by", "from", "is", "are", "was", "were", "be", "as", "it", "its",
    "this", "that", "new", "over", "after", "about", "into", "how", "why",
    "what", "which", "who", "will", "can", "has", "have", "had", "not", "but",
}

# Words that prove the item is really about fragrance (vs. "fragrance-free wipes").
CORE_FRAGRANCE_WORDS = {
    "perfume", "perfumes", "perfumery", "fragrance", "fragrances", "cologne",
    "colognes", "parfum", "parfums", "eau", "scent", "scents", "oud", "attar",
    "perfumer", "nose",
}

# Titles containing these phrases are usually NOT about perfume as a product.
FALSE_POSITIVE_RE = re.compile(
    r"fragrance[- ]free|unscented|fragrance[- ]allergy|odor[- ]free", re.I)


def strip_html(text: Optional[str]) -> str:
    if not text:
        return ""
    text = HTML_TAG_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def tokenize(text: str) -> list[str]:
    return TOKEN_RE.findall(text.lower())


def fingerprint(title: str) -> list[str]:
    """Normalized token set used for fuzzy dedup."""
    toks = [t for t in tokenize(title) if t not in STOPWORDS]
    return sorted(set(toks))


def jaccard(fp_a: list[str], fp_b: list[str]) -> float:
    if not fp_a or not fp_b:
        return 0.0
    a, b = set(fp_a), set(fp_b)
    inter = len(a & b)
    if inter == 0:
        return 0.0
    return inter / len(a | b)


def clean_google_title(title: str) -> tuple[str, str]:
    """Split 'Headline - Publisher' produced by Google/Bing News."""
    title = title.strip()
    if " - " in title:
        head, publisher = title.rsplit(" - ", 1)
        if len(publisher) <= 40:
            return head.strip(), publisher.strip()
    return title, ""


def is_about_fragrance(title: str, summary: str, trusted_source: bool) -> bool:
    """Relevance guard: kill false positives like 'fragrance-free baby wipes'."""
    if trusted_source:
        return True
    text = f"{title} {summary}".lower()
    if FALSE_POSITIVE_RE.search(text):
        # allow only if a strong perfume word also appears
        strong = any(w in text for w in ("perfume", "parfum", "cologne", "eau de"))
        if not strong:
            return False
    toks = set(tokenize(text))
    return bool(toks & CORE_FRAGRANCE_WORDS)


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------
CAT_SCANDAL = "scandal"          # جنجالی / حاشیه
CAT_BAN = "ban"                  # ممنوعه / سلامت
CAT_DISCONTINUED = "discontinued"  # دیسکانتینیود / ریفورموله
CAT_BLUNDER = "blunder"          # اشتباه برند
CAT_BEHAVIOR = "behavior"        # رفتار عجیب افراد
CAT_RECORD = "record"            # رکورد فروش
CAT_WEIRD_FACT = "weird_fact"    # دانستنی عجیب
CAT_VIRAL = "viral"              # وایرال
CAT_DUPE = "dupe"                # دوپ و کپی
CAT_CELEBRITY = "celebrity"      # سلبریتی
CAT_GENERAL = "general"          # عمومی

CATEGORY_NAMES_FA = {
    CAT_SCANDAL: "🔥 جنجالی / حاشیه",
    CAT_BAN: "⛔ ممنوعه / سلامت",
    CAT_DISCONTINUED: "💔 دیسکانتینیود / ریفورموله",
    CAT_BLUNDER: "🤦 اشتباه برند بزرگ",
    CAT_BEHAVIOR: "🎭 رفتار عجیب",
    CAT_RECORD: "📈 رکورد و فروش",
    CAT_WEIRD_FACT: "🤯 دانستنی باورنکردنی",
    CAT_VIRAL: "🚀 وایرال",
    CAT_DUPE: "🎭 دوپ و کپی",
    CAT_CELEBRITY: "⭐ سلبریتی",
    CAT_GENERAL: "📰 خبر ویژه",
}

# (regex, weight, category) — first match decides the primary category,
# but every match adds to the score.
KEYWORD_RULES: list[tuple[str, int, str]] = [
    # Scandal / outrage
    (r"\b(scandal|lawsuit|sues|sued|accuse[d]?|allegation|exposed|exposé|"
     r"backlash|boycott|outrage|controvers|scam|fraud)\b", 30, CAT_SCANDAL),
    # Bans / regulation / health
    (r"\b(bans?|banned|banning|ban\b|recall(s|ed)?|ifra|regulat\w+|restrict\w+|"
     r"illegal|prohibit\w+|allergen\w*|warning|health risk|toxic|carcinogen\w*|"
     r"no-?perfume zones?|fragrance-?free policies)\b", 28, CAT_BAN),
    # Discontinued / reformulated
    (r"\b(discontinu\w+|reformulat\w+|out of production|no longer (made|sold)|"
     r"axe[d]?|halt(ed)? production|last bottles?)\b", 26, CAT_DISCONTINUED),
    # Brand mistakes
    (r"\b(mistake|blunder|flops?|flop|apolog\w+|pulled (ad|campaign)|withdraw\w+|"
     r"backtrack\w+|under fire|slammed|criticiz\w+)\b", 26, CAT_BLUNDER),
    # Odd behaviour of people (perfumers, founders, reviewers)
    (r"\b(arrest\w*|fired|quits?|steps down|dies|death of|hospitaliz\w+|"
     r"meltdown|rant|drama|feud|bizarre (behavi|incident)|eccentric)\b", 26, CAT_BEHAVIOR),
    # Records / sales
    (r"\b(best-?selling|bestseller|record (sales|profit)|sold out|selling out|"
     r"million bottles|billion|outsells?|most sold|top-?selling|sales surge)\b", 24, CAT_RECORD),
    # Weird / unbelievable facts
    (r"\b(weird(est)?|bizarre|strangest|unbelievable|insane|most expensive|"
     r"rarest|oldest|secret|hidden|myth|truth about|never knew|shocking|"
     r"surprising|mind-?blowing)\b", 22, CAT_WEIRD_FACT),
    # Viral
    (r"\b(viral|goes viral|tiktok|trending|everyone is (buying|wearing)|"
     r"the internet|millions of views)\b", 20, CAT_VIRAL),
    # Dupes / counterfeits
    (r"\b(dupe[sd]?|clone[sd]?|counterfeit|fake (perfume|fragrance)|knock-?off|"
     r"imitation|smells identical|identical scent)\b", 18, CAT_DUPE),
    # Celebrity
    (r"\b(kardashian|rihanna|billie eilish|ariana grande|david beckham|kanye|"
     r"cristiano ronaldo|zendaya|pharrell|selena gomez|justin bieber|messi)\b",
     14, CAT_CELEBRITY),
]

BIG_BRAND_RE = re.compile(
    r"\b(chanel|dior|tom ford|creed|maison francis kurkdjian|mfk|le labo|"
    r"jo malone|versace|gucci|ysl|saint laurent|armani|hermes|hermès|guerlain|"
    r"lattafa|armaf|diptyque|byredo|mugler|pacco rabanne|pac rabanne|"
    r"jean paul gaultier|valentino|prada|burberry|hugo boss|d&g|dolce)\b", re.I)

NUMBER_RE = re.compile(r"\$\s?\d|€\s?\d|£\s?\d|\b\d+\s?(million|billion|thousand|%)\b", re.I)


def score_item(title: str, summary: str, source_boost: int,
               published: Optional[datetime],
               now: Optional[datetime] = None) -> tuple[int, str, list[str]]:
    """Return (score, primary_category, matched_tags)."""
    now = now or datetime.now(timezone.utc)
    text = f"{title}. {summary}".lower()
    tags: list[str] = []
    score = 0
    primary: Optional[str] = None

    for pattern, weight, cat in KEYWORD_RULES:
        m = re.search(pattern, text)
        if m:
            score += weight
            tags.append(m.group(0).strip())
            if primary is None:
                primary = cat

    if BIG_BRAND_RE.search(text):
        score += 6
        tags.append("brand:big")
    if NUMBER_RE.search(text):
        score += 8
        tags.append("numbers")

    # Freshness bonus
    if published:
        try:
            age_h = (now - published).total_seconds() / 3600
            if age_h < 0:
                age_h = 0
            if age_h <= 24:
                score += 10
            elif age_h <= 72:
                score += 6
            elif age_h <= 24 * 7:
                score += 3
            elif age_h > 24 * 45:
                score -= 25  # stale news is useless for daily content
        except Exception:
            pass

    score += source_boost
    if primary is None:
        primary = CAT_GENERAL
    return score, primary, tags
