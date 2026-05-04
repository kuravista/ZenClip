"""
Face Detection Module using MediaPipe
Provides accurate face detection for smart video cropping
"""

import cv2
import numpy as np
import time
import os
import sys
from threading import Lock
from dataclasses import dataclass
from typing import Optional, Dict, Tuple, List, Any

# Try to import mediapipe, fallback to OpenCV if not available
try:
    import mediapipe as mp
    # Check if solutions is actually available (common issue on some M1 installs)
    try:
        _ = mp.solutions.face_detection
        MEDIAPIPE_AVAILABLE = True
    except AttributeError:
        MEDIAPIPE_AVAILABLE = False
        print("[WARN] MediaPipe installed but 'solutions' attribute missing. Using OpenCV fallback.")
except ImportError:
    MEDIAPIPE_AVAILABLE = False
    print("[WARN] MediaPipe not installed. Using OpenCV Haar Cascade fallback.")
    print("   Install with: pip install mediapipe")

# Try to import scipy for advanced smoothing
try:
    from scipy.ndimage import gaussian_filter1d
    from scipy.signal import savgol_filter
    from scipy.interpolate import CubicSpline
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False
    print("[WARN] SciPy not installed. Advanced smoothing will be limited.")
    print("   Install with: pip install scipy")


@dataclass
class DetectionMetrics:
    total_frames: int
    detected_frames: int
    avg_confidence: float
    processing_time_ms: float


@dataclass
class TrackingSmoothingConfig:
    """Configuration for professional face tracking - optimized for short-form content."""
    
    # Gaussian smoothing
    gaussian_sigma: float = 1.5          # Lower = tighter tracking (was 2.5)
    gaussian_passes: int = 2              # Fewer passes = less delay (was 3)
    
    # Velocity limiting
    max_pan_speed_pct: float = 0.30      # 30% of frame width per second (Fast/Snappy)
    
    # Bezier easing
    ease_in_duration: float = 0.2        # Fast acceleration
    ease_out_duration: float = 0.2       # Fast deceleration
    
    # Sampling
    sample_interval: float = 0.25        # Optimized sampling (0.25s / 4 FPS) for better performance
    
    # Deadband - STABILIZED (prevent micro-movements when centered)
    deadband_threshold_pct: float = 0.08  # 8% of frame (prevents jitter when centered)
    deadband_ramp: float = 0.05          # Smooth ramp zone
    
    # Hold time - STABLE (prevent reaction to brief side detections)
    hold_time_sec: float = 0.4           # 400ms stability before moving
    hold_distance_threshold_pct: float = 0.05
    
    # Focus switching - CONFIDENT (don't chase every new detection)
    focus_switch_delay_sec: float = 0.3  # 300ms confirmation before switching focus
    focus_switch_threshold_pct: float = 0.12  # 12% screen = focus switch
    progressive_transition: bool = True   
    
    # Filter selection
    use_one_euro: bool = True            # Critical for low-latency smoothing
    use_savitzky_golay: bool = True
    
    # One Euro Params (Advanced)
    one_euro_min_cutoff: float = 1.0     # Responsiveness at low speed (default 1.5 in user snippet but 1.0 is standard)
    one_euro_beta: float = 0.05          # Responsiveness at high speed
    
    # Sticky tracking - Prevents distraction by background subjects
    sticky_tracking_penalty: float = 4.5  # Strong preference for current subject
    
    # Motion-based filtering - EXCLUDE STATIC FACES (banners, posters)
    min_motion_threshold: float = 2.0    # Minimum pixel variance to consider face "moving"
    static_face_timeout: float = 1.0     # Seconds of no movement before face is ignored
    motion_probation_frames: int = 10    # New faces must show movement within N frames



class OneEuroFilter:
    """One Euro Filter for smooth tracking with low latency.
    
    Used by Snapchat, Instagram, and professional motion capture systems.
    Provides excellent smoothing while maintaining responsiveness.
    
    Reference: http://cristal.univ-lille.fr/~casiez/1euro/
    """
    def __init__(self, min_cutoff=1.0, beta=0.007, d_cutoff=1.0):
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.d_cutoff = d_cutoff
        self.x_prev = None
        self.dx_prev = 0.0
        self.t_prev = None
    
    def __call__(self, x, t=None):
        """Filter a new value."""
        if t is None:
            t = time.time()
        
        # Initialize
        if self.x_prev is None:
            self.x_prev = x
            self.t_prev = t
            return x
        
        # Calculate time delta
        dt = t - self.t_prev
        if dt <= 0:
            dt = 0.001  # Prevent division by zero
        
        # Calculate derivative
        dx = (x - self.x_prev) / dt
        
        # Smooth derivative
        alpha_d = self._alpha(dt, self.d_cutoff)
        dx_smooth = alpha_d * dx + (1 - alpha_d) * self.dx_prev
        
        # Calculate cutoff
        cutoff = self.min_cutoff + self.beta * abs(dx_smooth)
        
        # Filter signal
        alpha = self._alpha(dt, cutoff)
        x_filtered = alpha * x + (1 - alpha) * self.x_prev
        
        # Save state
        self.x_prev = x_filtered
        self.dx_prev = dx_smooth
        self.t_prev = t
        
        return x_filtered
    
    def _alpha(self, dt, cutoff):
        """Calculate smoothing factor."""
        tau = 1.0 / (2 * np.pi * cutoff)
        return 1.0 / (1.0 + tau / dt)


def apply_gaussian_smoothing(values: np.ndarray, sigma: float = 2.5, passes: int = 3) -> np.ndarray:
    """Apply multi-pass Gaussian smoothing for cinema-quality motion.
    
    Args:
        values: Array of position values
        sigma: Standard deviation for Gaussian kernel (higher = smoother)
        passes: Number of smoothing passes (3 is industry standard)
    
    Returns:
        Smoothed values array
    """
    if not SCIPY_AVAILABLE:
        # Fallback: simple moving average
        return _simple_moving_average(values, window=int(sigma * 2) + 1)
    
    smoothed = values.copy().astype(float)
    for _ in range(passes):
        smoothed = gaussian_filter1d(smoothed, sigma=sigma, mode='nearest')
    return smoothed


