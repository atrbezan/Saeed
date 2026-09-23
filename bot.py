"""
Main Instagram to Telegram Forwarder Bot.
Can run continuously (daemon) or as a single execution (for GitHub Actions / Cron).
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Set

from config import Config
from instagram_downloader import InstagramDownloader, InstagramPostItem
from telegram_poster import TelegramPoster

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("InstagramToTelegram")


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
        # Keep only the last 500 shortcodes to prevent file from growing indefinitely
        posted_list = list(posted)[-500:]
        data = {
            "last_check_utc": datetime.now(timezone.utc).isoformat(),
            "posted_shortcodes": posted_list,
        }
        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info(f"Recorded '{shortcode}' in state file.")

    def bulk_mark_posted(self, shortcodes: list[str]):
        posted = self.load_posted_ids()
        posted.update(shortcodes)
        posted_list = list(posted)[-500:]
        data = {
            "last_check_utc": datetime.now(timezone.utc).isoformat(),
            "posted_shortcodes": posted_list,
        }
        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)


class InstagramTelegramAgent:
    def __init__(self, config: Config):
        self.config = config
        self.state = StateManager(config.state_file_path)
        self.tg = TelegramPoster(
            bot_token=config.telegram_bot_token,
            chat_id=config.telegram_chat_id,
        )
        self.ig = InstagramDownloader(
            target_username=config.instagram_username,
            session_file=config.instagram_session_file,
            cookies_file=config.instagram_cookies_file,
            login_user=config.login_user if hasattr(config, "login_user") else config.instagram_login_user,
            login_pass=config.login_pass if hasattr(config, "login_pass") else config.instagram_login_pass,
            download_dir=config.download_dir,
        )

    def test_telegram_connection(self):
        """Check bot token and send a test message to the channel."""
        logger.info("Verifying Telegram Bot and Channel connection...")
        bot_info = self.tg.verify_bot()
        test_text = (
            f"✅ ربات اینستاگرام به تلگرام فعال شد!\n"
            f"🤖 نام ربات: @{bot_info.get('username')}\n"
            f"🎯 پیج هدف: https://instagram.com/{self.config.instagram_username}\n"
            f"⏰ زمان: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        self.tg.send_message(test_text)
        logger.info("Test message successfully sent to the Telegram channel!")

    def initialize_state(self):
        """Mark existing posts as already processed so old posts aren't sent."""
        logger.info(f"Initializing state for @{self.config.instagram_username}...")
        posts = self.ig.get_latest_posts(limit=self.config.max_posts_per_check * 2)
        shortcodes = [p.shortcode for p in posts]
        self.state.bulk_mark_posted(shortcodes)
        logger.info(f"Initialized state with {len(shortcodes)} existing posts. Next run will only send new ones.")

    def format_caption(self, item: InstagramPostItem) -> str:
        """Format caption with optional link to original Instagram post."""
        caption = item.caption or ""
        if self.config.include_original_link:
            link_footer = f"\n\n🔗 [مشاهده در اینستاگرام]({item.url})"
            caption = caption.strip() + link_footer
        return caption.strip()

    def post_to_telegram(self, item: InstagramPostItem):
        """Send downloaded media item to Telegram based on media type."""
        caption = self.format_caption(item)
        files = item.media_files

        if not files:
            logger.warning(f"No media files downloaded for post {item.shortcode}. Sending text only.")
            self.tg.send_message(f"{caption}\n\n{item.url}")
            return

        if len(files) == 1:
            media = files[0]
            if media["type"] == "video":
                logger.info(f"Sending video/reel {item.shortcode} to Telegram...")
                self.tg.send_video(video_path=media["path"], caption=caption, thumb_path=media.get("thumb"))
            else:
                logger.info(f"Sending photo {item.shortcode} to Telegram...")
                self.tg.send_photo(photo_path=media["path"], caption=caption)
        else:
            # Multi-media carousel / album
            logger.info(f"Sending album ({len(files)} items) {item.shortcode} to Telegram...")
            self.tg.send_media_group(media_files=files, caption=caption)

    def check_and_sync(self):
        """One cycle of checking Instagram and forwarding new posts."""
        logger.info(f"Checking for new posts from @{self.config.instagram_username}...")
        already_posted = self.state.load_posted_ids()
        recent_posts = self.ig.get_latest_posts(limit=self.config.max_posts_per_check)

        # Identify new posts
        new_posts = [p for p in recent_posts if p.shortcode not in already_posted]

        if not new_posts:
            logger.info("No new posts found.")
            return

        logger.info(f"Found {len(new_posts)} new post(s) to process!")

        # Process in chronological order (oldest first)
        new_posts.sort(key=lambda p: p.date_utc)

        for post in new_posts:
            shortcode = post.shortcode
            logger.info(f"Processing new post: {shortcode} ({post.date_utc})")
            try:
                # 1. Download
                item = self.ig.download_post(post)

                # 2. Upload to Telegram
                self.post_to_telegram(item)

                # 3. Mark as posted
                self.state.mark_posted(shortcode)

                # 4. Clean up downloaded files
                self.ig.cleanup_post_dir(shortcode)

                # Small delay between posts to prevent Telegram spam rate limit
                time.sleep(3)
            except Exception as e:
                logger.error(f"Failed to process post {shortcode}: {e}", exc_info=True)
                # Continue with other posts

    def run_daemon(self):
        """Continuously check Instagram at interval."""
        logger.info(f"Starting agent daemon. Interval: {self.config.check_interval_seconds}s")
        while True:
            try:
                self.check_and_sync()
            except Exception as e:
                logger.error(f"Error during sync cycle: {e}", exc_info=True)
            
            logger.info(f"Sleeping for {self.config.check_interval_seconds} seconds...")
            time.sleep(self.config.check_interval_seconds)


def main():
    parser = argparse.ArgumentParser(description="Instagram to Telegram Forwarder Bot")
    parser.add_argument("--single-run", action="store_true", help="Run once and exit (for Cron / GitHub Actions)")
    parser.add_argument("--init", action="store_true", help="Initialize state with current posts (don't send old posts)")
    parser.add_argument("--test-telegram", action="store_true", help="Send a test message to Telegram channel and exit")
    args = parser.parse_args()

    try:
        config = Config.from_env()
    except ValueError as e:
        logger.error(str(e))
        sys.exit(1)

    agent = InstagramTelegramAgent(config)

    if args.test_telegram:
        agent.test_telegram_connection()
        return

    if args.init:
        agent.initialize_state()
        return

    if args.single_run:
        agent.check_and_sync()
    else:
        agent.run_daemon()


if __name__ == "__main__":
    main()
