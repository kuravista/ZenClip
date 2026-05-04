import sys
import os
from moviepy import ColorClip
import traceback

# Ensure we can import from services
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from services.media.subtitle.styles.rapid_pro import create_rapid_pro_subtitles
from services.media.subtitle.ass_generator import generate_ass_file
from services.media.subtitle.utils.fonts import get_font_path

def test_rapid_pro_generation():
    print("\n=== Testing Rapid Pro Style (MoviePy & ASS) ===")

    # 1. Setup Mock Data
    video_w, video_h = 1080, 1920
    duration = 5.0
    video_clip = ColorClip(size=(video_w, video_h), color=(0, 0, 0), duration=duration).with_fps(30)
    
    # 3-word chunks logic test:
    # "One" -> White
    # "Two Three" -> Highlight, Highlight
    # "Four Five Six" -> White, Highlight, Highlight
    phrase_timings = [
        {
            "text": "One",
            "start": 0.0, "end": 0.5,
            "words": [{"text": "One", "start": 0.0, "end": 0.5}]
        },
        {
            "text": "Two Three",
            "start": 1.0, "end": 2.0,
            "words": [
                {"text": "Two", "start": 1.0, "end": 1.5},
                {"text": "Three", "start": 1.5, "end": 2.0}
            ]
        },
        {
            "text": "Four Five Six",
            "start": 2.5, "end": 4.0,
            "words": [
                {"text": "Four", "start": 2.5, "end": 3.0},
                {"text": "Five", "start": 3.0, "end": 3.5},
                {"text": "Six", "start": 3.5, "end": 4.0}
            ]
        }
    ]

    config = {
        "fontsize": 60,
        "style": "rapid_pro",
        "color": "white",
        "highlight_color": "yellow",
        "stroke_width": 2,
        "font": "Arial" # System font for test safety
    }

    # 2. Test MoviePy Generation
    print("\n--- Testing MoviePy Clip Generation ---")
    try:
        clips = create_rapid_pro_subtitles(config, video_clip, phrase_timings, 0, duration)
        print(f"✅ Created {len(clips)} composite clips")
        if len(clips) > 0:
            print("  Sample Clip 1 Duration:", clips[0].duration)
            # We expect 1 clip per chunk.
            # Chunk 1 (One) = 1 clip? No, rapid_pro groups words.
            # rapid_pro creates a list of clips.
            # "One" (1 chunk) -> 0.5s
            # "Two Three" (1 chunk) -> 1.0s
            # "Four Five Six" (1 chunk) -> 1.5s
            # Total expected clips depends on how create_rapid_pro_subtitles constructs them.
            # It returns `subtitle_clips` which is a list of CompositeVideoClip or TextClip.
            # Logic: `subtitle_clips.extend(final_composite_clips)` where final_composite_clips is per word in chunk?
            # Looking at code: `final_composite_clips.append(clip)` for each word in temp_clips.
            # So "One" -> 1 clip. "Two Three" -> 2 clips. "Four Five Six" -> 3 clips. Total 6 clips.
            print(f"  Expected approx 6 clips. Got {len(clips)}")

            # Composite and Save
            print("  writing video file...")
            from moviepy import CompositeVideoClip
            final = CompositeVideoClip([video_clip] + clips)
            output_filename = "rapid_pro_test_output.mp4"
            final.write_videofile(output_filename, fps=24)
            print(f"✅ Video saved to {output_filename}")
            
    except Exception as e:
        print(f"❌ MoviePy Failed: {e}")
        traceback.print_exc()

    # 3. Test ASS Generation
    print("\n--- Testing ASS Generation ---")
    ass_path = "test_rapid_pro.ass"
    try:
        success = generate_ass_file(ass_path, phrase_timings, 0, duration, (video_w, video_h), config)
        if success:
            print(f"✅ ASS file generated at {ass_path}")
            
            # Verify content logic if possible
            with open(ass_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
            # Check for color codes logic
            # Chunk 1: "One" -> White (&H00FFFFFF)
            # Chunk 2: "Two Three" -> Yellow (&H0000D7FF in ASS BGR)
            # Check if HighlightBox style exists
            if "Style: HighlightBox" in content:
                print("  ✅ Found HighlightBox style")
            
            # Simple check for line count
            start_lines = [l for l in content.split('\n') if l.startswith('Dialogue:')]
            print(f"  Generated {len(start_lines)} dialogue events")
            
            # Cleanup
            if os.path.exists(ass_path):
                os.remove(ass_path)
        else:
            print("❌ ASS Generation returned False")
    except Exception as e:
        print(f"❌ ASS Generation Failed: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    test_rapid_pro_generation()
