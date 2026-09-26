# -*- coding: utf-8 -*-
"""
Perfume News Scout — evergreen fact bank.

When a day's live news doesn't produce enough strong stories, the digest is
filled from these verified, always-interesting fragrance facts. Each fact is
used only once (tracked in the archive) so the daily 5 topics never repeat.

Add your own facts here — format is self-explanatory.
"""

from scout_scorer import (CAT_WEIRD_FACT, CAT_RECORD, CAT_BAN, CAT_CELEBRITY,
                          CAT_DUPE, CAT_GENERAL, CAT_SCANDAL)

EVERGREEN_FACTS = [
    {
        "id": "eg-chanel5-monroe",
        "cat": CAT_CELEBRITY,
        "title_en": "Marilyn Monroe: 'I wear only a few drops of Chanel No. 5 to bed'",
        "title_fa": "جواب افسانه‌ای مریلین مونرو وقتی پرسیدند شب‌ها چه می‌پوشی: فقط چند قطره شنل شماره ۵!",
        "fact": "در مصاحبه سال ۱۹۵۲ وقتی از مریلین مونرو پرسیدند «شب‌ها چه لباسی می‌پوشی؟» جواب داد: «فقط چند قطره شنل شماره ۵.» این جمله تبدیل به یکی از معروف‌ترین تبلیغات رایگان تاریخ عطر شد و فروش Chanel No.5 را برای همیشه تضمین کرد.",
    },
    {
        "id": "eg-ambergris",
        "cat": CAT_WEIRD_FACT,
        "title_en": "Ambergris: whale vomit worth thousands of dollars per kilo",
        "title_fa": "عنبر سائل: استفراغ نهنگ که کیلویی هزاران دلار می‌ارزد!",
        "fact": "عنبر سائل (Ambergris) ماده‌ای است که در دستگاه گوارش نهنگ عنبر تولید می‌شود و گاهی روی ساحل پیدا می‌شود. قیمتش تا کیلویی ده‌ها هزار دلار می‌رسد و در عطرهای لوکس استفاده می‌شود. پیداکننده‌های اتفاقیِ ساحلی یک‌شبه پولدار شده‌اند.",
    },
    {
        "id": "eg-most-expensive",
        "cat": CAT_RECORD,
        "title_en": "The most expensive perfume bottle ever: DKNY Golden Delicious at $1 million",
        "title_fa": "گران‌ترین شیشه عطر تاریخ: ۱ میلیون دلار با الماس و یاقوت!",
        "fact": "بطری DKNY Golden Delicious که با طراح جواهر مارتین کاتز ساخته شد، با ۲۹۰۹ سنگ قیمتی از جمله الماس و یاقوت زینت داده شده و قیمتش ۱ میلیون دلار بود. سود فروشش هم به خیریه رفت.",
    },
    {
        "id": "eg-sauvage-record",
        "cat": CAT_RECORD,
        "title_en": "Dior Sauvage: one of the best-selling men's fragrances of all time",
        "title_fa": "دیور ساواژ: طبق گزارش‌ها هر دقیقه چند بطری‌اش در جهان فروخته می‌شود!",
        "fact": "Dior Sauvage با بازی جانی دپ سال‌هاست یکی از پرفروش‌ترین عطرهای مردانه جهان است؛ گزارش‌های رسمی دیور می‌گویند در مقاطعی به‌طور میانگین هر ۳۰ ثانیه یک بطری ساواژ در دنیا فروخته شده. خیلی‌ها آن را «امضای بویایی نسل جدید» می‌دانند و بعضی‌ها از بس همه می‌زنند از آن فراری‌اند!",
    },
    {
        "id": "eg-musk-deer",
        "cat": CAT_BAN,
        "title_en": "Original musk came from a deer gland — and it's banned now",
        "title_fa": "مشک واقعی از غده آهوی مشک می‌آمد؛ امروزه تقریباً ممنوع است",
        "fact": "مشک طبیعی از غده آهوی مشک نر گرفته می‌شد و برای به دست آوردن یک کیلوی آن چندین آهو کشته می‌شد. امروز استفاده از مشک طبیعی تقریباً منسوخ و محدود شده و همه عطرهای تجاری از مشک مصنوعی استفاده می‌کنند.",
    },
    {
        "id": "eg-aventus-clones",
        "cat": CAT_DUPE,
        "title_en": "Creed Aventus and the billion-dollar clone war",
        "title_fa": "کرید اونتوس و جنگ کپی‌ها: عطری که یک صنعت کامل کپی از رویش ساخته",
        "fact": "Creed Aventus با قیمت بالای ۳۰۰ دلار آن‌قدر محبوب شد که یک ارتش کامل از کپی‌ها مثل Armaf Club de Nuit Intense Man و نسخه‌های لاطافه از روی آن ساخته شد؛ بعضی‌ها می‌گویند بازار کپی‌های آن از خود نسخه اصلی بزرگ‌تر شده!",
    },
    {
        "id": "eg-edt-vs-edp",
        "cat": CAT_WEIRD_FACT,
        "title_en": "EDT vs EDP: the biggest misconception in perfume",
        "title_fa": "بزرگ‌ترین باور غلط دنیای عطر: ادوتویلت ضعیف‌تر از ادوپرفیوم است؟",
        "fact": "خیلی‌ها فکر می‌کنند ادوپرفیوم همیشه قوی‌تر و ماندگارتر از ادوتویلت است، اما غلظت فقط بخشی از ماجراست؛ فرمولاسیون متفاوت است و گاهی نسخه سبک‌تر پخش و ماندگاری بهتری دارد. حتی گاهی اسم‌ها فقط بازاریابی‌اند!",
    },
    {
        "id": "eg-napoleon-4711",
        "cat": CAT_WEIRD_FACT,
        "title_en": "Napoleon reportedly used dozens of bottles of Eau de Cologne a month",
        "title_fa": "ناپلئون ماهی ده‌ها شیشه ادکلن مصرف می‌کرد!",
        "fact": "طبق روایت‌های تاریخی، ناپلئون بناپارت عاشق «او دو کلن» جان ماری فارینا بود و ماهانه ده‌ها بطری مصرف می‌کرد؛ می‌گویند بعد از جنگ روی بدن و دستمال‌هایش می‌ریخت. کلمه «کلن» هم از شهر کلن آلمان می‌آید.",
    },
    {
        "id": "eg-oakmoss-ifra",
        "cat": CAT_BAN,
        "title_en": "How IFRA restrictions changed classic perfumes forever",
        "title_fa": "چطور محدودیت‌های ایفرا عطرهای کلاسیک را برای همیشه عوض کرد؟",
        "fact": "استانداردهای ایفرا (IFRA) استفاده از موادی مثل اوک‌ماس (خزه بلوط) را محدود کرد؛ نتیجه این شد که بسیاری از عطرهای کلاسیک معروف مثل میتسوکو و شنل شماره ۱۹ به‌صورت رسمی ریفورموله شدند و دیگر آن بوی قدیمی را ندارند. بحث بین کلکسیونرها همیشه داغ است.",
    },
    {
        "id": "eg-angel-gourmand",
        "cat": CAT_GENERAL,
        "title_en": "Thierry Mugler's Angel invented the 'gourmand' category in 1992",
        "title_fa": "آنجل موگلر: اولین عطر خوراکی‌بوی تاریخ که اول تقریباً شکست خورد!",
        "fact": "وقتی در ۱۹۹۲ آنجل با بوی شکلات و کارامل و پشمک عرضه شد، منتقدان شوکه شدند؛ هیچ‌کس تا به حال عطر با بوی دسر نساخته بود. اول فروشش معمولی بود اما کم‌کم تبدیل به پدیده شد و دسته کاملی به نام «گورماند» ساخت که امروز نصف بازار را گرفته.",
    },
    {
        "id": "eg-chanel-deal",
        "cat": CAT_SCANDAL,
        "title_en": "Coco Chanel made a deal that cost her the fortune of Chanel No. 5",
        "title_fa": "قراردادی که باعث شد کوکو شنل از ثروت عطر خودش محروم بماند",
        "fact": "کوکو شنل در ۱۹۲۴ برای تولید انبوه شنل شماره ۵ با برادران ورتیمیر قرارداد بست و فقط سهم اقلیتی برای خودش نگه داشت. سال‌ها بعد جنگ و شکایت و مذاکره ادامه داشت؛ در نهایت خانواده ورتیمیر مالک کامل شدند و شنل سال‌ها علیه قرارداد خودش جنگید.",
    },
    {
        "id": "eg-skin-ph",
        "cat": CAT_WEIRD_FACT,
        "title_en": "Why the same perfume smells different on everyone",
        "title_fa": "چرا یک عطر روی پوست هر کسی بوی متفاوتی می‌دهد؟",
        "fact": "دمای بدن، چربی پوست، میکروبیوم، رژیم غذایی و حتی استرس باعث می‌شود یک عطر روی دو نفر کاملاً متفاوت بو بدهد. برای همین هیچ‌وقت نباید فقط بر اساس بوی عطر روی کاغذ یا پوست دیگران خرید کرد.",
    },
    {
        "id": "eg-zara-dupes",
        "cat": CAT_DUPE,
        "title_en": "Zara perfumes and the 'smells like luxury for $20' phenomenon",
        "title_fa": "عطرهای زارا: پدیده «بوی لوکس با ۲۰ دلار» که اینترنت را دیوانه کرده",
        "fact": "عطرهای زارا با همکاری جو مالون ساخته شدند و بعضی‌هایشان به شباهت عجیب به عطرهای چندصد دلاری معروف‌اند. ویدیوهای مقایسه‌ای آن‌ها در تیک‌تاک میلیون‌ها بازدید می‌گیرد و بحث «دوپ قانونی یا کپی؟» همیشه داغ است.",
    },
    {
        "id": "eg-civilized-laws",
        "cat": CAT_BAN,
        "title_en": "No-perfume zones: workplaces and airlines banning fragrance",
        "title_fa": "مناطق ممنوعه عطر: جاهایی که زدن عطر رسماً ممنوع است!",
        "fact": "در بعضی بیمارستان‌ها، ادارات دولتی کانادا و حتی برخی پروازها استفاده از عطر به‌خاطر حساسیت و آسم کارکنان ممنوع یا محدود شده. بحث «حق عطر زدن در برابر حق هوای پاک» یکی از جنجالی‌ترین بحث‌های سال‌های اخیر بوده است.",
    },
    {
        "id": "eg-baccarat-name",
        "cat": CAT_GENERAL,
        "title_en": "Baccarat Rouge 540: named after a crystal furnace temperature",
        "title_fa": "باکارا روژ ۵۴۰: اسمش از دمای کوره ذوب کریستال می‌آید!",
        "fact": "عدد ۵۴۰ در اسم عطر معروف باکارا روژ به دمای کوره‌ای اشاره دارد که کریستال قرمز باکارا در آن ذوب می‌شود. این عطر که با همکاری کریستال‌ساز ۲۵۰ ساله باکارا ساخته شد، به یکی از وایرال‌ترین عطرهای تاریخ اینستاگرام تبدیل شد.",
    },
]