def apply_savitzky_golay_filter(values: np.ndarray, window_length: int = 11, polyorder: int = 3) -> np.ndarray:
    """Apply Savitzky-Golay filter for polynomial smoothing.
    
    Preserves peaks and shapes better than Gaussian smoothing.
    
    Args:
        values: Array of position values
        window_length: Length of filter window (must be odd)
        polyorder: Order of polynomial (usually 2 or 3)
    
    Returns:
        Smoothed values array
    """
    if not SCIPY_AVAILABLE or len(values) < window_length:
        return values
    
    # Ensure window_length is odd and valid
    if window_length % 2 == 0:
        window_length += 1
    window_length = min(window_length, len(values))
    if window_length < polyorder + 2:
        return values
    
    return savgol_filter(values, window_length, polyorder, mode='nearest')


def _simple_moving_average(values: np.ndarray, window: int = 5) -> np.ndarray:
    """Fallback smoothing using simple moving average."""
    if len(values) < window:
        return values
    
    smoothed = np.copy(values)
    half_window = window // 2
    
    for i in range(len(values)):
        start = max(0, i - half_window)
        end = min(len(values), i + half_window + 1)
        smoothed[i] = np.mean(values[start:end])
    
    return smoothed


def limit_velocity(positions: np.ndarray, times: np.ndarray, 
                   max_speed_pct: float = 0.15, frame_width: int = 1920) -> np.ndarray:
    """Limit maximum pan speed to maintain professional look.
    
    Prevents jarring quick pans that look unprofessional.
    
    Args:
        positions: Array of x positions
        times: Corresponding time values
        max_speed_pct: Max speed as % of frame width per second (0.15 = 15%)
        frame_width: Width of video frame in pixels
    
    Returns:
        Velocity-limited positions
    """
    if len(positions) < 2:
        return positions
    
    max_pixels_per_sec = frame_width * max_speed_pct
    limited = np.copy(positions).astype(float)
    
    for i in range(1, len(positions)):
        dt = times[i] - times[i-1]
        if dt <= 0:
            continue
        
        max_delta = max_pixels_per_sec * dt
        actual_delta = positions[i] - limited[i-1]
        
        # Clamp delta
        if abs(actual_delta) > max_delta:
            clamped_delta = np.sign(actual_delta) * max_delta
            limited[i] = limited[i-1] + clamped_delta
    
    return limited


def create_bezier_interpolator(keyframes: List['KeyframePosition'], clip_width: int,
                               ease_duration: float = 0.3) -> callable:
    """Create smooth Bezier interpolation with ease-in/ease-out.
    
    Args:
        keyframes: List of KeyframePosition objects
        clip_width: Width of video frame
        ease_duration: Time for acceleration/deceleration (seconds)
    
    Returns:
        Interpolation function that takes time and returns x position
    """
    if not keyframes:
        return lambda t: clip_width / 2
    
    times = np.array([k.time for k in keyframes])
    positions = np.array([k.center_x for k in keyframes])
    
    if not SCIPY_AVAILABLE or len(keyframes) < 3:
        # Fallback to linear interpolation
        return lambda t: np.interp(t, times, positions)
    
    # Use cubic spline for smooth interpolation
    # bc_type='natural' provides smoothest curves
    spline = CubicSpline(times, positions, bc_type='natural')
    
    return lambda t: float(spline(np.clip(t, times[0], times[-1])))


def cubic_bezier(t: float, p0: float, p1: float, p2: float, p3: float) -> float:
    """Cubic Bezier interpolation.
    
    Args:
        t: Parameter (0 to 1)
        p0, p1, p2, p3: Control points
    
    Returns:
        Interpolated value
    """
    u = 1 - t
    return (u**3 * p0 + 
            3 * u**2 * t * p1 + 
            3 * u * t**2 * p2 + 
            t**3 * p3)


class FaceTracker:
    """
    Tracks faces across video frames for smart cropping.
    Uses MediaPipe for accurate detection, with OpenCV fallback.
    Thread-safe and context-manager compatible.
    """
    
    # ... (existing imports) ...
from collections import deque
import time

class FaceTrack:
    """
    State object for a single tracked face.
    Maintains history to calculate 'visual activity' (talking movement).
    Filters out static faces (banners, posters) based on movement.
    """
    def __init__(self, track_id: int, initial_box: Dict[str, Any]):
        self.track_id = track_id
        self.last_seen = time.time()
        self.box = initial_box
        self.center_history = deque(maxlen=15)  # Store last ~0.5s of positions (at 30fps)
        self.center_history.append((initial_box['center_x'], initial_box['center_y']))
        
        self.locked_score = 0.0 # Accumulated dominance score
        
        # Motion tracking for static face filtering
        self.frames_tracked = 0
        self.last_motion_time = time.time()
        self.consecutive_static_checks = 0
        self.is_confirmed_moving = False  # Passed probation period
        
    def update(self, new_box: Dict[str, Any]):
        self.last_seen = time.time()
        self.box = new_box
        self.center_history.append((new_box['center_x'], new_box['center_y']))
        self.frames_tracked += 1
        
        # Check if this update shows movement
        motion = self.get_motion_score()
        if motion > 0.5:  # Small threshold for any movement
            self.last_motion_time = time.time()
            self.consecutive_static_checks = 0
            
            # Auto-confirm moving status if we have enough motion during probation
            if not self.is_confirmed_moving and motion > 2.0:
                self.is_confirmed_moving = True
        else:
            self.consecutive_static_checks += 1
        
    def get_motion_score(self) -> float:
        """Calculate variance of position (visual activity)"""
        if len(self.center_history) < 3:
            return 0.0
            
        # Calculate standard deviation of X/Y movement
        xs = [p[0] for p in self.center_history]
        ys = [p[1] for p in self.center_history]
        var_x = np.var(xs)
        var_y = np.var(ys)
        
        # Combined variance as motion energy
        return np.sqrt(var_x + var_y)
    
    def is_static(self, threshold: float = 2.0) -> bool:
        """Check if face has been static (no significant movement)"""
        motion = self.get_motion_score()
        return motion < threshold
    
    def get_time_since_movement(self) -> float:
        """Get seconds since last significant movement"""
        return time.time() - self.last_motion_time
    
    def is_in_probation(self, probation_frames: int = 10) -> bool:
        """Check if face is still in probation period (needs to prove movement)"""
        return self.frames_tracked < probation_frames and not self.is_confirmed_moving
    
    def should_be_filtered(self, config: TrackingSmoothingConfig) -> bool:
        """Determine if this face should be filtered out (likely a banner/poster)"""
        # Need minimum frames to calculate motion reliably
        if self.frames_tracked < 3:
            return False  # Too early to judge, give it a chance
        
        # In probation: must show movement
        if self.is_in_probation(config.motion_probation_frames):
            if self.is_static(config.min_motion_threshold):
                return True  # Static during probation = likely banner
            else:
                self.is_confirmed_moving = True  # Passed probation!
                return False
        
        # After probation: allow brief pauses but timeout if too long
        if self.is_static(config.min_motion_threshold):
            time_static = self.get_time_since_movement()
            if time_static > config.static_face_timeout:
                return True  # Been static too long
        
        return False

