import pytest
import json
from unittest.mock import patch, MagicMock
from services.automation.models import ClipRequest
from services.automation.pipeline_bridge import PipelineBridge, DEFAULT_SETTINGS


class TestPipelineBridge:
    def setup_method(self):
        self.bridge = PipelineBridge(settings={})  # Empty settings for predictable defaults

    def test_minimal_request_mapping(self):
        req = ClipRequest(url="https://youtube.com/watch?v=abc123")
        job_data = self.bridge.build_job_data(req)
        assert job_data["url"] == "https://youtube.com/watch?v=abc123"
        assert job_data["yt_quality"] == "720p"
        assert job_data["video_aspect"] == "9:16"
        assert job_data["stop_for_review"] is False
        assert job_data["add_subtitles"] is True
        assert job_data["add_viral_hook"] is True
        assert job_data["transcription_mode"] == "fast"
        assert job_data["num_clips"] == 5
        assert job_data["min_duration"] == "15"
        assert job_data["api_provider"] == "deepseek"  # Default when no settings
        assert "hook_styles" in job_data
        assert job_data["hook_styles"]["hook_style"] == "preset-2"
        # Bridge now sends full hook config
        assert job_data["hook_styles"]["font"] == "Impact"
        assert job_data["hook_styles"]["font_size"] == 80

    def test_aspect_ratio_maps_to_video_aspect(self):
        req = ClipRequest(url="https://youtube.com/watch?v=abc", aspect_ratio="16:9")
        job_data = self.bridge.build_job_data(req)
        assert job_data["video_aspect"] == "16:9"
        assert "aspect_ratio" not in job_data

    def test_transcription_mode_passthrough(self):
        req = ClipRequest(url="https://youtube.com/watch?v=abc", transcription_mode="accurate")
        job_data = self.bridge.build_job_data(req)
        assert job_data["transcription_mode"] == "accurate"

    def test_hook_disabled_omits_hook_styles(self):
        req = ClipRequest(url="https://youtube.com/watch?v=abc", hook_enabled=False)
        job_data = self.bridge.build_job_data(req)
        assert job_data["add_viral_hook"] is False
        assert "hook_styles" not in job_data

    def test_subtitle_disabled(self):
        req = ClipRequest(url="https://youtube.com/watch?v=abc", subtitle_enabled=False)
        job_data = self.bridge.build_job_data(req)
        assert job_data["add_subtitles"] is False
        assert "subtitle_config" not in job_data

    def test_subtitle_config_has_all_visual_fields(self):
        """Bridge should send full subtitle config matching frontend defaults."""
        req = ClipRequest(url="https://youtube.com/watch?v=abc", subtitle_enabled=True)
        job_data = self.bridge.build_job_data(req)
        sub = job_data["subtitle_config"]
        assert sub["fontsize"] == 45
        assert sub["color"] == "#FFFF00"
        assert sub["stroke_color"] == "#000000"
        assert sub["stroke_width"] == 3
        assert sub["bg_opacity"] == 0.75
        assert sub["font"] == "Arial"
        assert sub["style"] == "word"
        assert sub["bg_color"] == "#2563eb"
        assert sub["vertical_position"] == 75

    def test_hook_config_has_all_visual_fields(self):
        """Bridge should send full hook config matching frontend defaults."""
        req = ClipRequest(url="https://youtube.com/watch?v=abc", hook_enabled=True)
        job_data = self.bridge.build_job_data(req)
        hook = job_data["hook_styles"]
        assert hook["font"] == "Impact"
        assert hook["color"] == "#FF0000"
        assert hook["position"] == "top"
        assert hook["font_size"] == 80
        assert hook["top_font_size"] == 28
        assert hook["sub_font_size"] == 35
        assert hook["stroke_width"] == 2
        assert hook["stroke_color"] == "#000000"
        assert hook["top_gap"] == 10
        assert hook["bottom_gap"] == 20
        assert hook["highlight_color"] == "#CBFF00"

    def test_custom_provider_and_key(self):
        req = ClipRequest(
            url="https://youtube.com/watch?v=abc",
            llm_provider="openrouter",
            api_key="sk-test-123"
        )
        job_data = self.bridge.build_job_data(req)
        assert job_data["api_provider"] == "openrouter"
        assert job_data["api_key"] == "sk-test-123"

    def test_settings_fallback(self):
        bridge = PipelineBridge(settings={"apiProvider": "gemini", "apiKey": "gemini-key"})
        req = ClipRequest(url="https://youtube.com/watch?v=abc")
        job_data = bridge.build_job_data(req)
        assert job_data["api_provider"] == "gemini"
        assert job_data["api_key"] == "gemini-key"

    def test_request_overrides_settings(self):
        bridge = PipelineBridge(settings={"apiProvider": "gemini"})
        req = ClipRequest(url="https://youtube.com/watch?v=abc", llm_provider="openai")
        job_data = bridge.build_job_data(req)
        assert job_data["api_provider"] == "openai"

    def test_settings_camel_case_keys(self):
        """user_settings.json uses camelCase: apiProvider, apiKey."""
        bridge = PipelineBridge(settings={"apiProvider": "openrouter", "openrouterApiKey": "sk-or-test"})
        req = ClipRequest(url="https://youtube.com/watch?v=abc")
        job_data = bridge.build_job_data(req)
        assert job_data["api_provider"] == "openrouter"
        assert job_data["api_key"] == "sk-or-test"

    def test_download_folder_set(self):
        req = ClipRequest(url="https://youtube.com/watch?v=abc")
        job_data = self.bridge.build_job_data(req)
        assert job_data["download_folder"] == "downloads"

    def test_quality_maps_to_yt_quality(self):
        req = ClipRequest(url="https://youtube.com/watch?v=abc", quality="1080p")
        job_data = self.bridge.build_job_data(req)
        assert job_data["yt_quality"] == "1080p"

    def test_hook_styles_dict_with_preset2(self):
        req = ClipRequest(url="https://youtube.com/watch?v=abc", hook_style="preset-2")
        job_data = self.bridge.build_job_data(req)
        assert job_data["hook_styles"]["hook_style"] == "preset-2"

    def test_max_clips_maps_to_num_clips(self):
        req = ClipRequest(url="https://youtube.com/watch?v=abc", max_clips=10)
        job_data = self.bridge.build_job_data(req)
        assert job_data["num_clips"] == 10

    def test_min_clip_duration_maps_to_min_duration(self):
        req = ClipRequest(url="https://youtube.com/watch?v=abc", min_clip_duration=20)
        job_data = self.bridge.build_job_data(req)
        assert job_data["min_duration"] == "20"

    def test_default_provider_when_no_settings(self):
        bridge = PipelineBridge(settings={})
        req = ClipRequest(url="https://youtube.com/watch?v=abc")
        job_data = bridge.build_job_data(req)
        assert job_data["api_provider"] == "deepseek"

    def test_user_settings_override_subtitle_visuals(self):
        """User settings should override default subtitle visual config."""
        bridge = PipelineBridge(settings={
            "subtitle_font_family": "Montserrat-Bold",
            "subtitle_font_size": 55,
            "subtitle_text_color": "#00FF00",
            "defaultSubtitleStyle": "mozi",
        })
        req = ClipRequest(url="https://youtube.com/watch?v=abc", subtitle_enabled=True)
        job_data = bridge.build_job_data(req)
        sub = job_data["subtitle_config"]
        assert sub["font"] == "Montserrat-Bold"
        assert sub["fontsize"] == 55
        assert sub["color"] == "#00FF00"
        assert sub["style"] == "mozi"

    def test_user_settings_override_hook_visuals(self):
        """User settings should override default hook visual config."""
        bridge = PipelineBridge(settings={
            "hook_font": "Anton",
            "hook_heading_color": "#CBFF00",
            "hook_font_size": 100,
        })
        req = ClipRequest(url="https://youtube.com/watch?v=abc", hook_enabled=True)
        job_data = bridge.build_job_data(req)
        hook = job_data["hook_styles"]
        assert hook["font"] == "Anton"
        assert hook["color"] == "#CBFF00"
        assert hook["font_size"] == 100

    def test_full_user_settings_produces_frontend_equivalent_output(self):
        """With full user_settings.json, bridge output should match what the frontend sends."""
        user_settings = {
            "apiProvider": "openrouter",
            "openrouterApiKey": "sk-or-test-key",
            "defaultSubtitleStyle": "mozi",
            "subtitle_font_family": "Montserrat-Bold",
            "subtitle_font_size": 55,
            "hook_font": "Anton",
            "hook_heading_color": "#CBFF00",
            "hook_font_size": 100,
        }
        bridge = PipelineBridge(settings=user_settings)
        req = ClipRequest(url="https://youtube.com/watch?v=abc")
        job_data = bridge.build_job_data(req)

        # Should have all the fields the frontend would send
        assert job_data["api_provider"] == "openrouter"
        assert job_data["subtitle_config"]["style"] == "mozi"
        assert job_data["subtitle_config"]["font"] == "Montserrat-Bold"
        assert job_data["subtitle_config"]["fontsize"] == 55
        assert job_data["hook_styles"]["font"] == "Anton"
        assert job_data["hook_styles"]["color"] == "#CBFF00"
        assert job_data["hook_styles"]["font_size"] == 100
