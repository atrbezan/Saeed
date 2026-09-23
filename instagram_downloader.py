import glob
import logging
import os
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import instaloader
import requests

logger = logging.getLogger(__name__)


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
    def __init__(
        self,
        target_username: str,
        session_file: Optional[str] = None,
        cookies_file: Optional[str] = None,
        login_user: Optional[str] = None,
        login_pass: Optional[str] = None,
        download_dir: str = "downloads",
    ):
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
            logger.info(f"Checking Instagram profile via embed: {url}")
            res = requests.get(url, timeout=20)
            if res.status_code == 200:
                pattern = r'shortcode_media\\":\{.*?\\"shortcode\\":\\"([A-Za-z0-9_-]+)\\"'
                matches = re.findall(pattern, res.text)
                seen = set()
                shortcodes = [x for x in matches if not (x in seen or seen.add(x))]
                logger.info(f"Found {len(shortcodes)} posts via embed interface.")
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

        logger.info(f"Fallback: extracting profile for @{self.target_username}...")
        profile = instaloader.Profile.from_username(self.loader.context, self.target_username)
        for p in profile.get_posts():
            posts.append(p)
            if len(posts) >= limit:
                break
        return posts

    def download_post(self, post: instaloader.Post) -> InstagramPostItem:
        sc = post.shortcode
        post_dir = self.download_dir / sc
        if post_dir.exists():
            shutil.rmtree(post_dir, ignore_errors=True)
        post_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Downloading post {sc} ({post.typename})...")
        self.loader.download_post(post, target=sc)

        media_items = self._collect_media_files(post_dir, post)

        return InstagramPostItem(
            shortcode=sc,
            url=f"https://www.instagram.com/p/{sc}/",
            is_video=post.is_video,
            typename=post.typename,
            caption=post.caption or "",
            date_utc=post.date_utc,
            media_files=media_items,
        )

    def _collect_media_files(self, post_dir: Path, post: instaloader.Post) -> List[dict]:
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

        return media_items

    def cleanup_post_dir(self, shortcode: str):
        post_dir = self.download_dir / shortcode
        if post_dir.exists():
            shutil.rmtree(post_dir, ignore_errors=True)
            logger.info(f"Cleaned up temporary files for {shortcode}")
