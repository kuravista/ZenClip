"""
Gallery cache for optimized video scanning.

Caches gallery listings to prevent blocking UI thread
and avoid redundant file system scans.
"""
import os
import json
import time
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from threading import Lock
import hashlib


class GalleryCache:
    """
    Cache for gallery video listings.

    Features:
    - TTL-based expiration
    - Thread-safe access
    - Incremental updates
    - Thumbnail caching
    """

    def __init__(
        self,
        cache_dir: Path,
        ttl_seconds: int = 60,
        thumbnail_ttl_seconds: int = 3600
    ):
        """
        Initialize gallery cache.

        Args:
            cache_dir: Directory to store cache files
            ttl_seconds: Cache TTL in seconds (default: 60)
            thumbnail_ttl_seconds: Thumbnail cache TTL (default: 1 hour)
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.ttl = ttl_seconds
        self.thumbnail_ttl = thumbnail_ttl_seconds

        self._lock = Lock()
        self._cache: Dict[str, Any] = {}
        self._thumbnails: Dict[str, str] = {}

        self._cache_file = self.cache_dir / 'gallery_cache.json'
        self._thumbnails_file = self.cache_dir / 'thumbnails_cache.json'

        self._load()

    def _load(self) -> None:
        """Load cache from disk."""
        # Load main cache
        if self._cache_file.exists():
            try:
                with open(self._cache_file, 'r') as f:
                    data = json.load(f)
                self._cache = data.get('videos', {})
            except (json.JSONDecodeError, IOError):
                self._cache = {}

        # Load thumbnails cache
        if self._thumbnails_file.exists():
            try:
                with open(self._thumbnails_file, 'r') as f:
                    self._thumbnails = json.load(f)
            except (json.JSONDecodeError, IOError):
                self._thumbnails = {}

    def _save(self) -> None:
        """Save cache to disk."""
        with self._lock:
            # Save main cache
            temp_file = self._cache_file.with_suffix('.tmp')
            with open(temp_file, 'w') as f:
                json.dump({
                    'videos': self._cache,
                    'timestamp': datetime.now().isoformat()
                }, f, indent=2)
            temp_file.replace(self._cache_file)

            # Save thumbnails cache
            temp_file = self._thumbnails_file.with_suffix('.tmp')
            with open(temp_file, 'w') as f:
                json.dump(self._thumbnails, f, indent=2)
            temp_file.replace(self._thumbnails_file)

    def _is_expired(self) -> bool:
        """Check if cache is expired."""
        if not self._cache_file.exists():
            return True

        try:
            with open(self._cache_file, 'r') as f:
                data = json.load(f)
            timestamp_str = data.get('timestamp')
            if not timestamp_str:
                return True

            timestamp = datetime.fromisoformat(timestamp_str)
            return datetime.now() > timestamp + timedelta(seconds=self.ttl)
        except (json.JSONDecodeError, IOError):
            return True

    def get_videos(self, directory: str) -> Optional[List[Dict]]:
        """
        Get cached videos for a directory.

        Args:
            directory: Directory path to get videos for

        Returns:
            List of video dicts or None if cache miss
        """
        with self._lock:
            if self._is_expired():
                return None

            dir_key = self._get_dir_key(directory)
            return self._cache.get(dir_key)

    def update_videos(self, directory: str, videos: List[Dict]) -> None:
        """
        Update cache for a directory.

        Args:
            directory: Directory path
            videos: List of video dicts to cache
        """
        with self._lock:
            dir_key = self._get_dir_key(directory)
            self._cache[dir_key] = videos
            self._save()

    def _get_dir_key(self, directory: str) -> str:
        """Generate cache key for a directory."""
        return hashlib.md5(directory.encode()).hexdigest()

    def get_thumbnail(self, video_path: str) -> Optional[str]:
        """
        Get cached thumbnail path for a video.

        Args:
            video_path: Path to video file

        Returns:
            Thumbnail path or None if not cached
        """
        with self._lock:
            return self._thumbnails.get(video_path)

    def set_thumbnail(self, video_path: str, thumbnail_path: str) -> None:
        """
        Cache thumbnail path for a video.

        Args:
            video_path: Path to video file
            thumbnail_path: Path to thumbnail file
        """
        with self._lock:
            self._thumbnails[video_path] = thumbnail_path
            self._save()

    def invalidate(self, directory: Optional[str] = None) -> None:
        """
        Invalidate cache for a directory or all.

        Args:
            directory: Specific directory to invalidate, or None for all
        """
        with self._lock:
            if directory:
                dir_key = self._get_dir_key(directory)
                self._cache.pop(dir_key, None)
            else:
                self._cache = {}
            self._save()

    def get_stats(self) -> Dict:
        """Get cache statistics."""
        with self._lock:
            return {
                'cached_directories': len(self._cache),
                'cached_thumbnails': len(self._thumbnails),
                'cache_file_exists': self._cache_file.exists(),
                'thumbnails_file_exists': self._thumbnails_file.exists(),
                'ttl_seconds': self.ttl,
                'is_expired': self._is_expired()
            }

    def clear_all(self) -> None:
        """Clear all cache."""
        with self._lock:
            self._cache = {}
            self._thumbnails = {}
            self._save()


def get_gallery_cache() -> GalleryCache:
    """
    Get or create the gallery cache instance.

    Uses environment variables for configuration:
    - CLIP_APP_DATA_DIR: App data directory
    - CLIP_CACHE_DIR: Cache directory override
    - CLIP_GALLERY_CACHE_TTL: Cache TTL in seconds
    """
    # Get cache directory
    cache_dir = os.environ.get('CLIP_CACHE_DIR')
    if not cache_dir:
        app_data_dir = os.environ.get('CLIP_APP_DATA_DIR', '.')
        cache_dir = os.path.join(app_data_dir, 'cache', 'gallery')

    # Get TTL
    ttl = int(os.environ.get('CLIP_GALLERY_CACHE_TTL', '60'))

    return GalleryCache(
        cache_dir=Path(cache_dir),
        ttl_seconds=ttl
    )


# Global instance
gallery_cache = get_gallery_cache()
