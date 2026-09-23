"""
Instagram to Telegram Auto Forwarder Bot (All-in-One Standalone Version)
Zero-dependency beyond standard library + instaloader + requests.
Features:
- Instagram embed scraping (bypasses datacenter 429 blocks)
- Telegram media sender (video/reels, photos, albums/carousels)
- Smart caption formatting & splitting (>1024 chars)
- Fallback configuration (auto-detects channel @Atrbezan and username atrbezan)
"""

import argparse
import glob
import json
import logging
import os
import re
import shutil
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set, Union

import instaloader
import requests

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s]: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("IgToTgBot")


# ==============================================================================
# 1. CONFIGURATION
# ==============================================================================
@dataclass
class Config:
    telegram_bot_token: str
    telegram_chat_id: str
    instagram_username: str
    check_interval_seconds: int = 300
    max_posts_per_check: int = 5
    include_original_link: bool = True
    state_file_path: str = "state.json"
    download_dir: str = "downloads"

    @classmethod
    def load(cls) -> "Config":
        bot_token = (
            os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
            or os.getenv("BOT_TOKEN", "").strip()
            or os.getenv("TELEGRAM_TOKEN", "").strip()
        )
        chat_id = (
            os.getenv("TELEGRAM_CHAT_ID", "").strip()
            or os.getenv("TELEGRAM_CHANNEL_ID", "").strip()
            or os.getenv("CHANNEL_ID", "").strip()
            or "@Atrbezan"
        )
        ig_username = (
            os.getenv("INSTAGRAM_USERNAME", "").strip()
            or os.getenv("IG_USERNAME", "").strip()
            or "atrbezan"
        )

        if not bot_token:
            logger.error(
                "❌ خطای مهم: متغیر TELEGRAM_BOT_TOKEN یافت نشد! "
                "لطفاً در گیت‌هاب به Settings > Secrets and variables > Actions بروید "
                "و سکرت TELEGRAM_BOT_TOKEN را با توکن ربات تلگرامتان تعریف کنید."
            )
            sys.exit(1)

        if not chat_id.startswith("@") and not chat_id.startswith("-"):
            chat_id = f"@{chat_id}"

        ig_username = ig_username.lstrip("@").strip()

        logger.info(f"✅ تنظیمات بارگذاری شد: پیج={ig_username} | کانال={chat_id}")

        return cls(
            telegram_bot_token=bot_token,
            telegram_chat_id=chat_id,
            instagram_username=ig_username,
            check_interval_seconds=int(os.getenv("CHECK_INTERVAL_SECONDS", "300")),
            max_posts_per_check=int(os.getenv("MAX_POSTS_PER_CHECK", "5")),
            include_original_link=os.getenv("INCLUDE_ORIGINAL_LINK", "true").lower() in ("true", "1", "yes"),
            state_file_path=os.getenv("STATE_FILE_PATH", "state.json"),
            download_dir=os.getenv("DOWNLOAD_DIR", "downloads"),
        )


# ==============================================================================
# 2. STATE MANAGER
# ==============================================================================
class StateManager:
    def __init__(self, state_file_path: str):
        self.file_path = Path(state_file_path)

    def load_posted_ids(self) -> Set[str]:
        if not self.file_path.exists():
            return set()
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return set(data.get("posted_shortcodes", []))
        except Exception as e:
            logger.warning(f"Could not load state from {self.file_path}: {e}")
            return set()

    def mark_posted(self, shortcode: str):
        posted = self.load_posted_ids()
        posted.add(shortcode)
        posted_list = list(posted)[-500:]
        data = {
            "last_check_utc": datetime.now(timezone.utc).isoformat(),
            "posted_shortcodes": posted_list,
        }
        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info(f"✅ پست {shortcode} در تاریخچه ثبت شد.")


