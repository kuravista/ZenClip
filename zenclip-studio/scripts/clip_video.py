#!/usr/bin/env python3
"""
ZenClip Video Clipper - Python CLI

Usage:
    python clip_video.py "path/to/video.mp4" --clips 3
    python clip_video.py "video.mp4" --manual --phrases transcript.json
    python clip_video.py --youtube "https://youtube.com/watch?v=..." --quality 720p --clips 3
"""

import argparse
import json
import os
import sys
import time
import requests
from pathlib import Path

from pathlib import Path

# Configuration
BACKEND_URL = "http://127.0.0.1:9478"
OUTPUT_DIR = Path("D:/Extend_C/Program/zenclip/audit/recovery-workspace/static/clips")


SETTINGS_FILE = Path("D:/Extend_C/Program/zenclip/audit/recovery-workspace/backend/user_settings.json")


def load_settings():
    """Load API key and provider from settings file."""
    try:
        with open(SETTINGS_FILE) as f:
            return json.load(f)
    except:
        return {}


def check_backend():
    try:
        resp = requests.get(f"{BACKEND_URL}/health", timeout=5)
        return resp.status_code == 200
    except:
        return False


def submit_auto(video_path: str, num_clips: int = 3, min_duration: int = 30,
               add_subtitles: bool = True, aspect_ratio: str = "9:16"):
    """Submit video for auto-processing with ASR."""
    print(f"\nSubmitting video: {video_path}")

    with open(video_path, 'rb') as f:
        files = {'video_file': (os.path.basename(video_path), f, 'video/mp4')}
        data = {
            'num_clips': num_clips,
            'min_duration': min_duration,
            'add_subtitles': str(add_subtitles).lower(),
            'video_aspect': aspect_ratio
        }
        resp = requests.post(f"{BACKEND_URL}/process", files=files, data=data)

    if resp.status_code == 200:
        result = resp.json()
        print(f"Job submitted: {result.get('job_id')}")
        return result.get('job_id')
    else:
        print(f"Error: {resp.text}")
        return None


def submit_youtube(url: str, quality: str = '720p', num_clips: int = 3,
                   min_duration: int = 30, add_subtitles: bool = True,
                   aspect_ratio: str = '9:16'):
    """Submit YouTube URL for download and auto-processing."""
    print(f"\nSubmitting YouTube URL: {url}")
    print(f"  Quality: {quality}")

    # Load API key from settings
    settings = load_settings()
    api_key = settings.get('apiKey', '')
    api_provider = settings.get('apiProvider', 'deepseek')

    if not api_key:
        try:
            env_var = f"{provider.upper()}_API_KEY"
            api_key = os.environ.get(env_var)
        except Exception:
            pass
    if not api_key:
        print(f"Error: API Key missing for {api_provider}")
        sys.exit(1)

    data = {
        'url': url,
        'yt_quality': quality,
        'num_clips': num_clips,
        'min_duration': min_duration,
        'add_subtitles': str(add_subtitles).lower(),
        'video_aspect': aspect_ratio,
        'api_key': api_key,
        'api_provider': api_provider
    }
    resp = requests.post(f"{BACKEND_URL}/process", data=data)
    if resp.status_code == 200:
        result = resp.json()
        print(f"Job submitted: {result.get('job_id')}")
        return result.get('job_id')
    else:
        print(f"Error: {resp.text}")
        return None
def preview_youtube(url: str):
    """Preview YouTube video metadata without downloading."""
    print(f"\nPreviewing: {url}")
    resp = requests.post(
        f"{BACKEND_URL}/api/yt-preview",
        json={"url": url},
        headers={"Content-Type": "application/json"},
    )
    if resp.status_code == 200:
        result = resp.json()
        meta = result.get('metadata', {})
        print(f"\n{'='*50}")
        print(f"  Title: {meta.get('title', 'Unknown')}")
        duration = meta.get('duration', 0)
        if duration:
            mins, secs = divmod(int(duration), 60)
            print(f"  Duration: {mins}:{secs:02d}")
        print(f"  Uploader: {meta.get('uploader', 'Unknown')}")
        print(f"  Qualities: {', '.join(meta.get('available_qualities', []))}")
        print(f"{'='*50}")
        return meta
    else:
        print(f"Preview failed: {resp.text}")
        return None
def submit_manual(video_path: str, phrase_timings: list, clips_data: list,
                  add_subtitles: bool = True, aspect_ratio: str = "9:16"):
    """Submit video with manual transcript (bypasses ASR)."""
    print(f"\nSubmitting with manual transcript: {video_path}")
    payload = {
        "video_path": video_path,
        "phrase_timings": phrase_timings,
        "clips_data": clips_data,
        "num_clips": len(clips_data),
        "video_aspect": aspect_ratio,
        "add_subtitles": add_subtitles,
    }
    resp = requests.post(
        f"{BACKEND_URL}/manual_transcript_import",
        json=payload,
        headers={"Content-Type": "application/json"}
    )
    if resp.status_code == 200:
        result = resp.json()
        print(f"Job submitted: {result.get('job_id')}")
        return result.get('job_id')
    else:
        print(f"Error: {resp.text}")
        return None
