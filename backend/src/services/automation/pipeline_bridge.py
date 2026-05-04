from __future__ import annotations

import os
import json
import time
from pathlib import Path
from typing import Any, Dict, Optional

from services.automation.models import ClipRequest


DEFAULT_SETTINGS: Dict[str, Any] = {}


def _read_user_settings() -> dict:
    """Read user_settings.json using the same path resolution as the rest of the app."""
    settings_path = os.environ.get("CLIP_SETTINGS_FILE")
    if not settings_path:
        app_data_dir = os.environ.get("CLIP_APP_DATA_DIR", ".")
        settings_path = str(Path(app_data_dir) / "user_settings.json")
    try:
        if os.path.exists(settings_path):
            with open(settings_path, "r", encoding="utf-8") as f:
                return json.load(f)
    except (json.JSONDecodeError, IOError):
        pass
    return {}


# Default visual config matching the frontend form defaults (app.py Form() defaults)
DEFAULT_HOOK_STYLES = {
    "hook_style": "preset-1",
    "font": "Impact",
    "color": "#FF0000",
    "position": "top",
    "top_text": "",
    "headline": "",
    "subheading": "",
    "stroke_width": 2,
    "stroke_color": "#000000",
    "line_spacing": 0,
    "top_gap": 10,
    "bottom_gap": 20,
    "font_size": 80,
    "top_font_size": 28,
    "sub_font_size": 35,
    "full_duration": False,
    "preset2_content": "",
    "highlight_color": "#CBFF00",
}

DEFAULT_SUBTITLE_CONFIG = {
    "fontsize": 45,
    "color": "#FFFF00",
    "stroke_color": "#000000",
    "stroke_width": 3,
    "bg_opacity": 0.75,
    "font": "Arial",
    "style": "word",
    "bg_color": "#2563eb",
    "glow_enabled": False,
    "glow_color": "#00FF00",
    "glow_intensity": 2,
    "smart_subtitles": False,
    "vertical_position": 75,
}


