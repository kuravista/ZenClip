"""
Smart cropping with composition rules
Drop-in enhancement for existing system
"""
import numpy as np

def calculate_smart_crop(face_positions, frame_width, frame_height, 
                         target_aspect=(9, 16)):
    """
    Enhanced crop calculation with composition rules
    
    Args:
        face_positions: List of detected face x-positions
        frame_width, frame_height: Original dimensions
        target_aspect: Output aspect (w, h)
    
    Returns:
        dict with crop parameters
    """
    if not face_positions:
        # Rule of thirds fallback
        avg_x = int(frame_width * 0.45)
    else:
        # Use median (robust to outliers)
        avg_x = int(np.median(face_positions))
    
    # Calculate crop dimensions
    target_w, target_h = target_aspect
    aspect_ratio = target_w / target_h
    
    crop_width = frame_width
    crop_height = int(crop_width / aspect_ratio)
    
    if crop_height > frame_height:
        crop_height = frame_height
        crop_width = int(crop_height * aspect_ratio)
    
    # Horizontal position: center on subject
    # STRICT CENTERING: No rule of thirds bias for vertical video
    crop_x = avg_x - crop_width // 2
    
    # Vertical: upper third (talking head standard)
    crop_y = int((frame_height - crop_height) * 0.35)
    
    # Constrain to bounds
    crop_x = max(0, min(crop_x, frame_width - crop_width))
    crop_y = max(0, min(crop_y, frame_height - crop_height))
    
    return {
        'x': crop_x,
        'y': crop_y,
        'width': crop_width,
        'height': crop_height
    }