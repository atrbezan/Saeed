"""
Instagram Downloader Module
Uses Instaloader and yt-dlp to fetch and download posts, reels, and carousels.
Supports both public profiles and authenticated sessions (session file or cookies).
"""

import glob
import http.cookiejar
import logging
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import instaloader

logger = logging.getLogger(__name__)


@dataclass
class InstagramPostItem:
    shortcode: str
    url: str
    is_video: bool
    typename: str  # 'GraphImage', 'GraphVideo', 'GraphSidecar'
    caption: str
    date_utc: datetime
    media_files: List[dict] = field(default_factory=list)
    # media_files structure:
    # [{"type": "photo"|"video", "path": str, "thumb": Optional[str]}]


class InstagramDownloader:
    def __init__(
        self,
        target_username: str,
        session_file: Optional[str] = None,
        cookies_file: Optional[str] = None,
        login_user: Optional[str] = None,
        login_pass: Optional[str] = None,
        download_dir: str = "downloads",
    ):
        self.target_username = target_username
        self.session_file = session_file
        self.cookies_file = cookies_file
        self.login_user = login_user
        self.login_pass = login_pass
        self.download_dir = Path(download_dir)
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
            post_metadata_txt_pattern="",  # Do not write txt captions
        )

        self._authenticate()

    def _authenticate(self):
        """Authenticate using session file, cookies file, or user/pass if provided."""
        # 1. Try session file
        if self.session_file and os.path.exists(self.session_file):
            try:
                username = self.login_user or self.target_username
                self.loader.load_session_from_file(username, self.session_file)
                logger.info(f"Loaded Instagram session from {self.session_file}")
                return
            except Exception as e:
                logger.warning(f"Failed to load session file: {e}")

        # 2. Try cookies file (Netscape format)
        if self.cookies_file and os.path.exists(self.cookies_file):
            try:
                cj = http.cookiejar.MozillaCookieJar(self.cookies_file)
                cj.load(ignore_discard=True, ignore_expires=True)
                self.loader.context._session.cookies.update(cj)
                logger.info(f"Loaded Instagram cookies from {self.cookies_file}")
                return
            except Exception as e:
                logger.warning(f"Failed to load cookies file: {e}")

        # 3. Try direct login (least recommended due to 2FA / checkpoints)
        if self.login_user and self.login_pass:
            try:
                self.loader.login(self.login_user, self.login_pass)
                logger.info(f"Logged in to Instagram as {self.login_user}")
                # Save session for next time
                session_target = self.session_file or f"session_{self.login_user}"
                self.loader.save_session_to_file(session_target)
                return
            except Exception as e:
                logger.warning(f"Login failed: {e}")

        logger.info("Running in anonymous mode (public profile access).")

    def get_latest_posts(self, limit: int = 5) -> List[instaloader.Post]:
        """Fetch the most recent posts from the target profile."""
        try:
            profile = instaloader.Profile.from_username(self.loader.context, self.target_username)
            posts = []
            for post in profile.get_posts():
                posts.append(post)
                if len(posts) >= limit:
                    break
            logger.info(f"Found {len(posts)} recent post(s) for @{self.target_username}")
            return posts
        except instaloader.exceptions.ProfileNotExistsException:
            logger.error(f"Instagram profile @{self.target_username} does not exist.")
            raise
        except instaloader.exceptions.LoginRequiredException:
            logger.error(
                "Instagram requires login to view this profile. Please provide a session or cookies file."
            )
            raise
        except Exception as e:
            logger.error(f"Error fetching posts for @{self.target_username}: {e}")
            raise

    def download_post(self, post: instaloader.Post) -> InstagramPostItem:
        """Download post media and return formatted InstagramPostItem."""
        shortcode = post.shortcode
        post_url = f"https://www.instagram.com/p/{shortcode}/"
        post_dir = self.download_dir / shortcode

        # Clean previous attempts if any
        if post_dir.exists():
            shutil.rmtree(post_dir)
        post_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Downloading post {shortcode} ({post.typename}) to {post_dir}...")
        self.loader.download_post(post, target=str(post_dir))

        # Inspect downloaded files
        media_items = self._collect_media_files(post_dir, post)

        # Fallback to yt-dlp if it's a video/reels and no mp4 was downloaded
        if post.is_video and not any(item["type"] == "video" for item in media_items):
            logger.warning(f"Video file missing in download for {shortcode}. Trying yt-dlp fallback...")
            ytdl_items = self._download_with_ytdlp(post_url, post_dir)
            if ytdl_items:
                media_items = ytdl_items

        caption = post.caption or ""

        return InstagramPostItem(
            shortcode=shortcode,
            url=post_url,
            is_video=post.is_video,
            typename=post.typename,
            caption=caption,
            date_utc=post.date_utc,
            media_files=media_items,
        )

    def _collect_media_files(self, post_dir: Path, post: instaloader.Post) -> List[dict]:
        """Collect and categorize downloaded images, videos, and thumbnails."""
        # Find all videos (.mp4)
        videos = sorted(glob.glob(str(post_dir / "*.mp4")))
        # Find all images (.jpg, .jpeg, .png)
        images = sorted(glob.glob(str(post_dir / "*.jpg")) + glob.glob(str(post_dir / "*.png")))

        media_items = []

        if post.typename == "GraphVideo" or (post.is_video and post.typename != "GraphSidecar"):
            # Single video / Reels
            if videos:
                vid_path = videos[0]
                # Thumbnail might be an image with the same base name
                thumb = images[0] if images else None
                media_items.append({"type": "video", "path": vid_path, "thumb": thumb})
        elif post.typename == "GraphSidecar":
            # Carousel / Album (multi-photo and/or multi-video)
            # Instaloader sidecar saves files numbered or named with sidecar nodes
            # Clean thumbnails for videos in sidecars
            for v in videos:
                base = os.path.splitext(v)[0]
                possible_thumb = base + ".jpg"
                thumb = possible_thumb if os.path.exists(possible_thumb) else None
                media_items.append({"type": "video", "path": v, "thumb": thumb})

            # Exclude images that act as thumbnails for videos
            video_bases = {os.path.splitext(v)[0] for v in videos}
            for img in images:
                base = os.path.splitext(img)[0]
                if base not in video_bases:
                    media_items.append({"type": "photo", "path": img, "thumb": None})

            # Sort media items by file name to keep Instagram carousel order
            media_items.sort(key=lambda x: x["path"])
        else:
            # Single Image
            if images:
                media_items.append({"type": "photo", "path": images[0], "thumb": None})

        return media_items

    def _download_with_ytdlp(self, post_url: str, post_dir: Path) -> List[dict]:
        """Download video/reels using yt-dlp."""
        import yt_dlp

        out_template = str(post_dir / "%(id)s.%(ext)s")
        ydl_opts = {
            "outtmpl": out_template,
            "format": "bestvideo+bestaudio/best",
            "quiet": True,
            "no_warnings": True,
            "writethumbnail": True,
        }
        if self.cookies_file and os.path.exists(self.cookies_file):
            ydl_opts["cookiefile"] = self.cookies_file

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([post_url])

            videos = glob.glob(str(post_dir / "*.mp4"))
            images = glob.glob(str(post_dir / "*.jpg")) + glob.glob(str(post_dir / "*.webp"))
            if videos:
                thumb = images[0] if images else None
                return [{"type": "video", "path": videos[0], "thumb": thumb}]
        except Exception as e:
            logger.error(f"yt-dlp download failed for {post_url}: {e}")
        return []

    def cleanup_post_dir(self, shortcode: str):
        """Remove downloaded media after successful transmission to Telegram."""
        post_dir = self.download_dir / shortcode
        if post_dir.exists():
            shutil.rmtree(post_dir, ignore_errors=True)
            logger.info(f"Cleaned up temporary files for {shortcode}")
