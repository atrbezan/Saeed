"""
Instagram to Telegram Auto Forwarder Bot
- Bypasses 666-second sleep (max_connection_attempts=1)
- Automatically sanitizes username (strips URL, slashes, and @)
- Fast embed scraper + fallback
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

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s]: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("IgToTgBot")


def clean_username(raw: str) -> str:
    if not raw:
        return "atrbezan"
    cleaned = re.sub(r'https?://(www\.)?instagram\.com/', '', raw)
    cleaned = cleaned.strip("/@ \t\n\r")
    return cleaned or "atrbezan"


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
        raw_ig = (
            os.getenv("INSTAGRAM_USERNAME", "").strip()
            or os.getenv("IG_USERNAME", "").strip()
            or "atrbezan"
        )
        ig_username = clean_username(raw_ig)

        if not bot_token:
            logger.error("❌ TELEGRAM_BOT_TOKEN یافت نشد!")
            sys.exit(1)

        if not chat_id.startswith("@") and not chat_id.startswith("-"):
            chat_id = f"@{chat_id}"

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
        except Exception:
            return set()

    def mark_posted(self, shortcode: str):
        posted = self.load_posted_ids()
        posted.add(shortcode)
        data = {
            "last_check_utc": datetime.now(timezone.utc).isoformat(),
            "posted_shortcodes": list(posted)[-500:],
        }
        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)


class TelegramPoster:
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.api_url = f"https://api.telegram.org/bot{self.bot_token}"
        self.session = requests.Session()

    def _request(self, method: str, data: Optional[dict] = None, files: Optional[dict] = None) -> dict:
        url = f"{self.api_url}/{method}"
        res = self.session.post(url, data=data, files=files, timeout=60)
        res_data = res.json()
        if not res_data.get("ok"):
            raise RuntimeError(f"Telegram API Error: {res_data.get('description')}")
        return res_data

    def split_caption(self, caption: str) -> tuple[str, Optional[str]]:
        if not caption:
            return "", None
        caption = caption.strip()
        if len(caption) <= 1024:
            return caption, None
        return caption[:1000].strip() + "\n\n...(ادامه در پیام بعد)", caption[1000:].strip()

    def send_photo(self, photo_path: str, caption: str = "") -> dict:
        c, extra = self.split_caption(caption)
        with open(photo_path, "rb") as f:
            res = self._request("sendPhoto", data={"chat_id": self.chat_id, "caption": c}, files={"photo": (os.path.basename(photo_path), f, "image/jpeg")})
        if extra:
            self._request("sendMessage", data={"chat_id": self.chat_id, "text": extra})
        return res

    def send_video(self, video_path: str, caption: str = "", thumb_path: Optional[str] = None) -> dict:
        c, extra = self.split_caption(caption)
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
            res = self._request("sendVideo", data={"chat_id": self.chat_id, "caption": c, "supports_streaming": True}, files=files)
        finally:
            for h in handlers:
                h.close()
        if extra:
            self._request("sendMessage", data={"chat_id": self.chat_id, "text": extra})
        return res

    def send_media_group(self, media_files: List[dict], caption: str = "") -> list[dict]:
        c, extra = self.split_caption(caption)
        results = []
        chunks = [media_files[i : i + 10] for i in range(0, len(media_files), 10)]

        for chunk_idx, chunk in enumerate(chunks):
            media_array = []
            files = {}
            handlers = []
            try:
                for idx, item in enumerate(chunk):
                    fkey = f"file_{idx}"
                    fh = open(item["path"], "rb")
                    handlers.append(fh)
                    mime = "video/mp4" if item.get("type") == "video" else "image/jpeg"
                    files[fkey] = (os.path.basename(item["path"]), fh, mime)

                    obj = {"type": item.get("type", "photo"), "media": f"attach://{fkey}"}
                    if chunk_idx == 0 and idx == 0 and c:
                        obj["caption"] = c
                    media_array.append(obj)

                res = self._request("sendMediaGroup", data={"chat_id": self.chat_id, "media": json.dumps(media_array)}, files=files)
                results.append(res)
            finally:
                for h in handlers:
                    h.close()
        if extra:
            self._request("sendMessage", data={"chat_id": self.chat_id, "text": extra})
        return results


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
        self.target_username = clean_username(target_username)
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
            max_connection_attempts=1,  # ❌ هرگز منتظر نمی‌ماند و بلافاصله اجرا می‌شود
        )

    def _fetch_shortcodes(self) -> List[str]:
        url = f"https://www.instagram.com/{self.target_username}/embed/"
        try:
            logger.info(f"در حال بررسی اینترفیس: {url}")
            res = requests.get(url, timeout=15)
            pattern = r'shortcode_media\\":\{.*?\\"shortcode\\":\\"([A-Za-z0-9_-]+)\\"'
            matches = re.findall(pattern, res.text)
            seen = set()
            shortcodes = [x for x in matches if not (x in seen or seen.add(x))]
            logger.info(f"یافت شد: {shortcodes}")
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
                    posts.append(instaloader.Post.from_shortcode(self.loader.context, sc))
                except Exception as e:
                    logger.warning(f"Error {sc}: {e}")
            if posts:
                return posts

        logger.info(f"Fallback get_posts برای @{self.target_username}")
        try:
            profile = instaloader.Profile.from_username(self.loader.context, self.target_username)
            for p in profile.get_posts():
                posts.append(p)
                if len(posts) >= limit:
                    break
        except Exception as e:
            logger.error(f"Fallback failed: {e}")
        return posts

    def download_post(self, post: instaloader.Post) -> InstagramPostItem:
        sc = post.shortcode
        post_dir = self.download_dir / sc
        if post_dir.exists():
            shutil.rmtree(post_dir, ignore_errors=True)
        post_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"دانلود {sc} ({post.typename})...")
        self.loader.download_post(post, target=sc)

        videos = sorted(glob.glob(str(post_dir / "*.mp4")))
        images = sorted(glob.glob(str(post_dir / "*.jpg")) + glob.glob(str(post_dir / "*.png")) + glob.glob(str(post_dir / "*.webp")))
        items = []

        if post.is_video and post.typename != "GraphSidecar":
            if videos:
                items.append({"type": "video", "path": videos[0], "thumb": images[0] if images else None})
        elif post.typename == "GraphSidecar":
            vbases = {os.path.splitext(v)[0] for v in videos}
            for v in videos:
                b = os.path.splitext(v)[0]
                items.append({"type": "video", "path": v, "thumb": (b + ".jpg") if os.path.exists(b + ".jpg") else None})
            for img in images:
                if os.path.splitext(img)[0] not in vbases:
                    items.append({"type": "photo", "path": img, "thumb": None})
            items.sort(key=lambda x: x["path"])
        else:
            if images:
                items.append({"type": "photo", "path": images[0], "thumb": None})

        return InstagramPostItem(
            shortcode=sc,
            url=f"https://www.instagram.com/p/{sc}/",
            is_video=post.is_video,
            typename=post.typename,
            caption=post.caption or "",
            date_utc=post.date_utc,
            media_files=items,
        )

    def cleanup_post_dir(self, shortcode: str):
        post_dir = self.download_dir / shortcode
        if post_dir.exists():
            shutil.rmtree(post_dir, ignore_errors=True)


class InstagramTelegramAgent:
    def __init__(self, config: Config):
        self.config = config
        self.state = StateManager(config.state_file_path)
        self.tg = TelegramPoster(config.telegram_bot_token, config.telegram_chat_id)
        self.ig = InstagramDownloader(config.instagram_username, config.download_dir)

    def format_caption(self, item: InstagramPostItem) -> str:
        caption = item.caption or ""
        if self.config.include_original_link:
            caption = caption.strip() + f"\n\n🔗 [مشاهده در اینستاگرام]({item.url})"
        return caption.strip()

    def post_to_telegram(self, item: InstagramPostItem):
        caption = self.format_caption(item)
        files = item.media_files
        if not files:
            return
        if len(files) == 1:
            if files[0]["type"] == "video":
                self.tg.send_video(files[0]["path"], caption=caption, thumb_path=files[0].get("thumb"))
            else:
                self.tg.send_photo(files[0]["path"], caption=caption)
        else:
            self.tg.send_media_group(files, caption=caption)

    def check_and_sync(self):
        logger.info(f"بررسی پیج @{self.config.instagram_username}...")
        already_posted = self.state.load_posted_ids()
        recent_posts = self.ig.get_latest_posts(limit=self.config.max_posts_per_check)

        new_posts = [p for p in recent_posts if p.shortcode not in already_posted]
        if not new_posts:
            logger.info("✅ همه پست‌ها قبلاً ارسال شده‌اند.")
            return

        logger.info(f"تعداد {len(new_posts)} پست جدید پیدا شد.")
        new_posts.sort(key=lambda p: p.date_utc)

        for post in new_posts:
            sc = post.shortcode
            try:
                item = self.ig.download_post(post)
                self.post_to_telegram(item)
                self.state.mark_posted(sc)
                self.ig.cleanup_post_dir(sc)
                logger.info(f"🎉 پست {sc} ارسال شد.")
                time.sleep(2)
            except Exception as e:
                logger.error(f"خطا در ارسال {sc}: {e}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--single-run", action="store_true")
    args = parser.parse_args()

    config = Config.load()
    agent = InstagramTelegramAgent(config)
    agent.check_and_sync()


if __name__ == "__main__":
    main()
