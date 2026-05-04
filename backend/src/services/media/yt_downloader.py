"""
YouTube (and general URL) video downloader using yt-dlp.

Provides:
  - preview_metadata(url) -> dict: non-downloading metadata extraction
  - download(url, quality, output_dir, progress_hook) -> str: file download
  - download_for_job(url, quality, output_dir, job_id) -> str: download with job progress
"""

from __future__ import annotations
import os
import re
from typing import Optional, Callable, Dict, Any


class YtDownloaderError(Exception):
    """Raised when yt-dlp operations fail."""
    pass


class YtDownloader:
    """Wrapper around yt-dlp for extracting metadata and downloading videos."""

    SUPPORTED_QUALITIES = {
        "best":  "bestvideo[height<=?1080]+bestaudio/best",
        "1080p": "bestvideo[height<=1080]+bestaudio/best",
        "720p":  "bestvideo[height<=720]+bestaudio/best[height<=720]",
        "480p":  "bestvideo[height<=480]+bestaudio/best[height<=480]",
        "audio": "bestaudio/best",
    }

    DEFAULT_QUALITY = "720p"

    @staticmethod
    def _get_ffmpeg_path() -> Optional[str]:
        """Resolve ffmpeg path using the same logic as the rest of the app."""
        try:
            from services.core.binary_manager import get_ffmpeg_path
            path = get_ffmpeg_path()
            if path and os.path.exists(path):
                return path
        except Exception:
            pass
        return None

    @classmethod
    def is_supported_url(cls, url: str) -> bool:
        """Quick check whether the URL looks downloadable."""
        if not url or not url.startswith("http"):
            return False
        return True

    def preview_metadata(self, url: str) -> Dict[str, Any]:
        """
        Extract metadata without downloading.

        Returns dict with: title, duration, thumbnail, description, uploader,
        formats, available_qualities.
        """
        try:
            import yt_dlp
        except ImportError:
            raise YtDownloaderError("yt-dlp not installed. Run: pip install yt-dlp")

        opts = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "extract_flat": False,
        }

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
        except Exception as e:
            raise YtDownloaderError(f"Failed to extract metadata: {e}")

        if not info:
            raise YtDownloaderError("No metadata returned for URL")

        # Build available quality labels
        available_qualities = set()
        for f in info.get("formats", []):
            h = f.get("height")
            if h and f.get("vcodec", "none") != "none":
                if h >= 1080:
                    available_qualities.add("1080p")
                if h >= 720:
                    available_qualities.add("720p")
                if h >= 480:
                    available_qualities.add("480p")
                available_qualities.add("best")
            if f.get("acodec", "none") != "none" and f.get("vcodec", "none") == "none":
                available_qualities.add("audio")

        quality_order = ["best", "1080p", "720p", "480p", "audio"]
        sorted_qualities = [q for q in quality_order if q in available_qualities]
        if not sorted_qualities:
            sorted_qualities = ["best"]

        return {
            "title": info.get("title", "Unknown"),
            "duration": info.get("duration"),
            "thumbnail": info.get("thumbnail"),
            "description": (info.get("description") or "")[:500],
            "uploader": info.get("uploader", ""),
            "channel": info.get("channel", ""),
            "view_count": info.get("view_count"),
            "upload_date": info.get("upload_date"),
            "webpage_url": info.get("webpage_url", url),
            "available_qualities": sorted_qualities,
        }

    def download(
        self,
        url: str,
        quality: str = "720p",
        output_dir: str = "downloads",
        progress_hook: Optional[Callable[[Dict], None]] = None,
    ) -> str:
        """
        Download a video and return the local file path.

        Returns absolute file path of the downloaded file.
        """
        try:
            import yt_dlp
        except ImportError:
            raise YtDownloaderError("yt-dlp not installed. Run: pip install yt-dlp")

        os.makedirs(output_dir, exist_ok=True)

        format_str = self.SUPPORTED_QUALITIES.get(quality, quality)
        filename_template = os.path.join(output_dir, "%(title.80)s [%(id)s].%(ext)s")

        is_audio = quality == "audio"

        postprocessors = []
        if is_audio:
            postprocessors.append({
                "key": "FFmpegExtractAudio",
                "preferredcodec": "m4a",
            })
        else:
            postprocessors.append({
                "key": "FFmpegVideoConvertor",
                "preferedformat": "mp4",
            })

        # Resolve ffmpeg path for yt-dlp (required for merging DASH streams)
        ffmpeg_exe = self._get_ffmpeg_path()

        opts = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "format": format_str,
            "outtmpl": filename_template,
            "merge_output_format": "mp4" if not is_audio else None,
            "postprocessors": postprocessors,
            "ffmpeg_location": ffmpeg_exe,
            "restrictfilenames": True,
        }

        hooks = []
        if progress_hook:
            hooks.append(progress_hook)

        def _internal_hook(d):
            for h in hooks:
                try:
                    h(d)
                except Exception:
                    pass

        opts["progress_hooks"] = [_internal_hook]

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)

                # yt-dlp may change extension after post-processing
                if not os.path.exists(filename):
                    base, _ = os.path.splitext(filename)
                    for ext in [".mp4", ".mkv", ".webm", ".m4a", ".mp3"]:
                        candidate = base + ext
                        if os.path.exists(candidate):
                            filename = candidate
                            break

                if not os.path.exists(filename):
                    raise YtDownloaderError(f"Download completed but file not found: {filename}")

                abs_path = os.path.abspath(filename)
                file_size = os.path.getsize(abs_path)
                try:
                    print(f"  [yt-dlp] Download complete: {abs_path} ({file_size / (1024*1024):.1f} MB)")
                except UnicodeEncodeError:
                    pass  # Windows console may not handle Unicode filenames
                return abs_path

        except YtDownloaderError:
            raise
        except Exception as e:
            raise YtDownloaderError(f"Download failed: {e}")

    def download_for_job(
        self,
        url: str,
        quality: str,
        output_dir: str,
        job_id: str,
        check_cancelled: Optional[Callable[[], bool]] = None,
    ) -> str:
        """
        Download with progress wired to job_manager status updates.
        Maps download progress (0-100%) to PREPARING progress (5-25%).
        """
        from services.core.job_manager import job_manager, JobStatus

        def hook(d):
            if d["status"] == "downloading":
                if check_cancelled and check_cancelled():
                    raise YtDownloaderError("Download cancelled by user")

                raw = d.get("_percent_str", "0%").strip().replace("%", "")
                try:
                    pct = float(raw)
                except ValueError:
                    pct = 0
                job_pct = 5 + int(pct * 0.2)
                job_manager.update_job_status(
                    job_id,
                    JobStatus.PREPARING,
                    f"Downloading video... {int(pct)}%",
                    progress_percent=job_pct,
                )

            elif d["status"] == "finished":
                job_manager.update_job_status(
                    job_id,
                    JobStatus.PREPARING,
                    "Download complete, preparing for processing...",
                    progress_percent=25,
                )

        return self.download(
            url=url,
            quality=quality,
            output_dir=output_dir,
            progress_hook=hook,
        )


# Module-level convenience functions
_downloader = YtDownloader()

def preview_metadata(url: str) -> Dict[str, Any]:
    return _downloader.preview_metadata(url)

def download_video(url: str, quality: str = "720p", output_dir: str = "downloads",
                   progress_hook=None) -> str:
    return _downloader.download(url, quality, output_dir, progress_hook)

def download_for_job(url: str, quality: str, output_dir: str, job_id: str,
                     check_cancelled=None) -> str:
    return _downloader.download_for_job(url, quality, output_dir, job_id, check_cancelled)