class PipelineBridge:
    """Converts Automation API parameters to job_data format expected by JobManager.submit_job()."""

    def __init__(self, settings: Optional[dict] = None):
        self._settings = settings if settings is not None else _read_user_settings()

    def build_job_data(self, request: ClipRequest) -> dict:
        """Build the job_data dict compatible with the existing pipeline."""
        job_data: Dict[str, Any] = {}

        # --- Source ---
        job_data["url"] = request.url
        job_data["yt_quality"] = request.quality
        job_data["download_folder"] = "downloads"

        # --- Pipeline control ---
        job_data["stop_for_review"] = False  # Automation never pauses for review

        # --- Aspect ratio ---
        job_data["video_aspect"] = request.aspect_ratio  # Pipeline reads 'video_aspect', NOT 'aspect_ratio'

        # --- Transcription ---
        job_data["transcription_mode"] = request.transcription_mode

        # --- Subtitles (full config matching frontend) ---
        # Priority: explicit request param > user_settings > hardcoded default
        sub_enabled = request.subtitle_enabled if request.subtitle_enabled is not None else self._settings.get("subtitle_enabled", True)
        job_data["add_subtitles"] = sub_enabled
        if sub_enabled:
            sub_config = dict(DEFAULT_SUBTITLE_CONFIG)
            # Style: request > settings > default
            sub_config["style"] = request.subtitle_style or self._settings.get("defaultSubtitleStyle", sub_config["style"])
            # Other subtitle params: settings override hardcoded defaults
            sub_config["font"] = self._settings.get("subtitle_font_family", sub_config["font"])
            sub_config["fontsize"] = self._settings.get("subtitle_font_size", sub_config["fontsize"])
            sub_config["color"] = self._settings.get("subtitle_text_color", sub_config["color"])
            sub_config["stroke_color"] = self._settings.get("subtitle_stroke_color", sub_config["stroke_color"])
            sub_config["stroke_width"] = self._settings.get("subtitle_stroke_width", sub_config["stroke_width"])
            sub_config["bg_opacity"] = self._settings.get("subtitle_bg_opacity", sub_config["bg_opacity"])
            sub_config["bg_color"] = self._settings.get("subtitle_bg_color", sub_config["bg_color"])
            sub_config["vertical_position"] = self._settings.get("subtitle_position", sub_config["vertical_position"])
            job_data["subtitle_config"] = sub_config

        # --- Hook (full config matching frontend) ---
        # Priority: explicit request param > user_settings > hardcoded default
        hook_enabled = request.hook_enabled if request.hook_enabled is not None else self._settings.get("hook_enabled", True)
        job_data["add_viral_hook"] = hook_enabled
        if hook_enabled:
            hook_styles = dict(DEFAULT_HOOK_STYLES)
            # Style: request > settings > default
            hook_styles["hook_style"] = request.hook_style or self._settings.get("hook_style", hook_styles["hook_style"])
            # Other hook params: settings override hardcoded defaults
            hook_styles["font"] = self._settings.get("hook_font", hook_styles["font"])
            hook_styles["color"] = self._settings.get("hook_heading_color", hook_styles["color"])
            hook_styles["font_size"] = self._settings.get("hook_font_size", hook_styles["font_size"])
            hook_styles["top_font_size"] = self._settings.get("hook_top_font_size", hook_styles["top_font_size"])
            hook_styles["sub_font_size"] = self._settings.get("hook_sub_font_size", hook_styles["sub_font_size"])
            hook_styles["position"] = self._settings.get("hook_position", hook_styles["position"])
            hook_styles["stroke_width"] = self._settings.get("hook_stroke_width", hook_styles["stroke_width"])
            hook_styles["stroke_color"] = self._settings.get("hook_stroke_color", hook_styles["stroke_color"])
            hook_styles["top_gap"] = self._settings.get("hook_top_gap", hook_styles["top_gap"])
            hook_styles["bottom_gap"] = self._settings.get("hook_bottom_gap", hook_styles["bottom_gap"])
            hook_styles["highlight_color"] = self._settings.get("hook_highlight_color", hook_styles["highlight_color"])
            # Preset-2 content
            if hook_styles["hook_style"] == "preset-2":
                preset2_content = self._settings.get("preset2_content", "") or self._settings.get("hook_preset2_text", "")
                hook_styles["preset2_content"] = preset2_content
            job_data["hook_styles"] = hook_styles

        # --- Analysis ---
        job_data["num_clips"] = request.max_clips
        job_data["min_duration"] = str(request.min_clip_duration)

        # --- LLM provider ---
        # Support both camelCase (user_settings.json) and snake_case keys
        provider = request.llm_provider or self._settings.get("apiProvider") or self._settings.get("api_provider", "deepseek")

        # Resolve API key: explicit request param > provider-specific key > generic key
        api_key = request.api_key
        if not api_key:
            if provider == "openrouter":
                api_key = self._settings.get("openrouterApiKey", "")
            if not api_key:
                api_key = self._settings.get("apiKey") or self._settings.get("api_key", "")

        job_data["api_provider"] = provider
        if api_key:
            job_data["api_key"] = api_key

        # --- Watermark ---
        wm_enabled = request.watermark_enabled if request.watermark_enabled else self._settings.get("watermark_enabled", False)
        if wm_enabled:
            job_data["add_watermark"] = True
            wm_config: Dict[str, Any] = {
                "watermark_type": request.watermark_type,
                "watermark_text": request.watermark_text or self._settings.get("watermark_text", "ZenClip"),
                "watermark_opacity": request.watermark_opacity,
                "watermark_position": request.watermark_position,
                "watermark_size": request.watermark_size,
                "watermark_font": request.watermark_font or self._settings.get("watermark_font", "Arial-Bold"),
            }
            if request.watermark_image_path:
                wm_config["watermark_image_path"] = request.watermark_image_path
            # Override from user_settings if present
            if not request.watermark_text:
                wm_config["watermark_text"] = self._settings.get("watermark_text", "ZenClip")
            job_data["watermark_config"] = wm_config

        # --- CTA (Call-to-Action) ---
        cta_enabled = request.cta_enabled if request.cta_enabled is not None else self._settings.get("cta_enabled", False)
        if cta_enabled:
            cta_cfg: Dict[str, Any] = {
                "enabled": True,
                "type": request.cta_type or self._settings.get("cta_type", "image"),
                "duration": request.cta_duration if request.cta_duration is not None else self._settings.get("cta_duration", 5.0),
            }
            # CTA path: explicit param > user_settings > project default folder
            cta_media = request.cta_path or self._settings.get("cta_path")
            if not cta_media:
                # Default to project-local static/cta-media/ folder
                default_cta_dir = os.path.normpath(os.path.join(os.getcwd(), "static", "cta-media"))
                if os.path.isdir(default_cta_dir) and os.listdir(default_cta_dir):
                    cta_media = default_cta_dir
            if cta_media:
                cta_cfg["path"] = cta_media
                job_data["cta_config"] = cta_cfg
            else:
                # CTA enabled but no media path — skip silently
                pass

        # --- Other defaults the pipeline expects ---
        job_data.setdefault("video_type", "general")
        job_data.setdefault("encoding_preset", "medium")
        job_data["manual_cut"] = False  # Automation API never uses manual cut

        # --- Metadata ---
        job_data["randomize_metadata"] = request.randomize_metadata or self._settings.get("randomize_metadata", False)

        return job_data
