
import os
import sys
import traceback
from moviepy import ColorClip
from services.subtitle.utils.fonts import get_font_path, _font_manager
from services.subtitle.styles.mozi import create_mozi_subtitles
from services.subtitle.styles.rapid_fire import create_rapid_fire_subtitles
from services.subtitle.ass_generator import generate_ass_file

def test_font_manager():
    print("\n=== Testing Font Manager ===")
    print(f"Loaded fonts: {len(_font_manager._fonts_cache)}")
    
    test_fonts = ["Arial", "Poppins-Bold", "Montserrat-Black", "NonExistentFont"]
    for f in test_fonts:
        path = get_font_path(f)
        print(f"Font '{f}' -> {path}")

def test_generators():
    print("\n=== Testing Generators ===")
    
    # 1. Setup Mock Data
    video_w, video_h = 1080, 1920
    duration = 5.0
    video_clip = ColorClip(size=(video_w, video_h), color=(0, 0, 0), duration=duration).with_fps(30)
    
    phrase_timings = [
        {
            "text": "Hello world testing mozi style",
            "start": 0.5,
            "end": 2.5,
            "words": [
                {"text": "Hello", "start": 0.5, "end": 0.9},
                {"text": "world", "start": 0.9, "end": 1.3},
                {"text": "testing", "start": 1.3, "end": 1.8},
                {"text": "mozi", "start": 1.8, "end": 2.2},
                {"text": "style", "start": 2.2, "end": 2.5},
            ]
        },
        {
            "text": "Phase two rapid fire",
            "start": 3.0,
            "end": 4.5,
            "words": [
                {"text": "Phase", "start": 3.0, "end": 3.4},
                {"text": "two", "start": 3.4, "end": 3.8},
                {"text": "rapid", "start": 3.8, "end": 4.2},
                {"text": "fire", "start": 4.2, "end": 4.5},
            ]
        }
    ]
    
    # 2. Test Mozi
    print("\n--- Testing Mozi Style ---")
    mozi_config = {
        "font": "Montserrat-Black",
        "fontsize": 60,
        "style": "mozi",
        "color": "white",
        "stroke_width": 4
    }
    
    try:
        clips = create_mozi_subtitles(mozi_config, video_clip, phrase_timings, 0, duration)
        print(f"✅ Mozi created {len(clips)} composite clips")
    except Exception as e:
        print(f"❌ Mozi Failed: {e}")
        traceback.print_exc()

    # 3. Test Rapid Fire
    print("\n--- Testing Rapid Fire Style ---")
    rapid_config = {
        "font": "Poppins-Bold",
        "fontsize": 70,
        "style": "rapid",
        "color": "yellow"
    }
    
    try:
        clips = create_rapid_fire_subtitles(rapid_config, video_clip, phrase_timings, 0, duration)
        print(f"✅ Rapid Fire created {len(clips)} text clips")
    except Exception as e:
        print(f"❌ Rapid Fire Failed: {e}")
        traceback.print_exc()

    # 4. Test ASS Generator
    print("\n--- Testing ASS Generator ---")
    ass_path = "test_output.ass"
    ass_config = {"style": "mozi", "fontsize": 40}
    try:
        success = generate_ass_file(ass_path, phrase_timings, 0, duration, (video_w, video_h), ass_config)
        if success:
            print(f"✅ ASS file generated at {ass_path}")
            # Clean up
            if os.path.exists(ass_path):
                os.remove(ass_path)
        else:
            print("❌ ASS Generation returned False")
    except Exception as e:
        print(f"❌ ASS Generation Failed: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    test_font_manager()
    test_generators()