class FaceTracker:
    def __init__(self, smoothing_factor: float = 0.3, config: Optional[TrackingSmoothingConfig] = None):
        """
        Initialize the face tracker.
        
        Args:
            smoothing_factor: Legacy parameter (kept for compat), now using OneEuroFilter.
            config: Configuration for tracking smoothing and motion filtering
        """
        self._lock = Lock()
        self.smoothing_factor = smoothing_factor
        self.last_face_center = None
        self.last_face_box = None
        
        # Configuration
        self.config = config if config is not None else TrackingSmoothingConfig()
        
        # Initialize One Euro Filters for X and Y
        # TUNED FOR CINEMATIC SMOOTHNESS ("Heavy Gimbal"):
        # min_cutoff: 0.01 (Extremely filtered when slow)
        # beta: 0.05 (Very lazy/smooth response to movement)
        self.filter_x = OneEuroFilter(min_cutoff=0.01, beta=0.05)
        self.filter_y = OneEuroFilter(min_cutoff=0.01, beta=0.05)
        
        # DEADBAND STATE
        self.deadband_center: Optional[Tuple[float, float]] = None
        
        # MULTI-FACE TRACKING STATE
        self.tracks: List[FaceTrack] = []
        self.next_track_id = 1
        self.active_track_id: Optional[int] = None
        self.last_switch_time = 0.0
        
        if MEDIAPIPE_AVAILABLE:
            # Initialize MediaPipe Face Detection
            self.mp_face_detection = mp.solutions.face_detection
            self.face_detection = self.mp_face_detection.FaceDetection(
                model_selection=1,  # ✅ Full-range (0-5m)
                min_detection_confidence=0.5  # Lower for better recall
            )
            self.detection_method = "MediaPipe"
        else:
            # Fallback to OpenCV Haar Cascade
            # Robust path resolution: Try local resources first, then system
            current_dir = os.path.dirname(os.path.abspath(__file__))
            resource_dir = os.path.join(current_dir, 'resources')
            
            def get_cascade_path(filename):
                # 1. Check local resource dir
                local_path = os.path.join(resource_dir, filename)
                if os.path.exists(local_path):
                    return local_path
                # 2. Check cv2 data
                if hasattr(cv2, 'data') and hasattr(cv2.data, 'haarcascades'):
                    sys_path = os.path.join(cv2.data.haarcascades, filename)
                    if os.path.exists(sys_path):
                        return sys_path
                return None

            frontal_path = get_cascade_path('haarcascade_frontalface_default.xml')
            profile_path = get_cascade_path('haarcascade_profileface.xml')
            
            if frontal_path:
                self.face_cascade = cv2.CascadeClassifier(frontal_path)
            else:
                print("[ERROR] Frontal face cascade not found!")
                # Create empty to prevent crash, but detection will fail
                self.face_cascade = cv2.CascadeClassifier()

            if profile_path:
                self.haar_profile = cv2.CascadeClassifier(profile_path)
            else:
                print("[WARN] Profile face cascade not found!")
                self.haar_profile = cv2.CascadeClassifier()
                
            self.detection_method = "OpenCV Haar"
            
    def __enter__(self):
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
    
    def detect_all_faces(self, frame: np.ndarray) -> List[Dict[str, Any]]:
        """
        Detect ALL faces in the frame.
        Use for multi-person tracking.
        """
        height, width = frame.shape[:2]
        candidates = []
        
        with self._lock:
            try:
                if MEDIAPIPE_AVAILABLE:
                    results = self.face_detection.process(frame)
                    if results.detections:
                        for detection in results.detections:
                            score = detection.score[0] if detection.score else 0.6
                            bbox = detection.location_data.relative_bounding_box
                            
                            x = int(bbox.xmin * width)
                            y = int(bbox.ymin * height)
                            w = int(bbox.width * width)
                            h = int(bbox.height * height)
                            center_x = x + w // 2
                            center_y = y + h // 2
                            
                            candidates.append({
                                'center_x': center_x,
                                'center_y': center_y,
                                'width': w,
                                'height': h,
                                'confidence': score
                            })
                else:
                    # Basic OpenCV multi-face
                    gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
                    faces = self.face_cascade.detectMultiScale(gray, 1.1, 5, minSize=(30, 30))
                    for (x, y, w, h) in faces:
                         candidates.append({
                            'center_x': x + w // 2,
                            'center_y': y + h // 2,
                            'width': w,
                            'height': h,
                            'confidence': 0.7
                        })
            except Exception as e:
                print(f"[WARN] Face detection error: {str(e)}")
                return []
                
        return candidates

    def track_faces(self, frame: np.ndarray, filter_static: bool = True) -> List[FaceTrack]:
        """
        Update tracking state with new frame detection.
        Matches new detections to existing tracks (Centroid Tracking).
        Filters out static faces (banners, posters) based on movement.
        
        Args:
            frame: Current video frame
            filter_static: If True, filter out static faces (default: True)
        
        Returns:
            List of active face tracks (excluding filtered static faces)
        """
        detections = self.detect_all_faces(frame)
        
        # Clean up old tracks (> 0.5s invisible)
        current_time = time.time()
        self.tracks = [t for t in self.tracks if (current_time - t.last_seen) < 0.5]
        
        # FILTER OUT STATIC FACES (banners, posters)
        if filter_static:
            self.tracks = [t for t in self.tracks if not t.should_be_filtered(self.config)]
        
        if not detections:
            return self.tracks
            
        used_detections = set()
        
        # 1. Update existing tracks
        for track in self.tracks:
            best_match_idx = -1
            min_dist = 1000000
            
            for idx, det in enumerate(detections):
                if idx in used_detections:
                    continue
                
                dist = np.sqrt((track.box['center_x'] - det['center_x'])**2 + 
                               (track.box['center_y'] - det['center_y'])**2)
                
                # Match threshold: move less than 200px between frames
                if dist < 200 and dist < min_dist:
                    min_dist = dist
                    best_match_idx = idx
            
            if best_match_idx != -1:
                track.update(detections[best_match_idx])
                used_detections.add(best_match_idx)
        
        # 2. Create new tracks
        for idx, det in enumerate(detections):
            if idx not in used_detections:
                new_track = FaceTrack(self.next_track_id, det)
                self.tracks.append(new_track)
                self.next_track_id += 1
        
        # 3. Final filter pass (remove newly created static tracks in probation)
        if filter_static:
            self.tracks = [t for t in self.tracks if not t.should_be_filtered(self.config)]
                
        return self.tracks

    def get_active_speaker_center(self, frame: np.ndarray) -> Optional[Tuple[int, int]]:
        """
        Smart switching logic for 2-3 people.
        Returns the center of the 'Active Speaker'.
        """
        tracks = self.track_faces(frame)
        current_time = time.time()
        height, width = frame.shape[:2]
        
        if not tracks:
            return self.get_smoothed_center(frame) # Fallback to default
            
        # 1. Scoring Logic
        candidate_scores = []
        for t in tracks:
            # A. Visual Activity (Motion) - HEAVILY WEIGHTED to prioritize moving faces
            motion_score = t.get_motion_score()
            
            # B. Size (Closer people are more likely to be main subjects)
            # Normalize size against frame
            size_score = (t.box['width'] * t.box['height']) / (width * height)
            
            # C. Centrality (Prefer people near middle)
            dist_from_center = abs(t.box['center_x'] - width/2)
            centrality_penalty = 1.0 - (dist_from_center / (width/2))
            
            # TOTAL DOMINANCE SCORE
            # Motion is now weighted MUCH more heavily (x0.15 vs x0.05) to strongly prefer moving faces
            # This ensures real people (who move) are prioritized over static banner faces
            dominance = (size_score * 1.0) + (centrality_penalty * 0.5) + (motion_score * 0.15)
            
            candidate_scores.append((t, dominance))
            
        # Find best candidate
        best_track, best_score = max(candidate_scores, key=lambda x: x[1])
        
        # 2. Switching Logic (Hysteresis)
        if self.active_track_id is None:
            # First lock
            self.active_track_id = best_track.track_id
            self.last_switch_time = current_time
        else:
            # Check if we should switch
            active_track = next((t for t in tracks if t.track_id == self.active_track_id), None)
            
            if active_track:
                # Calculate active track's current score
                # (Re-calculate mostly for comparison consistency)
                # ... reuse score from list above ...
                active_score = next((s for t, s in candidate_scores if t.track_id == self.active_track_id), 0)
                
                # Switch condition: New candidate is > 30% more dominant AND 2s passed
                if best_track.track_id != self.active_track_id:
                    if best_score > (active_score * 1.3) and (current_time - self.last_switch_time) > 2.0:
                        print(f"[SmartCrop] Switching Focus: Person {self.active_track_id} -> {best_track.track_id}")
                        self.active_track_id = best_track.track_id
                        self.last_switch_time = current_time
            else:
                # Active track lost? Switch immediately to best available
                self.active_track_id = best_track.track_id
                self.last_switch_time = current_time
                
        # 3. Use the Active Track for final smoothing
        final_track = next((t for t in tracks if t.track_id == self.active_track_id), best_track)
        
        # Feed into the EXISTING stabilization pipeline (Deadband + OneEuro)
        # We manually inject the 'Active' face into the smoothing/deadband logic
        # by calling internal logic, but we need to respect the class state.
        
        # Hack/Integration:
        # We want to use `get_smoothed_center` logic but FORCE it to use `final_track.box`
        # instead of calling `detect_face` again.
        
        # Let's call a modified internal smoothing method or temporarily override
        # Since `detect_face` wraps single detection, let's just copy the logic here or refactor.
        # Refactoring is safer.
        
        return self._process_smoothing(final_track.box, frame)

    def _process_smoothing(self, face_box: Dict[str, Any], frame: np.ndarray) -> Tuple[int, int]:
        """Internal method to apply Deadband+OneEuro to a specific face box"""
        current_time = time.time()
        current_center = (face_box['center_x'], face_box['center_y'])
        
        # Reset filters if we switched targets (large jump)
        # Using built-in 'last_face_center' check from get_smoothed_center logic effectively handles this
        
        with self._lock:
            # Check for large jumps (Scene Changes / Target Switches)
            if self.last_face_center:
                dist = np.sqrt((current_center[0] - self.last_face_center[0])**2 + 
                               (current_center[1] - self.last_face_center[1])**2)
                frame_width = frame.shape[1]
                
                # If jump > 30% of screen width, reset filters
                if dist > frame_width * 0.3:
                    self.filter_x.x_prev = None
                    self.filter_y.x_prev = None
                    self.deadband_center = None
            
            # 1. Apply One Euro Filter
            smooth_x = self.filter_x(current_center[0], current_time)
            smooth_y = self.filter_y(current_center[1], current_time)
            
            # 2. Apply DEADBAND
            if self.deadband_center is None:
                    self.deadband_center = (smooth_x, smooth_y)
            
            frame_width = frame.shape[1]
            deadband_threshold = frame_width * 0.05 
            
            dx = smooth_x - self.deadband_center[0]
            dy = smooth_y - self.deadband_center[1]
            dist_from_lock = np.sqrt(dx*dx + dy*dy)
            
            if dist_from_lock > deadband_threshold:
                if dist_from_lock > 0:
                    dir_x = dx / dist_from_lock
                    dir_y = dy / dist_from_lock
                    drag_dist = dist_from_lock - deadband_threshold
                    self.deadband_center = (
                        self.deadband_center[0] + dir_x * drag_dist,
                        self.deadband_center[1] + dir_y * drag_dist
                    )
            
            final_x = int(self.deadband_center[0])
            final_y = int(self.deadband_center[1])
            
            self.last_face_center = (final_x, final_y)
            self.last_face_box = face_box
            self.last_face_box['center_x'] = final_x
            self.last_face_box['center_y'] = final_y
            
            return self.last_face_center

    def detect_face(self, frame: np.ndarray, sticky_penalty: float = 4.5) -> Optional[Dict[str, Any]]:
        """
        Detect the most prominent face in a frame.
        Thread-safe execution.
        
        Args:
            frame: RGB numpy array of the video frame
            
        Returns:
            dict with 'center_x', 'center_y', 'width', 'height', 'confidence' or None if no face
        """
        result = None
        height, width = frame.shape[:2]
        
        with self._lock:
            try:
                if MEDIAPIPE_AVAILABLE:
                    result = self._detect_mediapipe(frame, width, height, sticky_penalty)
                else:
                    result = self._detect_opencv(frame, width, height)
            except Exception as e:
                print(f"[WARN] Face detection error: {str(e)}")
                return None
                
        return result
    
    def _detect_mediapipe(self, frame: np.ndarray, width: int, height: int, sticky_penalty: float = 4.5) -> Optional[Dict[str, Any]]:
        """Detect face using MediaPipe with sticky tracking"""
        # MediaPipe expects RGB
        results = self.face_detection.process(frame)
        
        if results.detections:
            candidates = []
            
            for detection in results.detections:
                score = detection.score[0] if detection.score else 0.6
                bbox = detection.location_data.relative_bounding_box
                
                # Convert relative to absolute coordinates
                x = int(bbox.xmin * width)
                y = int(bbox.ymin * height)
                w = int(bbox.width * width)
                h = int(bbox.height * height)
                center_x = x + w // 2
                center_y = y + h // 2
                
                candidates.append({
                    'center_x': center_x,
                    'center_y': center_y,
                    'width': w,
                    'height': h,
                    'confidence': score,
                    'detection_proto': detection
                })
            
            if not candidates:
                return None
            
            # STICKY TRACKING LOGIC
            # If we have a previous face, prefer faces close to it.
            # Score = Confidence - (Distance / ScreenWidth) * Weight
            
            if self.last_face_center:
                last_x, last_y = self.last_face_center
                
                def calculate_weighted_score(c):
                    dist = np.sqrt((c['center_x'] - last_x)**2 + (c['center_y'] - last_y)**2)
                    norm_dist = dist / width
                    # Penalty weight: 2.0 means a face 50% screen away needs >1.0 more confidence (impossible)
                    # A face 10% away needs 0.2 more confidence to steal focus.
                    penalty = norm_dist * sticky_penalty 
                    return c['confidence'] - penalty
                
                best_candidate = max(candidates, key=calculate_weighted_score)
            else:
                # No history, pick most confident
                best_candidate = max(candidates, key=lambda c: c['confidence'])
            
            return {
                'center_x': best_candidate['center_x'],
                'center_y': best_candidate['center_y'],
                'width': best_candidate['width'],
                'height': best_candidate['height'],
                'confidence': best_candidate['confidence']
            }
        
        return None
    
    def _detect_opencv(self, frame: np.ndarray, width: int, height: int) -> Optional[Dict[str, Any]]:
        """Enhanced: Detect face using OpenCV Haar Cascade (frontal + profile)"""
        gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
        
        # Try frontal first
        faces = self.face_cascade.detectMultiScale(
            gray, 
            scaleFactor=1.1,  # Keep this for quality
            minNeighbors=5,
            minSize=(30, 30)
        )
        
        if len(faces) > 0:
            x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
            return {
                'center_x': x + w // 2,
                'center_y': y + h // 2,
                'width': w,
                'height': h,
                'confidence': 0.7
            }
        
        # NEW: Try profile if frontal failed
        profiles = self.haar_profile.detectMultiScale(
            gray,
            scaleFactor=1.1,
            minNeighbors=5,
            minSize=(30, 30)
        )
        
        if len(profiles) > 0:
            x, y, w, h = max(profiles, key=lambda f: f[2] * f[3])
            return {
                'center_x': x + w // 2,
                'center_y': y + h // 2,
                'width': w,
                'height': h,
                'confidence': 0.6,
                'is_profile': True  # Flag for crop adjustment
            }
        
        # NEW: Try flipped for right profile
        gray_flipped = cv2.flip(gray, 1)
        profiles_flip = self.haar_profile.detectMultiScale(
            gray_flipped,
            scaleFactor=1.1,
            minNeighbors=5,
            minSize=(30, 30)
        )
        
        if len(profiles_flip) > 0:
            x, y, w, h = max(profiles_flip, key=lambda f: f[2] * f[3])
            # Unflip coordinates
            x = width - x - w
            return {
                'center_x': x + w // 2,
                'center_y': y + h // 2,
                'width': w,
                'height': h,
                'confidence': 0.6,
                'is_profile': True
            }
        
        return None
    
    def get_smoothed_center(self, frame: np.ndarray) -> Optional[Tuple[int, int]]:
        """
        Get smoothed face center position for stable cropping.
        Uses OneEuroFilter + DEADBAND for rock-solid stability.
        
        Args:
            frame: RGB numpy array
            
        Returns:
            tuple (center_x, center_y) or None if no face ever detected
        """
        # Lock is handled in detect_face, but we need to protect state updates
        face = self.detect_face(frame)
        current_time = time.time()
        
        with self._lock:
            if face:
                current_center = (face['center_x'], face['center_y'])
                
                # Check for large jumps (Scene Changes)
                if self.last_face_center:
                    dist = np.sqrt((current_center[0] - self.last_face_center[0])**2 + 
                                   (current_center[1] - self.last_face_center[1])**2)
                    frame_width = frame.shape[1]
                    
                    # If jump > 30% of screen width, assume scene change or new subject
                    if dist > frame_width * 0.3:
                        # Reset filters to snap immediately
                        self.filter_x.x_prev = None
                        self.filter_y.x_prev = None
                        self.deadband_center = None # Reset deadband too
                
                # 1. Apply One Euro Filter (Time Smoothing)
                smooth_x = self.filter_x(current_center[0], current_time)
                smooth_y = self.filter_y(current_center[1], current_time)
                
                # 2. Apply DEADBAND (Spatial Locking)
                if self.deadband_center is None:
                     self.deadband_center = (smooth_x, smooth_y)
                
                frame_width = frame.shape[1]
                deadband_threshold = frame_width * 0.05 # 5% of screen width allowed variance
                
                # Distance from locked center to new smoothed position
                dx = smooth_x - self.deadband_center[0]
                dy = smooth_y - self.deadband_center[1]
                dist_from_lock = np.sqrt(dx*dx + dy*dy)
                
                if dist_from_lock > deadband_threshold:
                    # Face pushed outside the deadband.
                    # Drag the deadband center towards the face
                    # The deadband center trails the face at exactly `deadband_threshold` distance
                    
                    # Normalized direction vector
                    if dist_from_lock > 0:
                        dir_x = dx / dist_from_lock
                        dir_y = dy / dist_from_lock
                        
                        # Move deadband center so that dist_from_lock == deadband_threshold
                        # New Pos = SmoothedPos - (Dir * Threshold)
                        drag_dist = dist_from_lock - deadband_threshold
                        
                        self.deadband_center = (
                            self.deadband_center[0] + dir_x * drag_dist,
                            self.deadband_center[1] + dir_y * drag_dist
                        )
                
                # The output is always the DEADBAND center
                final_x = int(self.deadband_center[0])
                final_y = int(self.deadband_center[1])
                
                self.last_face_center = (final_x, final_y)
                self.last_face_box = face
                
                # Update the face box center with locked values for consumers
                self.last_face_box['center_x'] = final_x
                self.last_face_box['center_y'] = final_y
                
                return self.last_face_center
            
            # Predict next position? No, just hold last known if missing
            return self.last_face_center
    
    def close(self):
        """Clean up resources"""
        with self._lock:
            if MEDIAPIPE_AVAILABLE and hasattr(self, 'face_detection'):
                self.face_detection.close()