# ==============================================================================
# 3. TELEGRAM POSTER
# ==============================================================================
class TelegramPoster:
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.api_url = f"https://api.telegram.org/bot{self.bot_token}"
        self.session = requests.Session()

    def _request(self, method: str, data: Optional[dict] = None, files: Optional[dict] = None) -> dict:
        url = f"{self.api_url}/{method}"
        for attempt in range(1, 4):
            try:
                res = self.session.post(url, data=data, files=files, timeout=90)
                res_data = res.json()
                if not res_data.get("ok"):
                    error_desc = res_data.get("description", "Unknown error")
                    error_code = res_data.get("error_code")
                    logger.error(f"Telegram API Error [{error_code}]: {error_desc}")

                    if error_code == 401:
                        logger.error("❌ توکن ربات تلگرام اشتباه است! لطفاً توکن @BotFather را چک کنید.")
                    elif error_code == 400 and ("chat not found" in error_desc.lower() or "not enough rights" in error_desc.lower()):
                        logger.error("❌ کانال پیدا نشد یا ربات ادمین نیست! مطمئن شوید ربات در کانال Admin شده و مجوز Post Messages دارد.")

                    if error_code == 429:
                        wait_sec = res_data.get("parameters", {}).get("retry_after", 10)
                        logger.warning(f"Rate limited by Telegram. Waiting {wait_sec}s...")
                        time.sleep(wait_sec)
                        continue

                    raise RuntimeError(f"Telegram API error [{error_code}]: {error_desc}")
                return res_data
            except requests.RequestException as e:
                logger.warning(f"Telegram request failed (attempt {attempt}/3): {e}")
                time.sleep(2 * attempt)
        raise RuntimeError(f"Telegram {method} failed after 3 attempts.")

    def split_caption(self, caption: str) -> tuple[str, Optional[str]]:
        if not caption:
            return "", None
        caption = caption.strip()
        if len(caption) <= 1024:
            return caption, None

        cut_idx = 1000
        last_nl = caption[:cut_idx].rfind("\n")
        if last_nl > 700:
            cut_idx = last_nl
        short_cap = caption[:cut_idx].strip() + "\n\n...(ادامه در پیام بعد)"
        extra = caption[cut_idx:].strip()
        return short_cap, extra

    def send_message(self, text: str, reply_to_message_id: Optional[int] = None) -> dict:
        data = {"chat_id": self.chat_id, "text": text[:4000]}
        if reply_to_message_id:
            data["reply_to_message_id"] = reply_to_message_id
        return self._request("sendMessage", data=data)

    def send_photo(self, photo_path: str, caption: str = "") -> dict:
        short_caption, extra_text = self.split_caption(caption)
        data = {"chat_id": self.chat_id, "caption": short_caption}
        with open(photo_path, "rb") as f:
            files = {"photo": (os.path.basename(photo_path), f, "image/jpeg")}
            res = self._request("sendPhoto", data=data, files=files)
        if extra_text:
            msg_id = res.get("result", {}).get("message_id")
            self.send_message(f"ادامه کپشن:\n\n{extra_text}", reply_to_message_id=msg_id)
        return res

    def send_video(self, video_path: str, caption: str = "", thumb_path: Optional[str] = None) -> dict:
        short_caption, extra_text = self.split_caption(caption)
        data = {"chat_id": self.chat_id, "caption": short_caption, "supports_streaming": True}
        files = {}
        handlers = []
        try:
            vf = open(video_path, "rb")
            handlers.append(vf)
            files["video"] = (os.path.basename(video_path), vf, "video/mp4")
            if thumb_path and os.path.exists(thumb_path):
                tf = open(thumb_path, "rb")
                handlers.append(tf)
                files["thumbnail"] = (os.path.basename(thumb_path), tf, "image/jpeg")
            res = self._request("sendVideo", data=data, files=files)
        finally:
            for h in handlers:
                h.close()
        if extra_text:
            msg_id = res.get("result", {}).get("message_id")
            self.send_message(f"ادامه کپشن:\n\n{extra_text}", reply_to_message_id=msg_id)
        return res

    def send_media_group(self, media_files: List[dict], caption: str = "") -> list[dict]:
        short_caption, extra_text = self.split_caption(caption)
        results = []
        chunks = [media_files[i : i + 10] for i in range(0, len(media_files), 10)]

        for chunk_idx, chunk in enumerate(chunks):
            media_array = []
            files = {}
            handlers = []
            try:
                for idx, item in enumerate(chunk):
                    file_key = f"file_{idx}"
                    file_path = item["path"]
                    mtype = item.get("type", "photo")
                    fh = open(file_path, "rb")
                    handlers.append(fh)
                    mime = "video/mp4" if mtype == "video" else "image/jpeg"
                    files[file_key] = (os.path.basename(file_path), fh, mime)

                    obj = {"type": mtype, "media": f"attach://{file_key}"}
                    if chunk_idx == 0 and idx == 0 and short_caption:
                        obj["caption"] = short_caption
                    if mtype == "video":
                        obj["supports_streaming"] = True
                        if item.get("thumb") and os.path.exists(item["thumb"]):
                            tkey = f"thumb_{idx}"
                            tfh = open(item["thumb"], "rb")
                            handlers.append(tfh)
                            files[tkey] = (os.path.basename(item["thumb"]), tfh, "image/jpeg")
                            obj["thumbnail"] = f"attach://{tkey}"

                    media_array.append(obj)

                data = {"chat_id": self.chat_id, "media": json.dumps(media_array)}
                res = self._request("sendMediaGroup", data=data, files=files)
                results.append(res)
            finally:
                for h in handlers:
                    h.close()
            if chunk_idx < len(chunks) - 1:
                time.sleep(1.5)

        if extra_text and results:
            msg_id = results[0].get("result", [{}])[0].get("message_id")
            self.send_message(f"ادامه کپشن:\n\n{extra_text}", reply_to_message_id=msg_id)

        return results


