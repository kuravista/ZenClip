import cv2
import numpy as np

def measure_real_height(text_clip, buffer=10):
    """
    Measure actual text height using OpenCV to prevent truncation
    """
    try:
        # Check for mask (Alpha channel) first - typically present in MoviePy TextClip/ImageClip
        if hasattr(text_clip, 'mask') and text_clip.mask is not None:
            # Mask is usually a Float array 0-1
            mask_frame = text_clip.mask.get_frame(0)
            # Convert to uint8 for OpenCV
            mask_uint8 = (mask_frame * 255).astype("uint8")
            # Use mask to find content
            coords = cv2.findNonZero(mask_uint8)
        else:
            # Fallback to RGB frame analysis (less accurate for black text/stroke on black bg)
            frame = text_clip.get_frame(0)
            # Ensure frame is uint8 for cvtColor if it's float
            if frame.dtype != np.uint8:
                frame_uint8 = (frame * 255).astype("uint8")
            else:
                frame_uint8 = frame
            
            h, w, _ = frame_uint8.shape
            gray = cv2.cvtColor(frame_uint8, cv2.COLOR_BGR2GRAY)
            _, thresh = cv2.threshold(gray, 5, 255, cv2.THRESH_BINARY)
            coords = cv2.findNonZero(thresh)

        if coords is None:
            return text_clip.h

        _, y, _, h_crop = cv2.boundingRect(coords)
        # Measure from top (0) to bottom of text (y + h_crop) plus generous buffer for strokes/shadows
        return y + h_crop + buffer + 5 # Extra 5px safety

    except Exception as e:
        # print(f"measure_height error: {e}")
        return text_clip.h

def split_text_to_max_lines(text, max_lines=2, max_chars_per_line=30):
    """
    Split text intelligently to ensure it doesn't exceed max_lines.
    Tries to split at natural word boundaries.
    
    Args:
        text: Input text
        max_lines: Maximum number of lines (default 2)
        max_chars_per_line: Approximate max characters per line
        
    Returns:
        Text split with newlines, guaranteed to be max_lines or fewer
    """
    words = text.strip().split()
    
    if not words:
        return text
    
    # If text is short enough for one line, return as-is
    if len(text) <= max_chars_per_line:
        return text
    
    # Build lines, trying to balance them
    lines = []
    current_line = []
    current_length = 0
    
    for word in words:
        # Check if adding this word would exceed line length
        word_length = len(word) + (1 if current_line else 0)  # +1 for space
        
        if current_length + word_length > max_chars_per_line and current_line:
            # Start new line if we haven't reached max_lines
            if len(lines) < max_lines:
                lines.append(' '.join(current_line))
                current_line = [word]
                current_length = len(word)
            else:
                # Already at max lines, add ellipsis and stop
                current_line.append('...')
                break
        else:
            current_line.append(word)
            current_length += word_length
    
    # Add final line if exists
    if current_line:
        lines.append(' '.join(current_line))
    
    # Ensure we don't exceed max_lines
    result = '\n'.join(lines[:max_lines])
    
    return result
