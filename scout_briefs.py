# -*- coding: utf-8 -*-
"""
Perfume News Scout — Persian content-brief generator.

Turns a scored news item into a ready-to-shoot content brief:
hook, why it works, angles, and a step-by-step shooting plan designed for
the user's exact toolkit: one smartphone camera + their own voice-over +
AI-generated visuals + simple editing (CapCut etc.).

Optional: if SCOUT_LLM_API_KEY is set, an OpenAI-compatible model rewrites
the brief for extra polish. Falls back silently to templates on any error.
"""

import json
import os
import random
import re
from typing import Optional

import requests

from scout_scorer import (CAT_BAN, CAT_BEHAVIOR, CAT_BLUNDER, CAT_CELEBRITY,
                          CAT_DISCONTINUED, CAT_DUPE, CAT_GENERAL, CAT_RECORD,
                          CAT_SCANDAL, CAT_VIRAL, CAT_WEIRD_FACT,
                          CATEGORY_NAMES_FA)

FA_DIGITS = "۰۱۲۳۴۵۶۷۸۹"


def fa_num(n: int) -> str:
    return "".join(FA_DIGITS[int(d)] for d in str(n))


# ---------------------------------------------------------------------------
# Hook templates per category ({t} = cleaned English title)
# ---------------------------------------------------------------------------
HOOKS = {
    CAT_SCANDAL: [
        "این رسوایی دنیای عطرها رو تکون داده و تقریباً هیچ‌کس فارسی‌زبون درموردش نمی‌دونه…",
        "اگه عطر دوست داری، این ماجرا رو باید بشنوی؛ چون هنوز تموم نشده!",
        "برندی که همه می‌شناسیش، وسط یه حاشیه بزرگ گیر کرده…",
    ],
    CAT_BAN: [
        "این عطر/ماده ممکنه به‌زودی ممنوع بشه؛ شاید همین الان توی قفسه‌ته!",
        "یه خبر ممنوعیت اومده که خیلی از عطربازها هنوز نشنیدن…",
        "چیزی که الان می‌زنی، ممکنه فردا غیرقانونی باشه!",
    ],
    CAT_DISCONTINUED: [
        "این عطر داره برای همیشه ناپدید می‌شه؛ اگه دوستش داری، این آخرین فرصت‌هاست!",
        "خبر بد برای طرفدارها: دیگه قرار نیست این عطر رو بسازن…",
        "دیسکانتینیود شدن این عطر یعنی قیمتش احتمالاً قراره بپره بالا!",
    ],
    CAT_BLUNDER: [
        "یه برند بزرگ عطر یه اشتباه حسابی کرده و اینترنت داره آتیشش می‌زنه!",
        "این کمپانی فکر می‌کرد شاهکار کرده، ولی نتیجه یه فاجعه بود…",
        "اشتباهی که یه برند چندمیلیون دلاری مجبور شد رسماً بابتش عذرخواهی کنه!",
    ],
    CAT_BEHAVIOR: [
        "رفتار این آدمِ دنیای عطرها همه رو شوکه کرده!",
        "این اتفاقی که برای این چهره دنیای عطر افتاد، باورت نمی‌شه…",
        "پشت پرده دنیای عطرها یه خبر عجیب هست که کمتر جایی می‌شنوی!",
    ],
    CAT_RECORD: [
        "این عطر داره رکورد فروش تاریخ رو جابه‌جا می‌کنه؛ می‌دونی رازش چیه؟",
        "آمار فروش این عطر واقعاً دیوانه‌کننده‌ست!",
        "پرفروش‌ترین عطر این روزها کدومه و چرا همه دارن می‌خرنش؟",
    ],
    CAT_WEIRD_FACT: [
        "این دانستنی درباره عطرها رو اگه بشنوی، باور نمی‌کنی!",
        "یه حقیقت عجیب درباره دنیای عطرها که تو هیچ ویدیوی فارسی نشنیدی!",
        "این واقعیت درباره عطرها انقدر عجیبه که باید دو بار بشنویش!",
    ],
    CAT_VIRAL: [
        "این عطر تیک‌تاک رو منفجر کرده و همه دارن درموردش حرف می‌زنن!",
        "ویدیوهای این عطر میلیونی بازدید گرفتن؛ ولی واقعاً ارزشش رو داره؟",
        "وایرال‌ترین عطر این هفته رو پیدا کردم…",
    ],
    CAT_DUPE: [
        "این عطر ارزون، بوی اون عطر چندمیلیونی رو می‌ده؟ بریم آزمایش کنیم!",
        "دوپ یا کپی؟ این ماجرا مرز بین نبوغ و دزدی بویایی‌ه!",
        "پول چندمیلیونی بدی یا یه‌دهمش رو برای کپیش بدی؟",
    ],
    CAT_CELEBRITY: [
        "این سلبریتی وارد دنیای عطرها شده؛ شاهکاره یا فقط پول‌سازی؟",
        "عطر جدید این سلبریتی سر و صدا کرده…",
        "وقتی سلبریتی‌ها عطر می‌سازن، نتیجه چی می‌شه؟",
    ],
    CAT_GENERAL: [
        "این خبر دنیای عطرها رو باید هر عطربازی بدونه!",
        "یه خبر خاص از دنیای عطرها که امروز باید بشنوی!",
        "اتفاقی که تو دنیای عطرها افتاده، ارزش یه ویدیوی کامل رو داره!",
    ],
}

