import sys
import os
from moviepy import ColorClip
import traceback

# Ensure we can import from services
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from services.media.subtitle.styles.pod_d import create_pod_d_subtitles

def test_pod_d_generation():
    print("\n=== Testing Pod D Style (MoviePy) ===")

    # 1. Setup Mock Data
    video_w, video_h = 1080, 1920
    duration = 5.0
    video_clip = ColorClip(size=(video_w, video_h), color=(50, 50, 50), duration=duration).with_fps(60)
    
    # Mock text: "Welcome to the Pod D show everyone"
    phrase_timings = [
        {
            "text": "Welcome to the",
            "start": 0.0, "end": 1.5,
            "words": [
                {"text": "Welcome", "start": 0.0, "end": 0.5},
                {"text": "to", "start": 0.5, "end": 1.0},
                {"text": "the", "start": 1.0, "end": 1.5}
            ]
        },
        {
            "text": "Pod D show",
            "start": 1.5, "end": 3.0,
            "words": [
                {"text": "Pod", "start": 1.5, "end": 2.0},
                {"text": "D", "start": 2.0, "end": 2.5},
                {"text": "show", "start": 2.5, "end": 3.0}
            ]
        },
        {
            "text": "everyone",
            "start": 3.0, "end": 4.0,
            "words": [
                {"text": "everyone", "start": 3.0, "end": 4.0}
            ]
        }
    ]

    config = {
        "fontsize": 80,
        "style": "pod_d",
        "color": "#FFB6C1", # Pink (frontend default)
        "stroke_color": "black",
        "stroke_width": 4, # Frontend default is 4
        "font": "Arial" # System font for test safety
    }

    # 2. Test MoviePy Generation
    print("\n--- Testing MoviePy Clip Generation ---")
    try:
        clips = create_pod_d_subtitles(config, video_clip, phrase_timings, 0, duration)
        print(f"✅ Created {len(clips)} composite clips")
        
        if len(clips) > 0:
            # Composite and Save
            print("  writing video file...")
            from moviepy import CompositeVideoClip
            final = CompositeVideoClip([video_clip] + clips)
            output_filename = "pod_d_test_output.mp4"
            final.write_videofile(output_filename, fps=60, codec='libx264')
            print(f"✅ Video saved to {os.path.abspath(output_filename)}")
            
    except Exception as e:
        print(f"❌ MoviePy Failed: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    test_pod_d_generation()
