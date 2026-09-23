"""
Telegram Poster Module
Handles communication with Telegram Bot API to send photos, videos, reels, and albums.
"""

import json
import logging
import mimetypes
import os
import time
from typing import Dict, List, Optional, Union
import requests

logger = logging.getLogger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org/bot"
MAX_CAPTION_LENGTH = 1024
MAX_MESSAGE_LENGTH = 4096


class TelegramPoster:
    def __init__(self, bot_token: str, chat_id: str, timeout: int = 120):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.timeout = timeout
        self.session = requests.Session()
        self.api_url = f"{TELEGRAM_API_BASE}{self.bot_token}"

    def _request(self, method: str, data: Optional[dict] = None, files: Optional[dict] = None) -> dict:
        url = f"{self.api_url}/{method}"
        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                response = self.session.post(url, data=data, files=files, timeout=self.timeout)
                res_data = response.json()
                if not res_data.get("ok"):
                    error_desc = res_data.get("description", "Unknown error")
                    error_code = res_data.get("error_code")
                    logger.error(f"Telegram API error [{error_code}]: {error_desc}")
                    # Handle rate limiting (429)
                    if error_code == 429:
                        retry_after = res_data.get("parameters", {}).get("retry_after", 10)
                        logger.warning(f"Rate limited by Telegram. Retrying after {retry_after}s...")
                        time.sleep(retry_after)
                        continue
                    raise RuntimeError(f"Telegram API error [{error_code}]: {error_desc}")
                return res_data
            except (requests.RequestException, json.JSONDecodeError) as e:
                logger.warning(f"Attempt {attempt}/{max_retries} failed for {method}: {e}")
                if attempt == max_retries:
                    raise
                time.sleep(2 * attempt)
        raise RuntimeError(f"Failed to execute {method} after {max_retries} attempts.")

    def verify_bot(self) -> dict:
        """Verify bot credentials and get bot info."""
        res = self._request("getMe")
        bot_user = res.get("result", {})
        logger.info(f"Connected to Telegram Bot: @{bot_user.get('username')} (ID: {bot_user.get('id')})")
        return bot_user

    def split_caption(self, caption: str) -> tuple[str, Optional[str]]:
        """
        Telegram captions for media (photos/videos) cannot exceed 1024 characters.
        If caption is longer, return (truncated_caption, extra_text).
        """
        if not caption:
            return "", None
        
        caption = caption.strip()
        if len(caption) <= MAX_CAPTION_LENGTH:
            return caption, None

        # Truncate to near 1000 chars at a newline or word boundary
        cut_idx = 1000
        last_newline = caption[:cut_idx].rfind("\n")
        if last_newline > 800:
            cut_idx = last_newline
        else:
            last_space = caption[:cut_idx].rfind(" ")
            if last_space > 800:
                cut_idx = last_space

        short_caption = caption[:cut_idx].strip() + "\n\n...(ادامه در پیام بعدی)"
        remaining_text = caption[cut_idx:].strip()
        return short_caption, remaining_text

    def send_message(self, text: str, reply_to_message_id: Optional[int] = None) -> dict:
        """Send a plain text message to the channel."""
        data = {
            "chat_id": self.chat_id,
            "text": text[:MAX_MESSAGE_LENGTH],
        }
        if reply_to_message_id:
            data["reply_to_message_id"] = reply_to_message_id
        return self._request("sendMessage", data=data)

    def send_photo(self, photo_path: str, caption: str = "") -> dict:
        """Send a single photo with caption to the channel."""
        short_caption, extra_text = self.split_caption(caption)
        data = {
            "chat_id": self.chat_id,
            "caption": short_caption,
        }

        with open(photo_path, "rb") as f:
            files = {"photo": (os.path.basename(photo_path), f, "image/jpeg")}
            res = self._request("sendPhoto", data=data, files=files)

        if extra_text:
            msg_id = res.get("result", {}).get("message_id")
            self.send_message(f"ادامه کپشن:\n\n{extra_text}", reply_to_message_id=msg_id)

        return res

    def send_video(self, video_path: str, caption: str = "", thumb_path: Optional[str] = None) -> dict:
        """Send a single video or reels with caption to the channel."""
        short_caption, extra_text = self.split_caption(caption)
        data = {
            "chat_id": self.chat_id,
            "caption": short_caption,
            "supports_streaming": True,
        }

        files = {}
        file_handlers = []
        try:
            vf = open(video_path, "rb")
            file_handlers.append(vf)
            files["video"] = (os.path.basename(video_path), vf, "video/mp4")

            if thumb_path and os.path.exists(thumb_path):
                tf = open(thumb_path, "rb")
                file_handlers.append(tf)
                files["thumbnail"] = (os.path.basename(thumb_path), tf, "image/jpeg")

            res = self._request("sendVideo", data=data, files=files)
        finally:
            for fh in file_handlers:
                fh.close()

        if extra_text:
            msg_id = res.get("result", {}).get("message_id")
            self.send_message(f"ادامه کپشن:\n\n{extra_text}", reply_to_message_id=msg_id)

        return res

    def send_media_group(self, media_files: List[dict], caption: str = "") -> list[dict]:
        """
        Send album / carousel of media items.
        Telegram limits media groups to 10 items per message;
        if more than 10 items, splits them into consecutive groups.
        """
        if not media_files:
            raise ValueError("media_files list cannot be empty")

        short_caption, extra_text = self.split_caption(caption)
        results = []

        # Split into chunks of 10
        chunks = [media_files[i:i + 10] for i in range(0, len(media_files), 10)]

        for chunk_idx, chunk in enumerate(chunks):
            media_array = []
            files = {}
            file_handlers = []

            try:
                for idx, item in enumerate(chunk):
                    file_key = f"file_{idx}"
                    file_path = item["path"]
                    media_type = item.get("type", "photo")

                    fh = open(file_path, "rb")
                    file_handlers.append(fh)
                    mime = "video/mp4" if media_type == "video" else "image/jpeg"
                    files[file_key] = (os.path.basename(file_path), fh, mime)

                    media_obj: Dict[str, Union[str, bool]] = {
                        "type": media_type,
                        "media": f"attach://{file_key}",
                    }

                    # Attach caption only to the first item of the very first chunk
                    if chunk_idx == 0 and idx == 0 and short_caption:
                        media_obj["caption"] = short_caption

                    if media_type == "video":
                        media_obj["supports_streaming"] = True
                        thumb_path = item.get("thumb")
                        if thumb_path and os.path.exists(thumb_path):
                            thumb_key = f"thumb_{idx}"
                            tfh = open(thumb_path, "rb")
                            file_handlers.append(tfh)
                            files[thumb_key] = (os.path.basename(thumb_path), tfh, "image/jpeg")
                            media_obj["thumbnail"] = f"attach://{thumb_key}"

                    media_array.append(media_obj)

                data = {
                    "chat_id": self.chat_id,
                    "media": json.dumps(media_array),
                }

                res = self._request("sendMediaGroup", data=data, files=files)
                results.append(res)
            finally:
                for fh in file_handlers:
                    fh.close()

            # Small delay between chunks
            if chunk_idx < len(chunks) - 1:
                time.sleep(1.5)

        if extra_text and results:
            first_msg = results[0].get("result", [{}])[0]
            msg_id = first_msg.get("message_id")
            self.send_message(f"ادامه کپشن:\n\n{extra_text}", reply_to_message_id=msg_id)

        return results
