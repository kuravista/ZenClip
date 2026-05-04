
import os
import sys
import time
from moviepy import VideoFileClip

# Setup paths to ensure imports work
sys.path.append(os.getcwd())
sys.path.append(os.path.join(os.getcwd(), 'Backend', 'src'))

try:
    from face_detector import analyze_face_positions
    from services.smart_crop import calculate_smart_crop
    print("[INFO] Imports successful")
except ImportError as e:
    print(f"[ERROR] Import failed: {e}")
    sys.exit(1)

def test_video(filename):
    video_path = os.path.join(os.getcwd(), filename)
    
    if not os.path.exists(video_path):
        print(f"[ERROR] File not found: {video_path}")
        return

    print(f"\n{'='*60}")
    print(f"TESTING VIDEO: {filename}")
    print(f"{'='*60}")

    try:
        clip = VideoFileClip(video_path)
        print(f"[INFO] Video loaded. Duration: {clip.duration:.2f}s, Size: {clip.size}")

        # 1. Test Face Detection
        print("\n[STEP 1] Running Face Detection (Analysis)...")
        start_t = time.time()
        
        # Run analysis
        face_result = analyze_face_positions(clip, num_samples=20)
        
        print(f"   > Detection Rate: {face_result['detection_rate']:.1%}")
        print(f"   > Avg Face Center X: {face_result['avg_center_x']} px")
        print(f"   > Detected: {face_result['detected']}")
        print(f"   > Time taken: {time.time() - start_t:.2f}s")

        # 2. Test Smart Crop Calculation
        print("\n[STEP 2] Calculating Smart Crop...")
        crop_params = calculate_smart_crop(
            face_result['positions'], 
            clip.w, 
            clip.h, 
            target_aspect=(9, 16)
        )
        
        print(f"   > Crop X: {crop_params['x']}")
        print(f"   > Crop Y: {crop_params['y']}")
        print(f"   > Crop Width: {crop_params['width']}")
        print(f"   > Crop Height: {crop_params['height']}")
        
        
        # 3. Validation
        center_x_metric = face_result['avg_center_x']
        frame_center = clip.w // 2
        
        print("\n[STEP 3] Analysis")
        if face_result['detected']:
            diff = center_x_metric - frame_center
            direction = "Right" if diff > 0 else "Left"
            print(f"   > Subject appears to be {abs(diff)}px to the {direction} of center.")
            print("   > Smart crop should compensate for this.")
        else:
            print("   > No face detected. Fallback logic used.")
            
        # 4. Generate Output Video
        print("\n[STEP 4] Generating Output Video...")
        x1 = int(crop_params['x'])
        y1 = int(crop_params['y'])
        width = int(crop_params['width'])
        height = int(crop_params['height'])
        
        # Apply Crop
        final_clip = clip.cropped(x1=x1, y1=y1, width=width, height=height)
        
        # Resize to standard 9:16 (1080w) if needed for preview
        # Or just keep as is (cropped aspect ratio is correct)
        
        # Limit duration for test speed (e.g. 10 seconds) unless short
        if final_clip.duration > 15:
            print("   > Trimming to 15s for quick test generation...")
            final_clip = final_clip.subclipped(0, 15)
            
        output_filename = f"{os.path.splitext(filename)[0]}_cropped.mp4"
        output_path = os.path.join(os.getcwd(), output_filename)
        
        print(f"   > Writing to: {output_filename}")
        final_clip.write_videofile(output_path, codec="libx264", audio_codec="aac", fps=30)
        print(f"\n✅ Video Generated: {output_filename}")

        clip.close()
        final_clip.close()
        print("\n✅ Test Complete")

    except Exception as e:
        print(f"❌ Error during test: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # Target video from user request
    target_file = "raditiya.mp4"
    test_video(target_file)
