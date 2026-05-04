"""
ffmpeg_crop.py - Converts face tracking data to FFmpeg crop coordinates.

Samples the face tracking interpolator at intervals and produces
crop rectangles for the FFmpeg pipeline.
"""
from typing import List, Optional
from dataclasses import dataclass


@dataclass
class CropRect:
    """A crop rectangle in pixel coordinates."""
    x: int
    y: int
    width: int
    height: int


@dataclass
class CropSegment:
    """A time segment with its crop rectangle (for dynamic tracking)."""
    start_time: float
    end_time: float
    crop: CropRect


def compute_static_crop(video_w, video_h, target_w, target_h,
                        center_x=None):
    """Compute a static center crop for portrait conversion.

    Args:
        video_w: Source video width
        video_h: Source video height
        target_w: Target output width (e.g., 1080)
        target_h: Target output height (e.g., 1920)
        center_x: Face center X position, or None for frame center

    Returns:
        CropRect with the crop region
    """
    target_aspect = target_w / target_h
    crop_w = min(video_w, int(video_h * target_aspect))
    crop_h = video_h

    if center_x is None:
        center_x = video_w // 2

    x1 = max(0, center_x - crop_w // 2)
    x1 = min(x1, video_w - crop_w)

    return CropRect(x=x1, y=0, width=crop_w, height=crop_h)


def should_use_dynamic_tracking(face_analysis):
    """Determine if dynamic tracking should be used.

    Returns True if face was detected and tracking interpolator exists.
    """
    if face_analysis is None:
        return False
    if not face_analysis.get('detected', False):
        return False
    return 'interpolator' in face_analysis and face_analysis['interpolator'] is not None