WHY = {
    CAT_SCANDAL: "موضوعات حاشیه‌ای و رسوایی همیشه بالاترین نرخ تعامل رو دارن؛ چون مردم دوست دارن واکنش نشون بدن، نظر بدن و برای بقیه بفرستن. این موضوع تو فارسی پوشش داده نشده، پس تو نفر اول می‌تونی باشی.",
    CAT_BAN: "موضوعات ممنوعیت و سلامت، حس فوریت و ترسِ از دست دادن می‌سازن؛ مخاطب ویدیو رو تا آخر می‌بینه چون می‌خواد بدونه آیا عطر خودش هم تحت تأثیره یا نه.",
    CAT_DISCONTINUED: "دیسکانتینیود شدن عطر برای کلکسیونرها و عطربازها حکم خبر فوری رو داره؛ حس کمیابی و ترس از گرون شدن، کامنت و سیو و شیر رو می‌ترکونه.",
    CAT_BLUNDER: "دیدن اشتباه برندهای بزرگ برای مخاطب جذابه؛ ترکیب «برند لوکس + خرابکاری» فرمول ثابت وایرال شدنه.",
    CAT_BEHAVIOR: "داستان‌های انسانی و عجیب درباره افراد مشهور دنیای عطر، هم کنجکاوی رو قلقلک می‌ده هم حس صمیمیت با مخاطب می‌سازه.",
    CAT_RECORD: "اعداد و رکوردها همیشه کنجکاوی‌برانگیزن؛ وقتی مخاطب بدونه یه عطر چقدر می‌فروشه، ناخودآگاه می‌خواد بدونه چرا.",
    CAT_WEIRD_FACT: "دانستنی‌های باورنکردنی بیشترین میزان «شیر شدن» رو دارن چون مخاطب دوست داره به بقیه هم بگه «این رو می‌دونستی؟».",
    CAT_VIRAL: "سوار شدن روی موج وایرال موجود، شانس دیده شدن ویدیوی تو رو چند برابر می‌کنه؛ الگوریتم خودش داره این موضوع رو هل می‌ده.",
    CAT_DUPE: "مقایسه و دوپ‌ها پربحث‌ترین موضوع کامنت‌هاست؛ همه دوست دارن تجربه خودشون رو بگن و سر اینکه کدوم بهتره بحث کنن.",
    CAT_CELEBRITY: "اسم سلبریتی خودش ترافیک میاره؛ ترکیبش با نقد صادقانه عطر، هم فن‌ها رو میاره هم منتقدها رو.",
    CAT_GENERAL: "این موضوع زاویه‌های جذابی برای روایت‌گری داره و مخاطب خاص عطر رو مستقیم هدف می‌گیره.",
}