# ==============================================================================
# 4. INSTAGRAM DOWNLOADER
# ==============================================================================
@dataclass
class InstagramPostItem:
    shortcode: str
    url: str
    is_video: bool
    typename: str
    caption: str
    date_utc: datetime
    media_files: List[dict] = field(default_factory=list)


class InstagramDownloader:
    def __init__(self, target_username: str, download_dir: str = "downloads"):
        self.target_username = target_username.lstrip("@").strip()
        self.download_dir = Path(download_dir).resolve()
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.loader = instaloader.Instaloader(
            dirname_pattern=str(self.download_dir / "{target}"),
            filename_pattern="{shortcode}_{date_utc:%Y%m%d_%H%M%S}",
            download_pictures=True,
            download_videos=True,
            download_video_thumbnails=True,
            download_geotags=False,
            download_comments=False,
            save_metadata=False,
            compress_json=False,
            post_metadata_txt_pattern="",
        )

    def _fetch_shortcodes(self) -> List[str]:
        url = f"https://www.instagram.com/{self.target_username}/embed/"
        try:
            logger.info(f"در حال بررسی پیج اینستاگرام از طریق اینترفیس عمومی: {url}")
            res = requests.get(url, timeout=20)
            if res.status_code == 200:
                pattern = r'shortcode_media\\":\{.*?\\"shortcode\\":\\"([A-Za-z0-9_-]+)\\"'
                matches = re.findall(pattern, res.text)
                seen = set()
                shortcodes = [x for x in matches if not (x in seen or seen.add(x))]
                logger.info(f"تعداد {len(shortcodes)} پست اخیر با موفقیت یافت شد: {shortcodes}")
                return shortcodes
        except Exception as e:
            logger.warning(f"Embed check error: {e}")
        return []

    def get_latest_posts(self, limit: int = 5) -> List[instaloader.Post]:
        shortcodes = self._fetch_shortcodes()
        posts = []
        if shortcodes:
            for sc in shortcodes[:limit]:
                try:
                    p = instaloader.Post.from_shortcode(self.loader.context, sc)
                    posts.append(p)
                except Exception as e:
                    logger.warning(f"Could not load post {sc}: {e}")
            if posts:
                return posts

        # Fallback to direct Profile
        try:
            profile = instaloader.Profile.from_username(self.loader.context, self.target_username)
            for p in profile.get_posts():
                posts.append(p)
                if len(posts) >= limit:
                    break
            return posts
        except Exception as e:
            logger.error(f"Fallback to Profile.get_posts failed: {e}")
            return posts

    def download_post(self, post: instaloader.Post) -> InstagramPostItem:
        sc = post.shortcode
        post_dir = self.download_dir / sc
        if post_dir.exists():
            shutil.rmtree(post_dir, ignore_errors=True)
        post_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"در حال دانلود پست {sc} ({post.typename})...")
        self.loader.download_post(post, target=sc)

        videos = sorted(glob.glob(str(post_dir / "*.mp4")))
        images = sorted(
            glob.glob(str(post_dir / "*.jpg"))
            + glob.glob(str(post_dir / "*.png"))
            + glob.glob(str(post_dir / "*.webp"))
        )
        media_items = []

        if post.is_video and post.typename != "GraphSidecar":
            if videos:
                thumb = images[0] if images else None
                media_items.append({"type": "video", "path": videos[0], "thumb": thumb})
        elif post.typename == "GraphSidecar":
            video_bases = {os.path.splitext(v)[0] for v in videos}
            for v in videos:
                base = os.path.splitext(v)[0]
                thumb = (base + ".jpg") if os.path.exists(base + ".jpg") else None
                media_items.append({"type": "video", "path": v, "thumb": thumb})
            for img in images:
                base = os.path.splitext(img)[0]
                if base not in video_bases:
                    media_items.append({"type": "photo", "path": img, "thumb": None})
            media_items.sort(key=lambda x: x["path"])
        else:
            if images:
                media_items.append({"type": "photo", "path": images[0], "thumb": None})

        return InstagramPostItem(
            shortcode=sc,
            url=f"https://www.instagram.com/p/{sc}/",
            is_video=post.is_video,
            typename=post.typename,
            caption=post.caption or "",
            date_utc=post.date_utc,
            media_files=media_items,
        )

    def cleanup_post_dir(self, shortcode: str):
        post_dir = self.download_dir / shortcode
        if post_dir.exists():
            shutil.rmtree(post_dir, ignore_errors=True)