def monitor_job(job_id: str):
    """Monitor job progress."""
    print(f"\nProcessing job: {job_id}")
    while True:
        try:
            resp = requests.get(f"{BACKEND_URL}/status/{job_id}", timeout=10)
            data = resp.json()
            status = data.get('status', 'unknown')
            progress = data.get('progress', 0)
            msg = data.get('msg', '')
            # Progress bar
            bar_len = 30
            filled = int(bar_len * progress / 100)
            bar = '#' * filled + '-' * (bar_len - filled)
            print(f"\r  [{bar}] {progress}% - {msg}", end='', flush=True)
            if status == 'complete':
                print(f"\n\nComplete!")
                clips = data.get('clips', [])
                show_results(job_id, clips)
                return
            elif status == 'error':
                print(f"\n\nError: {data.get('error', 'Unknown error')}")
                sys.exit(1)
        except Exception as e:
            print(f"\nError checking status: {e}")
        time.sleep(5)
def show_results(job_id: str, clips: list):
    """Show output results."""
    output_path = OUTPUT_DIR / job_id
    print("\n" + "=" * 50)
    print("OUTPUT")
    print("=" * 50)
    print(f"Folder: {output_path}")
    print()
    if clips:
        print("Clips created:")
        for i, clip in enumerate(clips, 1):
            topic = clip.get('topic', f'Clip {i}')
            duration = clip.get('duration', '?')
            path = clip.get('path', '')
            print(f"  {i}. {topic} ({duration}s)")
            if path and os.path.exists(path):
                size = os.path.getsize(path) / (1024 * 1024)
                print(f"     {os.path.basename(path)} ({size:.1f} MB)")
    print()
    print(f"Open folder: {output_path}")
def load_phrases(filepath: str) -> list:
    """Load phrase timings from JSON file."""
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)
def main():
    parser = argparse.ArgumentParser(
        description='ZenClip Video Clipper',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s "video.mp4" --clips 3
  %(prog)s "video.mp4" --manual --phrases transcript.json
  %(prog)s --youtube "https://youtube.com/watch?v=..." --quality 720p --clips 3
        """
    )
    # Input: video file OR YouTube URL (mutually exclusive)
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument('video', nargs='?', default=None, help='Path to video file')
    input_group.add_argument('--youtube', metavar='URL', help='YouTube URL to download and process')
    # Common options
    parser.add_argument('--clips', type=int, default=3, help='Number of clips (default: 3)')
    parser.add_argument('--duration', type=int, default=30, help='Min duration in seconds (default: 30)')
    parser.add_argument('--aspect', default='9:16', help='Aspect ratio (default: 9:16)')
    parser.add_argument('--no-subtitles', action='store_true', help='Disable subtitles')
    # YouTube options
    parser.add_argument('--quality', default='720p',
                        choices=['best', '1080p', '720p', '480p', 'audio'],
                        help='Download quality for YouTube (default: 720p)')
    parser.add_argument('--preview', action='store_true',
                        help='Preview YouTube metadata only (no download)')
    # Manual mode
    parser.add_argument('--manual', action='store_true', help='Use manual transcript mode')
    parser.add_argument('--phrases', help='JSON file with phrase timings')
    parser.add_argument('--clips-json', help='JSON file with clip definitions')
    args = parser.parse_args()
    # Check backend
    print("Checking backend...")
    if not check_backend():
        print("Backend not running!")
        print("Start with: python run_backend.py")
        sys.exit(1)
    print("Backend running")
    # YouTube mode
    if args.youtube:
        if args.preview:
            preview_youtube(args.youtube)
            sys.exit(0)
        else:
            job_id = submit_youtube(
                args.youtube,
                quality=args.quality,
                num_clips=args.clips,
                min_duration=args.duration,
                add_subtitles=not args.no_subtitles,
                aspect_ratio=args.aspect,
            )
    # Manual mode
    elif args.manual:
        if not args.video:
            print("Error: Manual mode requires a video file path")
            sys.exit(1)
        if not os.path.exists(args.video):
            print(f"Video not found: {args.video}")
            sys.exit(1)
        if args.phrases:
            phrases = load_phrases(args.phrases)
        else:
            phrases = [
                {"text": "Opening content", "start": 0.0, "end": 5.0},
                {"text": "Main discussion", "start": 5.0, "end": 15.0},
                {"text": "Key points", "start": 15.0, "end": 30.0},
            ]
        if args.clips_json:
            clips_data = load_phrases(args.clips_json)
        else:
            clips_data = [
                {"start_time": 0, "end_time": 15, "topic": "Opening", "hook_heading": "Watch", "hook_subheading": "Now"},
                {"start_time": 30, "end_time": 60, "topic": "Main", "hook_heading": "Key", "hook_subheading": "Point"},
            ]
        job_id = submit_manual(
            args.video, phrases, clips_data,
            add_subtitles=not args.no_subtitles,
            aspect_ratio=args.aspect
        )
    # Auto mode (file upload)
    else:
        if not args.video:
            print("Error: Provide a video file path or use --youtube URL")
            sys.exit(1)
        if not os.path.exists(args.video):
            print(f"Video not found: {args.video}")
            sys.exit(1)
        job_id = submit_auto(
            args.video,
            num_clips=args.clips,
            min_duration=args.duration,
            add_subtitles=not args.no_subtitles,
            aspect_ratio=args.aspect
        )
    if not job_id:
        sys.exit(1)
    # Monitor
    clips = monitor_job(job_id)
    # Results
    if clips:
        show_results(job_id, clips)
if __name__ == "__main__":
    main()