ANGLES = {
    CAT_SCANDAL: [
        "روایت کامل ماجرا از اول تا الان (خط زمانی ساده با عکس و تیتر)",
        "واکنش‌های واقعی مردم تو شبکه‌های اجتماعی رو نشون بده و خودت هم نظر بده",
        "سوال جنجالی آخر ویدیو: «به نظرت برند مقصره یا نه؟» برای انفجار کامنت",
    ],
    CAT_BAN: [
        "اول بگو این ماده/عطر دقیقاً چیه و تو کدوم عطرها پیدا می‌شه",
        "دلیل علمی/سلامتی ممنوعیت رو ساده توضیح بده (با تصویرسازی هوش مصنوعی)",
        "به مخاطب بگو الان باید چیکار کنه؛ نتیجه‌گیری کاربردی = سیو بالا",
    ],
    CAT_DISCONTINUED: [
        "تاریخچه کوتاه عطر و اینکه چرا محبوب شد",
        "چرا دیسکانتینیود شد؟ (رسمی + شایعه‌ها)",
        "الان چقدر می‌ارزه و جایگزین‌هاش چیه؟ (مخاطب عاشق پیشنهاد جایگزینه)",
    ],
    CAT_BLUNDER: [
        "اول خود اشتباه رو نشون بده (اسکرین‌شات/عکس تبلیغ)",
        "چرا از نظر بازاریابی اشتباه بود؟ تحلیل ساده و خودمونی",
        "نمونه‌های مشابه تاریخی رو در ۱۰ ثانیه مرور کن",
    ],
    CAT_BEHAVIOR: [
        "داستان رو مثل یه روایت سینمایی تعریف کن: مقدمه، اوج، واکنش‌ها",
        "عکس‌ها و لحظه‌های کلیدی رو با تصاویر هوش مصنوعی بازسازی کن",
        "آخرش بگو این رفتار چه تاثیری روی برندش/بازار عطر گذاشت",
    ],
    CAT_RECORD: [
        "عدد رکورد رو بزرگ و درشت اول ویدیو نشون بده",
        "دلایل موفقیت رو یکی‌یکی تحلیل کن (بویایی، تبلیغات، قیمت…)",
        "مقایسه با رقبای نزدیکش؛ کدوم ارزش خرید بیشتری داره؟",
    ],
    CAT_WEIRD_FACT: [
        "با خود حقیقت شروع کن، بدون مقدمه‌چینی",
        "منبع و مدرکش رو نشون بده تا باورپذیر بشه",
        "یه حقیقت دومِ مرتبط بچسبون آخرش تا مخاطب فالوت کنه",
    ],
    CAT_VIRAL: [
        "اول چند اسکرین‌شات از ویدیوهای وایرال نشون بده",
        "خودت تست/تحلیل کن: واقعاً می‌ارزه یا هایپه؟",
        "پیش‌بینی کن موج بعدی چیه (مخاطب عاشق پیش‌بینی‌کننده‌هاست)",
    ],
    CAT_DUPE: [
        "تست کور: خودت و یه نفر دیگه بدون دونستن اسم بو کنید",
        "مقایسه قیمت، ماندگاری و پخش کنار هم (جدول ساده)",
        "حکم نهایی: پول اصلی رو بدیم یا نه؟",
    ],
    CAT_CELEBRITY: [
        "داستان ورود سلبریتی به دنیای عطر",
        "نظر عطربازها و منتقدها رو جمع کن",
        "خودت رک بگو: می‌ارزه یا فقط اسمه؟",
    ],
    CAT_GENERAL: [
        "ماجرای خبر رو ساده و روایت‌گونه تعریف کن",
        "یه زاویه شخصی اضافه کن: نظر خودت + تجربه‌ات",
        "با یه سوال باز تموم کن تا کامنت بگیری",
    ],
}

HOWTO = {
    "default": [
        "۱. دوربین موبایل رو عمودی بگیر، نور پنجره روبروت؛ ۵ ثانیه اول فقط قلاب رو با انرژی بگو.",
        "۲. متن خبر/عکس‌ها رو با اسکرین‌شات یا تصاویر ساخته‌شده با هوش مصنوعی (مثلاً همین خبر رو بده به یه ابزار تصویرساز) به‌صورت اینسرت لابه‌لای صحبتت بذار.",
        "۳. کات‌های سریع هر ۲-۳ ثانیه؛ زیرنویس خودکار فارسی حتماً بذار (۸۰٪ مخاطب بی‌صدا می‌بینه).",
        "۴. ۱۰ ثانیه آخر: جمع‌بندی + سوال از مخاطب + دعوت به فالو برای «هر روز یه خبر ناب عطر».",
        "۵. تایتل روی کاور: کوتاه، کنجکاوی‌برانگیز، با عدد یا علامت سوال.",
    ],
}

HASHTAG_BASE = "#عطر #پرفیوم #عطرباز #ادکلن #عطر_اصل #دانستنی #عطر_و_ادکلن"
HASHTAG_BY_CAT = {
    CAT_SCANDAL: " #حاشیه #رسوایی #خبر_داغ",
    CAT_BAN: " #ممنوعیت #سلامت #مراقبت",
    CAT_DISCONTINUED: " #دیسکانتینیود #کلکسیون #کمیاب",
    CAT_BLUNDER: " #بازاریابی #برند #اشتباه",
    CAT_BEHAVIOR: " #خبر_عجیب #پشت_پرده",
    CAT_RECORD: " #رکورد #پرفروش #فروش",
    CAT_WEIRD_FACT: " #دانستنی_عجیب #باورنکردنی #حقایق",
    CAT_VIRAL: " #وایرال #تیک_تاک #ترند",
    CAT_DUPE: " #دوپ #کپی_عطر #عطر_اقتصادی",
    CAT_CELEBRITY: " #سلبریتی #عطر_سلبریتی",
    CAT_GENERAL: " #خبر_عطر",
}


