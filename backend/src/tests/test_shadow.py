import sys
import os
from moviepy import ColorClip
import traceback

# Ensure we can import from services
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from services.media.subtitle.styles.shadow import create_shadow_subtitles
from services.media.subtitle.utils.fonts import get_font_path

def test_shadow_generation():
    print("\n=== Testing Shadow Style ===")

    # 1. Setup Mock Data
    video_w, video_h = 1080, 1920
    duration = 5.0
    video_clip = ColorClip(size=(video_w, video_h), color=(255, 255, 0), duration=duration).with_fps(60)
    
    # 8-word chunk test (should be 2 lines)
    long_text = "This is a much longer test to verify that the shadow style correctly splits text into multiple lines and handles larger chunks of words appropriately without breaking the layout or the animation style."
    words = long_text.split()
    
    # Generate simple timing
    word_duration = 0.3
    p_timings = []
    current_time = 0.0
    
    for i, w in enumerate(words):
        p_timings.append({
            "text": w,
            "start": current_time,
            "end": current_time + word_duration
        })
        current_time += word_duration + 0.05
        
    phrase_timings = [
        {
            "text": long_text,
            "start": 0.0,
            "end": current_time,
            "words": p_timings
        }
    ]

    config = {
        "fontsize": 60,
        "style": "shadow",
        "color": "white",
        "stroke_color": "black",
        "shadow_color": "black",
        "shadow_offset": 8,
        "font": "Arial"
    }

    # 2. Test MoviePy Generation
    print("\n--- Testing MoviePy Clip Generation ---")
    try:
        clips = create_shadow_subtitles(config, video_clip, phrase_timings, 0, duration)
        print(f"✅ Created {len(clips)} composite clips")
        if len(clips) > 0:
            print("  Sample Clip 1 Duration:", clips[0].duration)
            
            # Composite and Save
            print("  writing video file...")
            from moviepy import CompositeVideoClip
            final = CompositeVideoClip([video_clip] + clips)
            output_filename = "shadow_test_output.mp4"
            final.write_videofile(output_filename, fps=60)
            print(f"✅ Video saved to {output_filename}")
            
    except Exception as e:
        print(f"❌ MoviePy Failed: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    test_shadow_generation()