try:
    from tqdm import tqdm
except ImportError:
    tqdm = lambda x, **kwargs: x

@dataclass
class KeyframePosition:
    time: float
    center_x: int
    confidence: float
    is_scene_change: bool

def generate_tracking_path(clip, config: Optional[TrackingSmoothingConfig] = None, check_cancelled=None) -> List[KeyframePosition]:
    """
    Generate a path of face positions for dynamic tracking.
    
    Args:
        clip: MoviePy VideoClip
        config: Tracking smoothing configuration
        check_cancelled: Optional function returning bool to abort processing
        
    Returns:
        List of KeyframePosition objects
    """
    if config is None:
        config = TrackingSmoothingConfig()
    
    duration = clip.duration
    width = clip.size[0]
    
    # SAFETY CHECK for long videos to prevent memory crash
    MAX_TRACKING_DURATION = 300 # 5 minutes
    if duration > MAX_TRACKING_DURATION:
        print(f"  [WARN] Video too long for full tracking ({duration:.0f}s > {MAX_TRACKING_DURATION}s). Disabling tracking to prevent memory crash.")
        return [] # Return empty to signal fallback to static analysis
    
    # Use configured sample interval (default: 0.2s for professional smoothness)
    times = np.arange(0, duration, config.sample_interval)
    
    keyframes: List[KeyframePosition] = []
    
    print(f"  [INFO] Generating tracking path ({len(times)} keyframes, {config.sample_interval}s interval)...")
    
    # Previous Frame Histogram for Scene Change Detection
    last_hist = None
    
    with FaceTracker(smoothing_factor=0.3) as tracker: # Smoothing is less relevant here if we interpolate, but good for detection stability
        
        iterator = tqdm(times, desc="Tracking Face", leave=False) if tqdm else times
        
        for t in iterator:
            # Check cancellation inside the loop (granular check)
            if check_cancelled and check_cancelled():
                print(f"  [INFO] Tracking cancelled by user.")
                return [] 

            try:
                frame = clip.get_frame(t)
                h, w = frame.shape[:2]
                
                # 1. Scene Change Detection using Histogram Check
                is_scene_change = False
                # Convert to HSV for better color matching unaffected by brightness slightly? Or simple RGB.
                # Simple RGB Histogram
                curr_hist = cv2.calcHist([frame], [0, 1, 2], None, [8, 8, 8], [0, 256, 0, 256, 0, 256])
                curr_hist = cv2.normalize(curr_hist, curr_hist).flatten()
                
                if last_hist is not None:
                    # Compare histograms (Correlation)
                    similarity = cv2.compareHist(last_hist, curr_hist, cv2.HISTCMP_CORREL)
                    # Heuristic: < 0.5 usually means significant change
                    if similarity < 0.6: 
                        is_scene_change = True
                        # print(f"    [SCENE DETECTED] at {t:.2f}s (Sim: {similarity:.2f})")
                
                last_hist = curr_hist
                
                # 2. Face Detection
                # Optimization: Resize for detection if 4K
                scale = 1.0
                detect_frame = frame
                if w > 640:
                    scale = 640 / w
                    new_h = int(h * scale)
                    detect_frame = cv2.resize(frame, (640, new_h))
                
                face = tracker.detect_face(detect_frame, sticky_penalty=config.sticky_tracking_penalty)
                
                center_x = int(w * 0.5) # Default to center
                confidence = 0.0
                
                if face:
                    # Scale back
                    raw_center = face['center_x'] / scale
                    raw_y = face['center_y'] / scale # Need Y for sticky tracking update
                    confidence = face['confidence']
                    center_x = int(raw_center)
                    center_y_scaled = int(raw_y)
                    
                    # CRITICAL: Update tracker state for "Sticky Tracking"
                    # The detector needs to know where the face was to prioritizing it next frame
                    tracker.last_face_center = (center_x, center_y_scaled)
                else:
                    # If no face, use center (or keep last known? Using center for safety)
                    # Better: Use last known if recent?
                    # For now, simplistic fallback to center. The smoother will handle it.
                    if keyframes:
                        center_x = keyframes[-1].center_x
                        confidence = 0.0 # Low confidence, signal to maybe stay static
                    else:
                        center_x = int(w * 0.5)
                
                keyframes.append(KeyframePosition(
                    time=t,
                    center_x=center_x,
                    confidence=confidence,
                    is_scene_change=is_scene_change
                ))
                
            except Exception as e:
                print(f"  [WARN] Tracking error at {t:.2f}s: {e}")
                
    return keyframes

