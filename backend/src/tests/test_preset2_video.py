"""
Generate a test video with Preset 2 hook overlay
This creates a simple video to verify the rendering works correctly
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from moviepy import VideoFileClip, ColorClip, CompositeVideoClip
from services.media.subtitle.preset2_hook import _render_preset2_hook
import traceback

def create_test_video():
    """Generate a test video with Preset 2 hook"""
    print("=" * 60)
    print("PRESET 2 HOOK - VIDEO TEST")
    print("=" * 60)
    
    try:
        # Create a simple 5-second background clip (9:16 vertical)
        print("\n[1/4] Creating background clip...")
        width, height = 1080, 1920  # 9:16 vertical
        duration = 5.0
        
        # Create a gradient background (dark blue to purple)
        background = ColorClip(size=(width, height), color=(30, 20, 60), duration=duration)
        print(f"✅ Background created: {width}x{height}, {duration}s")
        
        # Test hook configuration
        print("\n[2/4] Setting up Preset 2 hook...")
        hook_styles = {
            'hook_style': 'preset-2',
            'preset2_content': 'this might be *the best* **BUDGET** wireless microphone',
            'highlight_color': '#CBFF00',  # Lime
            'color': '#FFFFFF',  # White
            'font': 'Impact',
            'font_size': 80,
            'stroke_width': 2,
            'stroke_color': '#000000'
        }
        
        print(f"Text: {hook_styles['preset2_content']}")
        print(f"Highlight Color: {hook_styles['highlight_color']}")
        
        # Render Preset 2 hook
        print("\n[3/4] Rendering Preset 2 hook overlay...")
        
        class MockConfig:
            pass
        
        hook_overlay = _render_preset2_hook(
            config=MockConfig(),
            hook_styles=hook_styles,
            video_width=width,
            video_height=height,
            duration=duration
        )
        
        if hook_overlay:
            print("✅ Hook overlay rendered successfully")
            
            # Compose video
            print("\n[4/4] Compositing video...")
            final_video = CompositeVideoClip([background, hook_overlay])
            final_video = final_video.with_duration(duration)
            
            # Output path
            output_path = os.path.join(os.path.dirname(__file__), '..', '..', 'static', 'test_preset2_output.mp4')
            output_path = os.path.abspath(output_path)
            
            print(f"\n📹 Writing video to: {output_path}")
            print("⏳ This may take a moment...")
            
            # Write video
            final_video.write_videofile(
                output_path,
                fps=30,
                codec='libx264',
                audio=False,
                preset='ultrafast',
                logger=None  # Suppress moviepy logs
            )
            
            print("\n" + "=" * 60)
            print("✅ SUCCESS! Test video created successfully!")
            print("=" * 60)
            print(f"\n📁 Output: {output_path}")
            print(f"📊 Duration: {duration}s")
            print(f"📐 Resolution: {width}x{height} (9:16)")
            print("\n🎬 Open the video to see Preset 2 hook in action!")
            print("   - Regular text in white")
            print("   - *the best* in italic")
            print("   - **BUDGET** in bold + lime color")
            print("=" * 60)
            
            # Cleanup
            background.close()
            if hook_overlay:
                hook_overlay.close()
            final_video.close()
            
            return output_path
            
        else:
            print("❌ Hook overlay failed to render")
            return None
            
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        traceback.print_exc()
        return None

if __name__ == "__main__":
    print("\n🎯 Generating Preset 2 Test Video...\n")
    output = create_test_video()
    
    if output:
        print(f"\n✅ Test completed! Video saved to:\n   {output}")
    else:
        print("\n❌ Test failed. Check errors above.")
