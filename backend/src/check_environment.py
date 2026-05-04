
import cv2
import os
import sys

print(f"OpenCV Version: {cv2.__version__}")
print(f"Haar Cascades Path: {cv2.data.haarcascades}")

cascades = {
    'frontal_default': 'haarcascade_frontalface_default.xml',
    'frontal_alt': 'haarcascade_frontalface_alt.xml',
    'profile': 'haarcascade_profileface.xml',
}
 
print("\n--- Checking Cascades ---")
for name, filename in cascades.items():
    path = os.path.join(cv2.data.haarcascades, filename)
    exists = os.path.exists(path)
    
    # Try loading
    clf = cv2.CascadeClassifier(path)
    loaded = not clf.empty()
    
    status = "✅ OK" if (exists and loaded) else "❌ MISSING/FAILED"
    print(f"{name:<20} : {filename:<35} {status}")
    if not loaded:
        print(f"   -> Path: {path}")

print("\n--- Checking MediaPipe ---")
try:
    import mediapipe as mp
    print(f"MediaPipe Version: {mp.__version__}")
    
    if hasattr(mp.solutions, 'face_detection'):
        print("✅ mp.solutions.face_detection is available")
        fd = mp.solutions.face_detection.FaceDetection(model_selection=1)
        print("✅ FaceDetection initialized successfully")
        fd.close()
    else:
        print("❌ mp.solutions.face_detection MISSING")

except ImportError:
    print("❌ MediaPipe NOT INSTALLED")
except Exception as e:
    print(f"❌ MediaPipe Error: {e}")
