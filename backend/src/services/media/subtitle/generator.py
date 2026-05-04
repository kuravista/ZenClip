from moviepy import CompositeVideoClip, TextClip, ColorClip
import os
import glob
from services.media.subtitle.utils.text import measure_real_height, split_text_to_max_lines
from services.media.subtitle.styles.karaoke import create_karaoke_subtitles
from services.media.subtitle.styles.rapid_fire import create_rapid_fire_subtitles
from services.media.subtitle.styles.mozi import create_mozi_subtitles
from services.media.subtitle.styles.shadow import create_shadow_subtitles
from services.media.subtitle.styles.boxies import create_boxies_subtitles
from services.media.subtitle.styles.pod_d import create_pod_d_subtitles

class ReelsSubtitleGenerator:
    def __init__(self, style_config=None):
        from services.media.subtitle.utils.fonts import get_font_path
        
        # Default font selection logic
        default_font = "Poppins-Medium"
        if style_config and style_config.get('style') == 'mozi':
             default_font = "Montserrat-Black"
        elif style_config and style_config.get('style') == 'elegant':
             default_font = "PlayfairDisplay-Italic"
        
        # Determine basic font name from config or default
        font_name = style_config.get('font', default_font) if style_config else default_font
        
        # Resolve path using centralized manager
        # If the user passed a path or filename, get_font_path handles it
        font_path = get_font_path(font_name)
        
        self.config = {
            "fontsize": 40,
            "font": font_path,
            "color": "white",
            "stroke_color": "black",
            "stroke_width": 0,
            "highlight_color": "#FFD700",
            "bg_opacity": 0.75,
            "margin_from_bottom": 180,
            "max_width_percent": 0.85,
            "audio_offset": 0.0,
            "debug_logging": True,
            "bg_color": "#2563eb",
            "glow_enabled": False,
            "glow_color": "#00FF00",
            "glow_radius": 12,
            "glow_intensity": 2,
            "vertical_position": 75,
        }

        if style_config:
            self.config.update(style_config)
            # Re-resolve font if it was in config
            if 'font' in style_config:
                 self.config['font'] = get_font_path(style_config['font'])

    # Legacy method support (used in old Phrase style fallbacks)
    def create_subtitle_clip(self, text, start_time, duration, video_size):
        try:
            video_w, video_h = video_size
            video_w, video_h = video_size

            approx_char_width = self.config["fontsize"] * 0.6
            max_chars_per_line = int((video_w * self.config["max_width_percent"]) / approx_char_width)
            max_chars_per_line = max(20, min(max_chars_per_line, 40))
            
            text_wrapped = split_text_to_max_lines(text, max_lines=2, max_chars_per_line=max_chars_per_line)
            max_width = int(video_w * self.config["max_width_percent"])
            text_with_space = text_wrapped + "\n "
            
            txt = TextClip(
                text=text_with_space.upper(),
                font=self.config["font"],
                font_size=self.config["fontsize"],
                color=self.config["color"],
                stroke_color=self.config["stroke_color"],
                stroke_width=self.config["stroke_width"],
                method="caption",
                size=(max_width, None),
                text_align="center",
            )
            txt = txt.with_fps(30)
            real_h = measure_real_height(txt, buffer=10)
            txt = txt.cropped(y2=real_h)
            
            padding_horizontal = 35
            padding_vertical = 20
            stroke_buffer = self.config["stroke_width"] * 2
            bg_w = txt.w + padding_horizontal * 2
            bg_h = txt.h + padding_vertical * 2 + stroke_buffer

            bg = ColorClip((int(bg_w), int(bg_h)), color=(0, 0, 0)).with_opacity(
                self.config["bg_opacity"]
            ).with_fps(30)
            
            txt_centered = txt.with_position(("center", "center"))
            subtitle = CompositeVideoClip([bg, txt_centered], size=(int(bg_w), int(bg_h)))
            subtitle = subtitle.with_start(start_time).with_duration(duration).with_fps(30)

            # Apply Smooth Animation (Fade In)
            try:
                from moviepy.video.fx import CrossFadeIn
                subtitle = subtitle.with_effects([CrossFadeIn(duration=0.1)])
            except ImportError:
                # Fallback for Phrase style
                class SimpleFadeIn:
                    def __init__(self, duration):
                        self.duration = duration
                    def copy(self):
                        return SimpleFadeIn(self.duration)
                    def apply(self, clip):
                        return clip.with_opacity(lambda t: min(1.0, max(0.0, t / self.duration)))
                
                subtitle = subtitle.with_effects([SimpleFadeIn(0.1)])
            
            
            safe_bottom_margin = self.config["margin_from_bottom"]

            # Fix for vertical jumping: Smart Anchoring
            # If multi-line, use single-line height for anchoring
            anchor_h = bg_h
            content_lines = text_wrapped.count('\n') + 1
            if content_lines > 1:
                # text_with_space has an extra line "\n ", so total lines is content_lines + 1
                total_clip_lines = content_lines + 1
                if total_clip_lines > 0:
                    one_line_h = txt.h / total_clip_lines
                    # We want to anchor as if it's 1 content line (+ 1 extra line)
                    anchor_txt_h = one_line_h * 2
                    anchor_h = anchor_txt_h + padding_vertical * 2 + stroke_buffer
            
            y_pos = video_h - safe_bottom_margin - anchor_h
            y_pos = max(80, y_pos)
            
            subtitle = subtitle.with_position(("center", int(y_pos)))
            return subtitle
            
        except Exception as e:
            print("❌ Subtitle creation error:", e)
            return None

    def create_word_subtitles(self, video_clip, phrase_timings, clip_start, clip_end):
        if not phrase_timings:
            return video_clip

        style = self.config.get('style', 'word')
        # Normalize: frontend sends 'rapid_fire', backend uses 'rapid'
        if style == 'rapid_fire':
            style = 'rapid'
        has_word_timings = any('words' in p for p in phrase_timings)
        glow_enabled = self.config.get('glow_enabled', False)

        clips = []

        if has_word_timings and style != 'phrase':
            if style == 'rapid':
                 clips = create_rapid_fire_subtitles(self.config, video_clip, phrase_timings, clip_start, clip_end)
            elif style == 'rapid_pro':
                 from services.media.subtitle.styles.rapid_pro import create_rapid_pro_subtitles
                 clips = create_rapid_pro_subtitles(self.config, video_clip, phrase_timings, clip_start, clip_end)
            elif style == 'pod_d':
                 clips = create_pod_d_subtitles(self.config, video_clip, phrase_timings, clip_start, clip_end)
            elif style == 'mozi':
                 clips = create_mozi_subtitles(self.config, video_clip, phrase_timings, clip_start, clip_end)
            elif style == 'elegant':
                 clips = create_elegant_subtitles(self.config, video_clip, phrase_timings, clip_start, clip_end)
            elif style == 'boxies':
                 clips = create_boxies_subtitles(self.config, video_clip, phrase_timings, clip_start, clip_end)
            elif style == 'shadow':
                 from services.media.subtitle.styles.shadow import create_shadow_subtitles
                 clips = create_shadow_subtitles(self.config, video_clip, phrase_timings, clip_start, clip_end)
            else:
                 clips = create_karaoke_subtitles(self.config, video_clip, phrase_timings, clip_start, clip_end)
        else:
            # Phrase style using legacy create_subtitle_clip
            all_items = sorted(phrase_timings, key=lambda x: x['start'])
            for i, item in enumerate(all_items):
                if item['end'] > clip_start and item['start'] < clip_end:
                    start = max(0, item['start'] - clip_start)
                    end = min(clip_end - clip_start, item['end'] - clip_start)
                    
                    if i < len(all_items) - 1:
                        next_item = all_items[i+1]
                        if next_item['start'] < clip_end:
                            next_start = max(0, next_item['start'] - clip_start)
                            if end > next_start:
                                end = next_start
                    
                    dur = end - start
                    if dur >= 0.4:
                        sub = self.create_subtitle_clip(
                            item['text'], start, dur, video_clip.size
                        )
                        if sub: clips.append(sub)

        if not clips:
            return video_clip

        try:
            final = CompositeVideoClip([video_clip] + clips)
            final = final.with_fps(video_clip.fps if hasattr(video_clip, 'fps') and video_clip.fps else 30)
            return final
        except Exception as e:
            print(f"❌ Error creating composite clip: {e}")
            # Cleanup generated clips to prevent memory leaks
            for clip in clips:
                try:
                    clip.close()
                except:
                    pass
            raise e

def add_subtitles_to_video(video_clip, word_timings, clip_start, clip_end, style_config=None):
    generator = ReelsSubtitleGenerator(style_config)
    return generator.create_word_subtitles(video_clip, word_timings, clip_start, clip_end)