# ==============================================================================
# 5. AGENT ORCHESTRATOR
# ==============================================================================
class InstagramTelegramAgent:
    def __init__(self, config: Config):
        self.config = config
        self.state = StateManager(config.state_file_path)
        self.tg = TelegramPoster(config.telegram_bot_token, config.telegram_chat_id)
        self.ig = InstagramDownloader(config.instagram_username, config.download_dir)

    def format_caption(self, item: InstagramPostItem) -> str:
        caption = item.caption or ""
        if self.config.include_original_link:
            link = f"\n\n🔗 [مشاهده در اینستاگرام]({item.url})"
            caption = caption.strip() + link
        return caption.strip()

    def post_to_telegram(self, item: InstagramPostItem):
        caption = self.format_caption(item)
        files = item.media_files
        if not files:
            logger.warning(f"فایل مدیایی برای {item.shortcode} دانلود نشد. ارسال متن...")
            self.tg.send_message(f"{caption}\n\n{item.url}")
            return

        if len(files) == 1:
            media = files[0]
            if media["type"] == "video":
                logger.info(f"ارسال ویدیوی ریلز {item.shortcode} به تلگرام...")
                self.tg.send_video(media["path"], caption=caption, thumb_path=media.get("thumb"))
            else:
                logger.info(f"ارسال تصویر {item.shortcode} به تلگرام...")
                self.tg.send_photo(media["path"], caption=caption)
        else:
            logger.info(f"ارسال آلبوم اسلایدی ({len(files)} آیتم) {item.shortcode} به تلگرام...")
            self.tg.send_media_group(files, caption=caption)

    def check_and_sync(self):
        logger.info(f"در حال بررسی پست‌های جدید پیج @{self.config.instagram_username}...")
        already_posted = self.state.load_posted_ids()
        recent_posts = self.ig.get_latest_posts(limit=self.config.max_posts_per_check)

        new_posts = [p for p in recent_posts if p.shortcode not in already_posted]
        if not new_posts:
            logger.info("✅ هیچ پست جدیدی وجود ندارد (همه قبلاً ارسال شده‌اند).")
            return

        logger.info(f"تعداد {len(new_posts)} پست جدید پیدا شد! شروع پردازش...")
        new_posts.sort(key=lambda p: p.date_utc)

        for post in new_posts:
            sc = post.shortcode
            try:
                item = self.ig.download_post(post)
                self.post_to_telegram(item)
                self.state.mark_posted(sc)
                self.ig.cleanup_post_dir(sc)
                logger.info(f"🎉 پست {sc} با موفقیت در تلگرام منتشر شد!")
                time.sleep(3)
            except Exception as e:
                logger.error(f"خطا در ارسال پست {sc}: {e}")

    def run_daemon(self):
        logger.info(f"ربات در حال اجراست (فاصله بررسی: {self.config.check_interval_seconds} ثانیه)...")
        while True:
            try:
                self.check_and_sync()
            except Exception as e:
                logger.error(f"خطا در بررسی دوره‌ای: {e}")
            time.sleep(self.config.check_interval_seconds)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--single-run", action="store_true", help="Run once and exit (for GitHub Actions)")
    args = parser.parse_args()

    config = Config.load()
    agent = InstagramTelegramAgent(config)

    if args.single_run:
        agent.check_and_sync()
    else:
        agent.run_daemon()


if __name__ == "__main__":
    main()