def get_tracking_interpolator(keyframes: List[KeyframePosition], clip_width: int,
                               config: Optional[TrackingSmoothingConfig] = None):
    """
    Returns a function x_center(t) that smoothly interpolates between keyframes,
    respecting scene changes (cuts).
    
    Uses professional-grade smoothing for cinema-quality camera movement.
    """
    if not keyframes:
        return lambda t: clip_width / 2
    
    if config is None:
        config = TrackingSmoothingConfig()
        
    times = np.array([k.time for k in keyframes])
    centers = np.array([k.center_x for k in keyframes], dtype=float)
    
    # Identify scene changes (cuts) where we should NOT interpolate
    cut_indices = [i for i, k in enumerate(keyframes) if k.is_scene_change]
    
    # Process segments between scene changes separately
    segments = []
    segment_start = 0
    
    for cut_idx in cut_indices + [len(keyframes)]:
        if cut_idx > segment_start:
            segments.append((segment_start, cut_idx))
        segment_start = cut_idx
    
    # If no segments, treat entire sequence as one segment
    if not segments:
        segments = [(0, len(keyframes))]
    
    # Process each segment independently
    smoothed_centers = np.copy(centers)
    
    for seg_start, seg_end in segments:
        if seg_end - seg_start < 2:
            continue
        
        segment_times = times[seg_start:seg_end]
        segment_centers = centers[seg_start:seg_end]
        
        # Step 1: Apply refined deadband logic with HOLD TIME and PROGRESSIVE TRANSITION
        threshold = clip_width * config.deadband_threshold_pct
        ramp_zone = clip_width * config.deadband_ramp
        
        # Logic state variables
        current_pos = segment_centers[0]
        hold_start_time = None
        
        deadband_filtered = np.copy(segment_centers)
        deadband_filtered[0] = current_pos
        
        for i in range(1, len(segment_centers)):
            target = segment_centers[i]
            t = segment_times[i]
            diff = abs(target - current_pos)
            
            if diff < threshold:
                # Within deadband - stay still
                deadband_filtered[i] = current_pos
                hold_start_time = None # Reset hold
            else:
                # Movement detected
                
                # Check hold timer
                if hold_start_time is None:
                    hold_start_time = t
                
                elapsed_hold = t - hold_start_time
                
                # Determine required hold time
                # If jump is large (Focus Switch), use short micro-delay
                # If jump is small (drift), use standard hold time
                is_large_jump = diff > (clip_width * 0.2) # 20% screen width
                
                required_hold = config.focus_switch_delay_sec if is_large_jump else config.hold_time_sec
                
                if elapsed_hold < required_hold:
                    # Holding... yield to stable position
                    deadband_filtered[i] = current_pos
                else:
                    # Hold expired - Move!
                    
                    # Apply ramp logic for smooth start if it's not a large jump
                    if not is_large_jump and diff < threshold + ramp_zone:
                         ramp_factor = (diff - threshold) / ramp_zone
                         delta = target - current_pos
                         new_pos = current_pos + delta * ramp_factor * 0.5
                         deadband_filtered[i] = new_pos
                         current_pos = new_pos
                    else:
                        # Full movement or large jump
                        # If progressive transition enabled, nudge towards target instead of snap
                        if config.progressive_transition:
                            # Move 20% towards target per frame? 
                            # Or just accept target and let Gaussian smooth it?
                            # Gaussian is best. Snapping here creates a step that Gaussian makes sigmoid.
                            deadband_filtered[i] = target
                            current_pos = target
                        else:
                            deadband_filtered[i] = target
                            current_pos = target

        # Step 2: Apply Gaussian smoothing (multi-pass)
        gaussian_smoothed = apply_gaussian_smoothing(
            deadband_filtered,
            sigma=config.gaussian_sigma,
            passes=config.gaussian_passes
        )
        
        # Step 3: Apply Savitzky-Golay filter (polynomial smoothing)
        if config.use_savitzky_golay and len(gaussian_smoothed) >= 5:
            poly_smoothed = apply_savitzky_golay_filter(
                gaussian_smoothed,
                window_length=min(7, len(gaussian_smoothed) if len(gaussian_smoothed) % 2 == 1 else len(gaussian_smoothed) - 1),
                polyorder=3
            )
        else:
            poly_smoothed = gaussian_smoothed
        
        # Step 4: Apply velocity limiting
        velocity_limited = limit_velocity(
            poly_smoothed,
            segment_times,
            max_speed_pct=config.max_pan_speed_pct,
            frame_width=clip_width
        )
        
        # Step 5: One Euro Filter for final polish
        if config.use_one_euro and len(velocity_limited) > 2:
            one_euro = OneEuroFilter(min_cutoff=config.one_euro_min_cutoff, beta=config.one_euro_beta)
            euro_smoothed = np.zeros_like(velocity_limited)
            
            for i, (t, pos) in enumerate(zip(segment_times, velocity_limited)):
                euro_smoothed[i] = one_euro(pos, t)
            
            smoothed_centers[seg_start:seg_end] = euro_smoothed
        else:
            smoothed_centers[seg_start:seg_end] = velocity_limited
    
    # Create interpolator using the smoothed keyframes
    # Use cubic spline for smooth acceleration/deceleration
    if SCIPY_AVAILABLE and len(keyframes) >= 3:
        try:
            # Build piecewise spline that respects scene changes
            # by creating separate splines for each segment
            def get_pos(t):
                if t <= times[0]:
                    return smoothed_centers[0]
                if t >= times[-1]:
                    return smoothed_centers[-1]
                
                # Find which segment this time belongs to
                for seg_start, seg_end in segments:
                    if times[seg_start] <= t <= times[seg_end - 1]:
                        seg_times = times[seg_start:seg_end]
                        seg_centers = smoothed_centers[seg_start:seg_end]
                        
                        if len(seg_times) >= 3:
                            # Use cubic spline for this segment
                            spline = CubicSpline(seg_times, seg_centers, bc_type='natural')
                            return float(spline(t))
                        else:
                            # Linear interpolation for short segments
                            return float(np.interp(t, seg_times, seg_centers))
                
                # Fallback
                return float(np.interp(t, times, smoothed_centers))
            
            return get_pos
            
        except Exception as e:
            print(f"  [WARN] Cubic spline failed: {e}, falling back to linear")
            # Fallback to linear interpolation
            return lambda t: float(np.interp(t, times, smoothed_centers))
    else:
        # Fallback: linear interpolation with smoothed values
        return lambda t: float(np.interp(t, times, smoothed_centers))


