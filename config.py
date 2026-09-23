"""
Configuration Manager for Instagram to Telegram Forwarder.
Loads settings from environment variables or .env file.
"""

import os
from dataclasses import dataclass
from typing import Optional
from pathlib import Path
from dotenv import load_dotenv

# Load .env if present
env_path = Path(".env")
if env_path.exists():
    load_dotenv(dotenv_path=env_path)


@dataclass
class Config:
    # Telegram settings
    telegram_bot_token: str
    telegram_chat_id: str

    # Instagram settings
    instagram_username: str
    instagram_session_file: Optional[str] = None
    instagram_cookies_file: Optional[str] = None
    instagram_login_user: Optional[str] = None
    instagram_login_pass: Optional[str] = None

    # Bot behavior settings
    check_interval_seconds: int = 300  # 5 minutes default
    max_posts_per_check: int = 5
    include_original_link: bool = True
    state_file_path: str = "state.json"
    download_dir: str = "downloads"

    @classmethod
    def from_env(cls) -> "Config":
        bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
        ig_username = os.getenv("INSTAGRAM_USERNAME", "").strip()

        missing = []
        if not bot_token:
            missing.append("TELEGRAM_BOT_TOKEN")
        if not chat_id:
            missing.append("TELEGRAM_CHAT_ID")
        if not ig_username:
            missing.append("INSTAGRAM_USERNAME")

        if missing:
            raise ValueError(
                f"Missing required environment variables: {', '.join(missing)}. "
                "Please configure them in your .env file or environment variables."
            )

        interval = int(os.getenv("CHECK_INTERVAL_SECONDS", "300"))
        max_posts = int(os.getenv("MAX_POSTS_PER_CHECK", "5"))
        include_link = os.getenv("INCLUDE_ORIGINAL_LINK", "true").lower() in ("true", "1", "yes")

        return cls(
            telegram_bot_token=bot_token,
            telegram_chat_id=chat_id,
            instagram_username=ig_username,
            instagram_session_file=os.getenv("INSTAGRAM_SESSION_FILE"),
            instagram_cookies_file=os.getenv("INSTAGRAM_COOKIES_FILE"),
            instagram_login_user=os.getenv("INSTAGRAM_LOGIN_USER"),
            instagram_login_pass=os.getenv("INSTAGRAM_LOGIN_PASS"),
            check_interval_seconds=interval,
            max_posts_per_check=max_posts,
            include_original_link=include_link,
            state_file_path=os.getenv("STATE_FILE_PATH", "state.json"),
            download_dir=os.getenv("DOWNLOAD_DIR", "downloads"),
        )