# ---------------------------------------------------------------------------
def build_brief(item: dict, index: int, total: int = 5) -> str:
    """item: {title, url, cat, pub(source label), publisher, score, tags}"""
    cat = item.get("cat", CAT_GENERAL)
    title = item.get("title", "")
    hook = random.choice(HOOKS.get(cat, HOOKS[CAT_GENERAL]))
    why = WHY.get(cat, WHY[CAT_GENERAL])
    angles = ANGLES.get(cat, ANGLES[CAT_GENERAL])
    howto = HOWTO["default"]
    tags = HASHTAG_BASE + HASHTAG_BY_CAT.get(cat, "")

    lines = []
    lines.append(f"🎯 موضوع {fa_num(index)} از {fa_num(total)} — {CATEGORY_NAMES_FA.get(cat, cat)}")
    lines.append(f"📌 تیتر: {title}")
    if item.get("publisher"):
        lines.append(f"📰 رسانه: {item['publisher']}")
    lines.append("")
    lines.append("🎣 قلاب ۳ ثانیه اول ویدیو:")
    lines.append(f"«{hook}»")
    lines.append("")
    lines.append("🧠 چرا این موضوع می‌ترکونه؟")
    lines.append(why)
    lines.append("")
    lines.append("🎯 زاویه‌های پیشنهادی:")
    for a in angles:
        lines.append(f"• {a}")
    lines.append("")
    lines.append("🎬 چطور بسازی؟ (موبایل + هوش مصنوعی)")
    for h in howto:
        lines.append(h)
    lines.append("")
    lines.append(f"🔗 منبع: {item.get('url', '')}")
    lines.append("")
    lines.append(f"✍️ کپشن پیشنهادی: نظرت رو کامنت کن 👇 {tags}")
    return "\n".join(lines)


def build_evergreen_brief(fact: dict, index: int, total: int = 5) -> str:
    cat = fact["cat"]
    why = WHY.get(cat, WHY[CAT_GENERAL])
    angles = ANGLES.get(cat, ANGLES[CAT_GENERAL])
    lines = []
    lines.append(f"🎯 موضوع {fa_num(index)} از {fa_num(total)} — {CATEGORY_NAMES_FA.get(cat, cat)} (دانستنی همیشه‌سبز)")
    lines.append(f"📌 {fact['title_fa']}")
    lines.append("")
    lines.append("🎣 قلاب ۳ ثانیه اول ویدیو:")
    lines.append(f"«{random.choice(HOOKS.get(cat, HOOKS[CAT_GENERAL]))}»")
    lines.append("")
    lines.append("📖 فکت کامل (همین رو با لحن خودت روایت کن):")
    lines.append(fact["fact"])
    lines.append("")
    lines.append("🧠 چرا این موضوع می‌ترکونه؟")
    lines.append(why)
    lines.append("")
    lines.append("🎯 زاویه‌های پیشنهادی:")
    for a in angles:
        lines.append(f"• {a}")
    lines.append("")
    lines.append("🎬 چطور بسازی؟ (موبایل + هوش مصنوعی)")
    for h in HOWTO["default"]:
        lines.append(h)
    lines.append("")
    lines.append(f"✍️ کپشن پیشنهادی: این رو می‌دونستی؟ 👇 {HASHTAG_BASE}{HASHTAG_BY_CAT.get(cat, '')}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Optional LLM polish (OpenAI-compatible). Only used if SCOUT_LLM_API_KEY set.
# ---------------------------------------------------------------------------
def llm_polish(brief_text: str, item_title: str) -> Optional[str]:
    api_key = os.getenv("SCOUT_LLM_API_KEY", "").strip()
    if not api_key:
        return None
    base_url = os.getenv("SCOUT_LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.getenv("SCOUT_LLM_MODEL", "gpt-4o-mini").strip()
    prompt = (
        "تو یک استراتژیست محتوای فارسی برای پیج اینستاگرام/یوتیوب عطر هستی. "
        "بریف زیر را بازنویسی کن: لحن صمیمی و پرانرژی، ساختار را حفظ کن، "
        "قلاب را جذاب‌تر و زاویه‌ها را خلاقانه‌تر کن. فقط متن نهایی را برگردان.\n\n"
        f"بریف:\n{brief_text}"
    )
    try:
        resp = requests.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "temperature": 0.8,
                "messages": [
                    {"role": "system", "content": "You rewrite Persian content briefs."},
                    {"role": "user", "content": prompt},
                ],
            },
            timeout=90,
        )
        resp.raise_for_status()
        text = resp.json()["choices"][0]["message"]["content"].strip()
        return text or None
    except Exception as exc:
        print(f"[llm] polish failed, using template: {exc}")
        return None