def analyze_face_positions(clip, num_samples: int = 10, 
                         max_resolution: Tuple[int, int] = (640, 480),
                         enable_tracking: bool = False,
                         smoothing_config: Optional[TrackingSmoothingConfig] = None,
                         check_cancelled=None) -> Dict[str, Any]:
    """
    Analyze a video clip.
    If enable_tracking=True, generates a tracking path (Pan & Scan).
    If False, calculates static average center (Crop).
    
    Args:
        smoothing_config: Configuration for professional tracking smoothness
        check_cancelled: Optional function returning bool to abort processing
    """
    
    if smoothing_config is None:
        smoothing_config = TrackingSmoothingConfig()
    
    if enable_tracking:
        print(f"  [INFO] Starting Dynamic Face Tracking (Pro Mode)...")
        # Use high-freq sampling for tracking
        keyframes = generate_tracking_path(clip, config=smoothing_config, check_cancelled=check_cancelled)
        
        # Check if empty due to cancellation
        if not keyframes and check_cancelled and check_cancelled():
            return None

        # Detect if we actually found faces
        # If confidence sum is very low, maybe fallback?
        valid_frames = sum(1 for k in keyframes if k.confidence > 0.4)
        detection_rate = valid_frames / len(keyframes) if keyframes else 0
        
        width = clip.size[0]
        
        result = {
            'detected': (detection_rate > 0.2), # Threshold active
            'detection_rate': detection_rate,
            'mode': 'tracking',
            'keyframes': keyframes, # Pass raw keyframes
            'interpolator': get_tracking_interpolator(keyframes, width, config=smoothing_config), # Pass ready-to-use function with config
            # Maintain backward compat fields
            'positions': [k.center_x for k in keyframes],
            'avg_center_x': int(np.mean([k.center_x for k in keyframes])) if keyframes else width//2,
            'metrics': None
        }
        return result

    # --- Original Static Logic ---
    # Adaptive sampling
    duration = clip.duration
    # Min 10, Max 30, roughly 2 samples per second if short, or spread out
    adaptive_samples = min(30, max(10, int(duration * 2)))
    
    print(f"  [INFO] Analyzing {adaptive_samples} frames (adaptive) for static crop...")
    
    metrics = DetectionMetrics(
        total_frames=adaptive_samples,
        detected_frames=0,
        avg_confidence=0.0,
        processing_time_ms=0.0
    )
    
    start_time_all = time.perf_counter()
    positions = []
    
    width = clip.size[0]
    confidences = []
    
    with FaceTracker(smoothing_factor=0.5) as tracker:
        print(f"  [INFO]  Using detector: {tracker.detection_method}")
        
        # Sample frames evenly across the clip
        sample_times = np.linspace(0, max(0, duration - 0.1), adaptive_samples)
        
        # Step 5: Progress Feedback
        iterator = tqdm(sample_times, desc="Analyzing Face Positions", leave=False) if tqdm else sample_times
        
        for t in iterator:
            # Check cancellation
            if check_cancelled and check_cancelled():
                return None
            
            try:
                frame_start = time.perf_counter()
                
                # Get frame
                original_frame = clip.get_frame(t)
                
                # Resize for performance if needed
                h, w = original_frame.shape[:2]
                scale = 1.0
                
                detection_frame = original_frame
                if w > max_resolution[0] or h > max_resolution[1]:
                    # Calculate scale to fit within max_resolution while preserving aspect ratio
                    scale = min(max_resolution[0] / w, max_resolution[1] / h)
                    new_w = int(w * scale)
                    new_h = int(h * scale)
                    detection_frame = cv2.resize(original_frame, (new_w, new_h))
                
                # Detect
                face = tracker.detect_face(detection_frame)
                
                frame_end = time.perf_counter()
                metrics.processing_time_ms += (frame_end - frame_start) * 1000
                
                if face:
                    # Scale back coordinates to original size
                    if scale != 1.0:
                        center_x = int(face['center_x'] / scale)
                    else:
                        center_x = face['center_x']
                        
                    positions.append(center_x)
                    confidences.append(face['confidence'])
                    metrics.detected_frames += 1
                    
            except Exception as e:
                print(f"  [WARN] Frame analysis failed at {t:.2f}s: {str(e)}")
                continue
    
    total_time = time.perf_counter() - start_time_all
    metric_denom = adaptive_samples if adaptive_samples > 0 else 1
    metrics.processing_time_ms /= metric_denom  # Average per frame
    
    if confidences:
        metrics.avg_confidence = sum(confidences) / len(confidences)
    
    detection_rate = len(positions) / adaptive_samples
    
    result = {
        'positions': positions,
        'detection_rate': detection_rate,
        'detected': False,
        'metrics': metrics,
        'mode': 'static'
    }
    
    if positions:
        avg_center_x = int(np.mean(positions))
        print(f"  [SUCCESS] Face detected in {len(positions)}/{adaptive_samples} frames")
        print(f"  [INFO] Average face position: {avg_center_x}px (frame width: {width}px)")
        result['avg_center_x'] = avg_center_x
        result['detected'] = True
    else:
        # Step 3: Fix Fallback Center Crop
        print(f"  ⚠️ No face detected, using intelligent fallback")
        # Rule of thirds default (slightly left of center)
        result['avg_center_x'] = int(width * 0.45)  # ✅ Compositionally better
        
    return result


# Test function
if __name__ == "__main__":
    print(f"Face Detection Module Test")
    print(f"MediaPipe available: {MEDIAPIPE_AVAILABLE}")
    
    with FaceTracker() as tracker:
        print(f"Using: {tracker.detection_method}")
        # Create a dummy image
        dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        # Draw a face-like circle
        cv2.circle(dummy_frame, (320, 240), 50, (255, 200, 200), -1)
        
        res = tracker.detect_face(dummy_frame)
        print(f"Dummy detection result: {res}")
