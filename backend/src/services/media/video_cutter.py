from moviepy import VideoFileClip, ImageClip, TextClip, CompositeVideoClip, concatenate_videoclips, ColorClip
from moviepy.video.fx import CrossFadeIn, CrossFadeOut
from moviepy.audio.fx import AudioFadeOut
import os
import json
import uuid
import psutil
import threading
import time
import numpy as np
import traceback
from dataclasses import dataclass, field
from contextlib import contextmanager
import concurrent.futures
import multiprocessing
import queue

from PIL import Image, ImageDraw, ImageFont
from typing import Optional, List, Dict, Any, Tuple
import atexit
import signal
import sys
import shutil

from services.media.subtitle.ass_generator import generate_ass_file

from services.media.subtitle.utils.text import split_text_to_max_lines
from services.media.subtitle.utils.color import hex_to_rgb
from services.media.video_encoder import get_optimal_video_codec, get_codec_display_name
from services.media.subtitle.utils.fonts import get_font_path

# Preset 2 Hook Rendering
from services.media.subtitle.preset2_hook import _render_preset2_hook
from services.media.subtitle.preset3_hook import _render_preset3_hook
from services.media.subtitle.preset4_hook import _render_preset4_hook

# Try to import tqdm
try:
    from tqdm import tqdm
except ImportError:
    tqdm = None
    print("[WARN] tqdm not installed. Progress bars disabled.")

def add_rounded_corners(clip, radius: int = 30):
    """
    Applies rounded corners to a MoviePy clip using a mask.
    Compatible with MoviePy 2.0 (with_mask).
    """
    try:
        w, h = clip.size
        
        # Create a mask using PIL
        # 'L' mode is 8-bit pixels, black and white
        mask_img = Image.new('L', (w, h), 0)
        draw = ImageDraw.Draw(mask_img)
        
        # Draw filled rounded rectangle
        draw.rounded_rectangle((0, 0, w, h), radius=radius, fill=255)
        
        # Convert to numpy array and create ImageClip mask
        mask_np = np.array(mask_img) / 255.0 # Normalize to 0-1 float for MoviePy
        
        # In MoviePy 2.0, masks are ImageClips (or VideoClips) with is_mask=True
        # We need to make sure the mask has the same duration as the clip
        mask_clip = ImageClip(mask_np, is_mask=True).with_duration(clip.duration)
        
        # Apply mask
        return clip.with_mask(mask_clip)
        
    except Exception as e:
        print(f"⚠️ Failed to apply rounded corners: {e}")
        return clip

# --- Configuration & Dataclasses ---

@dataclass
class VideoProcessingConfig:
    """Configuration for video clip processing"""
    # Audio settings
    audio_padding_sec: float = 0.1
    audio_fadeout_sec: float = 0.15
    
    # Smart crop settings
    face_detection_samples: int = 8
    
    # Hook overlay settings
    hook_top_padding: int = 10
    hook_bottom_padding: int = 15
    hook_side_padding: int = 20
    hook_heading_offset: int = 60
    hook_subheading_offset: int = 80
    
    # Encoding settings
    video_bitrate: str = '5000k'
    audio_bitrate: str = '192k'
    encoding_threads: int = 0  # 0 = auto (use all available CPU cores)
    fps: int = 30
    # Encoding speed preset (only applies to libx264/libx265, not hardware encoders)
    # Options: 'veryslow', 'slow', 'medium', 'fast', 'veryfast', 'ultrafast'
    encoding_preset: str = 'medium'
    
    # Parallel processing
    # CRITICAL: Set to 1 for debugging reliability issues (prevent race conditions/OOM)
    max_workers: int = 1
    
    # Portrait dimensions
    target_width: int = 1080
    target_height: int = 1920

    # Watermark settings
    add_watermark: bool = False
    watermark_type: str = 'text' # 'text' or 'image'
    watermark_text: str = ""
    watermark_image_path: Optional[str] = None
    watermark_opacity: float = 0.5
    watermark_position: str = 'bottom_right'
    watermark_size: float = 0.3 # Scale relative to video width
    watermark_font: str = 'Arial-Bold'

@dataclass
class ClipQualityMetrics:
    """Quality metrics for processed clip"""
    clip_index: int
    duration_sec: float
    resolution: tuple
    file_size_mb: float
    bitrate_actual: float
    has_audio: bool
    has_subtitles: bool
    face_detected: bool
    processing_time_sec: float
    errors: list = field(default_factory=list)

@dataclass
class ClipJob:
    """Job metadata for batch processing"""
    id: str
    video_path: str
    clips_data: list
    output_folder: str
    status: str  # 'queued', 'processing', 'complete', 'failed'
    created_at: str
    output_paths: Optional[List[str]] = None
    error: Optional[str] = None
    progress: float = 0.0
    
    # Processing options
    add_subtitles: bool = False
    smart_crop: bool = True
    add_viral_hook: bool = False

# --- Classes ---
from services.media.font_manager import FontManager



class LocalProcessMonitor:
    """Monitor system resources during processing"""
    
    def __init__(self):
        self.monitoring = False
        self.metrics = {
            'cpu_percent': [],
            'memory_percent': [],
            'memory_gb': []
        }
        self.thread = None
    
    def start(self):
        """Start monitoring in background thread"""
        self.monitoring = True
        self.thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.thread.start()
    
    def stop(self):
        """Stop monitoring and return summary"""
        self.monitoring = False
        if self.thread:
            self.thread.join(timeout=1)
        
        cpu_avg = np.mean(self.metrics['cpu_percent']) if self.metrics['cpu_percent'] else 0
        mem_peak = np.max(self.metrics['memory_gb']) if self.metrics['memory_gb'] else 0
        
        return {
            'avg_cpu': cpu_avg,
            'max_cpu': np.max(self.metrics['cpu_percent']) if self.metrics['cpu_percent'] else 0,
            'avg_memory_gb': np.mean(self.metrics['memory_gb']) if self.metrics['memory_gb'] else 0,
            'peak_memory_gb': mem_peak
        }
    
    def _monitor_loop(self):
        """Monitoring loop"""
        while self.monitoring:
            try:
                cpu = psutil.cpu_percent(interval=0.5)
                mem = psutil.virtual_memory()
                
                self.metrics['cpu_percent'].append(cpu)
                self.metrics['memory_percent'].append(mem.percent)
                self.metrics['memory_gb'].append(mem.used / (1024**3))
            except:
                pass

# --- Cleanup Manager ---
class CleanupManager:
    """Robust cleanup for temporary and partial output files"""
    
    def __init__(self):
        self.temp_files = set()
        self.partial_outputs = set()
        self._lock = threading.Lock()
        
        # Only register signal handlers in main thread
        if threading.current_thread() is threading.main_thread():
            atexit.register(self.cleanup)
            signal.signal(signal.SIGINT, self._signal_handler)
            signal.signal(signal.SIGTERM, self._signal_handler)
    
    def register_temp(self, path):
        with self._lock:
            self.temp_files.add(path)
            
    def register_output(self, path):
        with self._lock:
            self.partial_outputs.add(path)
            
    def unregister_output(self, path):
        """Call this on success"""
        with self._lock:
            if path in self.partial_outputs:
                self.partial_outputs.remove(path)
    
    def _signal_handler(self, signum, frame):
        print("\n[INFO] Interrupt received. Cleaning up...")
        self.cleanup()
        sys.exit(0)
    
    def cleanup(self):
        # Flatten sets to avoid modification during iteration if any weirdness
        all_files = list(self.temp_files | self.partial_outputs)
        count = 0
        for f in all_files:
            try:
                if os.path.exists(f):
                    os.remove(f)
                    count += 1
            except Exception as e:
                print(f"[WARN] Failed to clean {f}: {e}")
                
        if count > 0:
            print(f"[INFO] Cleaned up {count} temporary/partial files.")

cleanup_manager = CleanupManager()

class JobQueue:
    """Manage batch processing queue"""
    
    def __init__(self):
        from queue import Queue
        from datetime import datetime
        
        self.queue = Queue()
        self.jobs: Dict[str, ClipJob] = {}
        self.current_job: Optional[ClipJob] = None
        self._lock = threading.Lock()
        
    def add_job(self, video_path: str, clips_data: list, output_folder: str = "clips", **options) -> str:
        """Add a new job to the queue"""
        from datetime import datetime
        
        job_id = str(uuid.uuid4())
        job = ClipJob(
            id=job_id,
            video_path=video_path,
            clips_data=clips_data,
            output_folder=output_folder,
            status='queued',
            created_at=datetime.now().isoformat(),
            add_subtitles=options.get('add_subtitles', False),
            smart_crop=options.get('smart_crop', True),
            add_viral_hook=options.get('add_viral_hook', False)
        )
        
        with self._lock:
            self.jobs[job_id] = job
            self.queue.put(job)
            
        return job_id
    
    def get_job(self, job_id: str) -> Optional[ClipJob]:
        """Get job by ID"""
        with self._lock:
            return self.jobs.get(job_id)
    
    def get_all_jobs(self) -> List[ClipJob]:
        """Get all jobs"""
        with self._lock:
            return list(self.jobs.values())
    
    def process_queue(self, callback=None):
        """Process all jobs in queue"""
        while not self.queue.empty():
            job = self.queue.get()
            
            with self._lock:
                self.current_job = job
                job.status = 'processing'
            
            try:
                # Call the main processing function
                # This is a simplified version - actual implementation would pass all required params
                result = cut_video_clips(
                    job.video_path,
                    job.clips_data,
                    output_folder=job.output_folder,
                    add_subtitles=job.add_subtitles,
                    smart_crop=job.smart_crop,
                    add_viral_hook=job.add_viral_hook
                )
                
                with self._lock:
                    job.output_paths = result
                    job.status = 'complete'
                    job.progress = 1.0
                    
            except Exception as e:
                with self._lock:
                    job.error = str(e)
                    job.status = 'failed'
                    
            if callback:
                callback(job)
                
        with self._lock:
            self.current_job = None

# Global job queue instance
job_queue = JobQueue()

# --- Helper Functions ---

def validate_disk_space(output_folder: str, estimated_mb: float):
    """Check if there is enough disk space"""
    try:
        # Check parent if output doesn't exist yet
        check_path = output_folder if os.path.exists(output_folder) else os.path.dirname(output_folder)
        usage = shutil.disk_usage(check_path)
        
        free_mb = usage.free / (1024 * 1024)
        required_mb = estimated_mb * 1.5 # 50% safety margin for temp files
        
        if free_mb < required_mb:
            print(f"[ERROR] Insufficient disk space! Free: {free_mb:.0f}MB, Required: {required_mb:.0f}MB")
            raise RuntimeError(f"Insufficient disk space. Need {required_mb:.0f}MB, have {free_mb:.0f}MB.")
    except Exception as e:
        print(f"[WARN] Disk space check failed: {e}")

@contextmanager
def video_clip_context(video_path):
    """Safe video loading with guaranteed cleanup"""
    video = None
    try:
        video = VideoFileClip(video_path)
        yield video
    finally:
        if video is not None:
            try:
                video.close()
            except Exception as e:
                print(f"[WARN] Error closing video: {e}")

def create_viral_hook_overlay(heading_text, subheading_text, duration=3.0, width=1080, style_config=None, return_png=False):
    """Build hook overlay with text and gradient backgrounds."""
    config = VideoProcessingConfig() # Use defaults
    
    try:
        # Get BACKGROUND_DIR from app
        from app import BACKGROUND_DIR
        
        # Try to load background image
        bg_path = os.path.join(BACKGROUND_DIR, "background_hook.png")
        if not os.path.exists(bg_path):
            # Fallback to static if not in BACKGROUND_DIR (dev mode compatibility)
            bg_path = os.path.join("static", "background", "background_hook.png")
        
        if os.path.exists(bg_path):
            print(f"[INFO] Using hook background from: {bg_path}")
        else:
            # Fallback: generate a dark gradient background so preset-1 still works
            print(f"[INFO] Hook background not found, generating fallback gradient")
            bg_path = None

        if bg_path:
            bg_img = ImageClip(bg_path).with_duration(duration)
        else:
            # Generate fallback dark gradient background
            from PIL import Image as PILImage
            bg_h_fallback = int(width * 16 / 9)  # Portrait aspect
            gradient = PILImage.new('RGBA', (width, bg_h_fallback), (0, 0, 0, 0))
            # Draw a subtle dark gradient
            from PIL import ImageDraw
            draw = ImageDraw.Draw(gradient)
            for y in range(bg_h_fallback):
                alpha = int(180 + (75 * y / bg_h_fallback))  # 180 -> 255
                draw.line([(0, y), (width, y)], fill=(10, 10, 10, alpha))
            import tempfile
            tmp_bg = os.path.join(tempfile.mkdtemp(prefix='hook_bg_'), 'bg.png')
            gradient.save(tmp_bg, 'PNG')
            bg_img = ImageClip(tmp_bg).with_duration(duration)
        if bg_img.w != width:
            bg_img = bg_img.resized(width=width)
        
        # Determine effective height of bg
        bg_h = bg_img.h
        y_center = bg_h / 2
        
        # Style Config
        style_config = style_config or {}
        font_name = style_config.get('font', 'Impact')
        heading_color = style_config.get('color', '#FF0000')
        position_mode = style_config.get('position', 'bottom')
        top_text_content = style_config.get('top_text', '')
        top_text_content = style_config.get('top_text', '')
        stroke_width = int(style_config.get('stroke_width', 2))
        stroke_color_hex = style_config.get('stroke_color', '#000000')
        line_spacing = int(style_config.get('line_spacing', -4))
        font_size = int(style_config.get('font_size', 80))
        top_font_size = int(style_config.get('top_font_size', 30))
        sub_font_size = int(style_config.get('sub_font_size', 28))

        # Custom Gap Settings
        top_gap = int(style_config.get('top_gap', 10))
        bottom_gap = int(style_config.get('bottom_gap', 20))

        # 1. Top Text
        top_text_clip = None
        if top_text_content:
            top_pil_font = FontManager.load_font(font_name, top_font_size) or FontManager.load_font("Arial-Bold", top_font_size)
            
            top_text_upper = top_text_content.upper()
            dummy = Image.new('RGBA', (1, 1), (0, 0, 0, 0))
            draw = ImageDraw.Draw(dummy)
            top_bbox = draw.textbbox((0, 0), top_text_upper, font=top_pil_font)
            top_w = top_bbox[2] - top_bbox[0]
            top_h = top_bbox[3] - top_bbox[1]
            
            top_canvas_w = int(top_w + config.hook_top_padding * 2)
            top_canvas_h = int(top_h + config.hook_top_padding * 2)
            
            top_canvas = Image.new('RGBA', (top_canvas_w, top_canvas_h), (0, 0, 0, 0))
            top_draw = ImageDraw.Draw(top_canvas)
            
            top_x = config.hook_top_padding - top_bbox[0]
            top_y = config.hook_top_padding - top_bbox[1]
            top_draw.text((top_x, top_y), top_text_upper, font=top_pil_font, fill=(255, 255, 255, 255))
            
            top_text_clip = ImageClip(np.array(top_canvas)).with_duration(duration)
            # Position will be set later relative to heading

        # 2. Heading
        heading_text_final = heading_text.upper()
        
        # --- Auto-Scaling & Wrapping Logic ---
        # Goal: Fit text into max 2 lines. Shrink font until it fits.
        
        current_font_size = font_size
        min_font_size = 40
        max_width = width - (config.hook_side_padding * 2) - 20 # Safety margin
        
        final_lines = [heading_text_final]
        pil_font = None
        
        def split_text_to_lines(text, font, max_w):
            """Split text into lines that fit within max_w pixels."""
            words = text.split()
            lines = []
            current_line = []
            
            dummy_draw = ImageDraw.Draw(Image.new('RGBA', (1, 1)))
            
            for word in words:
                test_line = current_line + [word]
                # Measure
                bbox = dummy_draw.textbbox((0, 0), " ".join(test_line), font=font)
                w = bbox[2] - bbox[0]
                
                if w <= max_w:
                    current_line.append(word)
                else:
                    if current_line:
                        lines.append(" ".join(current_line))
                        current_line = [word]
                    else:
                        # Single word is too long, force it (or could split char by char, but sticking to word)
                        lines.append(word)
                        current_line = []
            
            if current_line:
                lines.append(" ".join(current_line))
            
            return lines

        while current_font_size >= min_font_size:
            pil_font = FontManager.load_font(font_name, current_font_size) or FontManager.load_font("Impact", current_font_size)
            
            # Try splitting
            lines = split_text_to_lines(heading_text_final, pil_font, max_width)
            
            # Check constraints
            if len(lines) <= 2:
                # Also check if any single line exceeds max_width (the logic above ensures it tries to fit, 
                # but if a single word is massive, it might still exceed. We accept that or shrink more?)
                # The split logic ensures it fits IF possible. If single word > max_width, it returns single line that is > max_width.
                
                # Double check width of longest line
                max_line_w = 0
                dummy_draw = ImageDraw.Draw(Image.new('RGBA', (1, 1)))
                for line in lines:
                    bbox = dummy_draw.textbbox((0, 0), line, font=pil_font)
                    max_line_w = max(max_line_w, bbox[2] - bbox[0])
                
                if max_line_w <= max_width:
                    final_lines = lines
                    break # Success!
            
            # Reduce and retry
            current_font_size -= 5
            
        # -- Drawing Multi-line Heading --
        # Calculate total dimensions
        dummy = Image.new('RGBA', (1, 1), (0, 0, 0, 0))
        draw = ImageDraw.Draw(dummy)
        
        line_heights = []
        line_widths = []
        total_text_h = 0
        
        # Internal line spacing for the heading block itself (not the global line_spacing param which is for gaps)
        # Use a tight spacing usually for impact font
        heading_line_gap = int(current_font_size * 0.1) 
        
        for line in final_lines:
            bbox = draw.textbbox((0, 0), line, font=pil_font)
            w = bbox[2] - bbox[0]
            h = bbox[3] - bbox[1]
            line_widths.append(w)
            line_heights.append(h)
            total_text_h += h
            
        total_text_h += (len(final_lines) - 1) * heading_line_gap
        max_line_w = max(line_widths) if line_widths else 0
        
        # Extra padding to avoid clipping (especially for descenders like g, y, p)
        # Apply to both single and multi-line to prevent bottom text cut-off
        padding = stroke_width * 2 + 20
        bottom_extra = 40  # Increased padding for all cases
        
        canvas_w = int(max_line_w + padding * 2)
        canvas_h = int(total_text_h + padding * 2 + bottom_extra)
        
        heading_canvas = Image.new('RGBA', (canvas_w, canvas_h), (0, 0, 0, 0))
        heading_draw = ImageDraw.Draw(heading_canvas)
        
        heading_color_rgb = hex_to_rgb(heading_color) if isinstance(heading_color, str) else (255, 0, 0)
        stroke_color_rgb = hex_to_rgb(stroke_color_hex) if isinstance(stroke_color_hex, str) else (0, 0, 0)

        # Draw lines centered
        current_y = padding
        visual_text_top = None
        visual_text_bottom = None
        
        for i, line in enumerate(final_lines):
            line_w = line_widths[i]
            line_h = line_heights[i]
            
            # Recalculate bbox for this line to get exact top/bottom metrics relative to (0,0)
            # We need this to determine exact visual edges when drawn at current_y
            l_bbox = draw.textbbox((0, 0), line, font=pil_font)
            # l_bbox is (left, top, right, bottom)
            
            # Visual Top of this line = current_y + l_bbox[1] - stroke_width
            line_visual_top = current_y + l_bbox[1] - stroke_width
            # Visual Bottom of this line = current_y + l_bbox[3] + stroke_width
            line_visual_bottom = current_y + l_bbox[3] + stroke_width
            
            if visual_text_top is None:
                visual_text_top = line_visual_top
            else:
                visual_text_top = min(visual_text_top, line_visual_top)
                
            if visual_text_bottom is None:
                visual_text_bottom = line_visual_bottom
            else:
                visual_text_bottom = max(visual_text_bottom, line_visual_bottom)

            # Center X
            # canvas_w is padded max width. Center of canvas is canvas_w/2.
            # line start x = (canvas_w - line_w)/2? 
            # Wait, our canvas is exactly fitted to max width. 
            # Yes, center text in canvas.
            x = (canvas_w - line_w) // 2
            
            # Draw Stroke
            if stroke_width > 0:
                for dx in range(-stroke_width, stroke_width + 1):
                    for dy in range(-stroke_width, stroke_width + 1):
                        if dx != 0 or dy != 0:
                            heading_draw.text((x + dx, current_y + dy), line, font=pil_font, fill=(*stroke_color_rgb, 255))
            
            # Draw Text
            heading_draw.text((x, current_y), line, font=pil_font, fill=(*heading_color_rgb, 255))
            
            current_y += line_h + heading_line_gap
        
        heading = ImageClip(np.array(heading_canvas)).with_duration(duration)
        
        # Position Heading (Center Anchor)
        heading_pos_y = y_center - config.hook_heading_offset
        heading = heading.with_position(('center', heading_pos_y))
        
        # Exact Visual Edges in Global Y
        # If no text (empty), fallback to padded box
        if visual_text_top is None: visual_text_top = padding
        if visual_text_bottom is None: visual_text_bottom = padding
        
        global_visual_top = heading_pos_y + visual_text_top
        global_visual_bottom = heading_pos_y + visual_text_bottom
        
        top_text_internal_padding = config.hook_top_padding
        
        # Position Top Text relative to Heading
        if top_text_clip:
            # We want VISUAL bottom of Top Text to be at (Global Visual Top - top_gap)
            # Top Text Clip starts at 'top_pos_y'.
            # Visual top text starts at 'top_pos_y + top_text_internal_padding' (approx? let's trust padding for Top Text for now or refine)
            # Actually, let's refine Top Text too if possible, but sticking to padding logic for Top Text is safer as it's single line usually.
            # Visual bottom of Top Text = top_pos_y + top_text_clip.h - top_text_internal_padding (approx)
            
            target_bottom = global_visual_top - top_gap
            
            # top_pos_y + top_text_clip.h - top_text_internal_padding = target_bottom
            # top_pos_y = target_bottom - top_text_clip.h + top_text_internal_padding
            
            top_pos_y = target_bottom - top_text_clip.h + top_text_internal_padding
            top_text_clip = top_text_clip.with_position(('center', top_pos_y))

        # 3. Subheading
        sub_pil_font = FontManager.load_font(font_name, sub_font_size) or FontManager.load_font("Arial-Bold", sub_font_size)
        
        dummy = Image.new('RGBA', (1, 1), (0, 0, 0, 0))
        draw = ImageDraw.Draw(dummy)
        sub_bbox = draw.textbbox((0, 0), subheading_text, font=sub_pil_font)
        sub_w = sub_bbox[2] - sub_bbox[0]
        sub_h = sub_bbox[3] - sub_bbox[1]
        
        sub_canvas_w = int(sub_w + config.hook_side_padding * 2)
        # Vertical padding check:
        # sub_y = 10 - sub_bbox[1]. So top padding is ~10px.
        sub_canvas_h = int(sub_h + config.hook_bottom_padding + 10)
        
        sub_canvas = Image.new('RGBA', (sub_canvas_w, sub_canvas_h), (0, 0, 0, 0))
        sub_draw = ImageDraw.Draw(sub_canvas)
        
        sub_x = config.hook_side_padding - sub_bbox[0]
        sub_y = 10 - sub_bbox[1]
        sub_draw.text((sub_x, sub_y), subheading_text, font=sub_pil_font, fill=(255, 255, 255, 255))
        
        subheading = ImageClip(np.array(sub_canvas)).with_duration(duration)
        
        # Position Subheading relative to Heading
        # We want VISUAL top of Subheading to be at (Global Visual Bottom + bottom_gap)
        # See subheading generation: sub_y = 10 - sub_bbox[1]
        # Visual top of subheading text in clip is 10px.
        # sub_pos_y + 10 = global_visual_bottom + bottom_gap
        # sub_pos_y = global_visual_bottom + bottom_gap - 10
        
        sub_pos_y = global_visual_bottom + bottom_gap - 10
        subheading = subheading.with_position(('center', sub_pos_y))
        
        # Composite
        # Adjust required height calculation to ensure everything fits if we use bg_img as container
        # Actually we are compositing onto a canvas of size bg_img.w x required_height
        
        # Find accumulated bounding box
        min_y = heading_pos_y
        max_y = heading_pos_y + heading.h
        
        if top_text_clip:
            min_y = min(min_y, top_pos_y)
        
        max_y = max(max_y, sub_pos_y + subheading.h)
        
        # Ensure the composite is tall enough
        # We are using bg_img logic which seems to just be a background?
        # If we return a composite of size (W, H), moviepy will center it if we use with_position properly later?
        # No, 'overlay' is the return.
        
        # Let's check logic:
        # hook_layer = CompositeVideoClip(clips, size=composite_size)
        # We need composite_size to be large enough to hold the positioned clips?
        # Actually MoviePy CompositeVideoClip size= argument defines the canvas.
        # If we position elements at y=500, and canvas is 100, they are cropped.
        
        # The positioning logic above (y_center - offset) assumes coordinate system of the FINAL video?
        # OR coordinate system of this overlay?
        # The previous code used:
        # overlay = hook_layer.with_position(final_pos)
        # So hook_layer IS the overlay.
        # AND previous code positioned items using `y_center`.
        # `y_center = bg_h / 2`.
        # So the coordinate system is the `bg_img` (background_hook.png).
        
        # If the gap pushes text outside `bg_img` height, it will be cropped!
        # We should probably resize the canvas if needed, OR just trust `bg_img` is big enough (usually 1920x1080 transparent?).
        # If `bg_img` is just a small box, this will break.
        # But `bg_img` is likely full screen transparent png called "background_hook.png".
        
        # Let's stick to existing canvas logic but just update positions.
        # Recalculating required_height strictly might be safer if bg is small.
        
        clips_to_composite = [bg_img]
        if top_text_clip:
            clips_to_composite.append(top_text_clip)
        clips_to_composite.append(heading)
        clips_to_composite.append(subheading)
        
        # If text goes beyond bg_h, we might need to increase size?
        # Assuming bg_img is full screen or large enough for now as per original code.
        
        composite_size = (bg_img.w, max(bg_h, int(max_y + 50))) # Ensure enough height
        hook_layer = CompositeVideoClip(clips_to_composite, size=composite_size)

        final_pos = ('center', 'bottom')
        if position_mode == 'top':
            final_pos = ('center', 'top')
        elif position_mode == 'center':
            final_pos = ('center', 'center')

        # PNG return mode for FFmpeg pipeline
        if return_png:
            import tempfile
            from PIL import Image as PILImage
            # Render the composite to a single frame
            frame = hook_layer.get_frame(0)
            pil_img = PILImage.fromarray(frame)
            tmp_dir = tempfile.mkdtemp(prefix='zenclip_hook_')
            tmp_path = os.path.join(tmp_dir, 'hook_preset1.png')
            pil_img.save(tmp_path, 'PNG')
            # Map position to pixels
            pos_y_map = {'top': 0, 'center': int(width * 9 / 16 / 2), 'bottom': int(width * 9 / 16)}
            py = pos_y_map.get(position_mode, 0)
            return (tmp_path, ('center', py))

        overlay = hook_layer.with_position(final_pos)
        overlay = overlay.with_effects([CrossFadeIn(0.2), CrossFadeOut(0.5)])

        return overlay
        
    except Exception as e:
        print(f"Error creating hook overlay: {e}")
        return None

def create_watermark_overlay(config: VideoProcessingConfig, video_width: int, video_height: int, duration: float):
    """Creates a watermark overlay clip based on configuration."""
    print(f"  [Watermark] Checking config: enabled={config.add_watermark}, type={config.watermark_type}, text='{config.watermark_text}'")
    if not config.add_watermark:
        return None

    try:
        watermark_clip = None

        if config.watermark_type == 'image' and config.watermark_image_path:
            if not os.path.exists(config.watermark_image_path):
                print(f"  [WARN] Watermark image not found at {config.watermark_image_path}")
                return None
            watermark_clip = ImageClip(config.watermark_image_path)
        
        elif config.watermark_type == 'text' and config.watermark_text:
            # Load font
            target_font = getattr(config, 'watermark_font', 'Arial-Bold')
            
            # High-res rendering for quality scaling
            base_font_size = 200 
            # Use FontManager
            pil_font = FontManager.load_font(target_font, base_font_size) or FontManager.load_font("Arial-Bold", base_font_size)
            
            # Draw text to image
            dummy = Image.new('RGBA', (1, 1), (0, 0, 0, 0))
            draw = ImageDraw.Draw(dummy)
            bbox = draw.textbbox((0, 0), config.watermark_text.upper(), font=pil_font)
            w = bbox[2] - bbox[0]
            h = bbox[3] - bbox[1]
            
            # Add padding
            padding = 40
            canvas = Image.new('RGBA', (w + padding, h + padding), (0, 0, 0, 0))
            draw_canvas = ImageDraw.Draw(canvas)
            # Center text
            draw_canvas.text((padding//2 - bbox[0], padding//2 - bbox[1]), config.watermark_text.upper(), font=pil_font, fill=(255, 255, 255, 255))
            
            # Create high-res clip
            watermark_clip = ImageClip(np.array(canvas))

        if not watermark_clip:
            return None

        # Resize logic
        # target width relative to video width
        target_w = int(video_width * config.watermark_size)
        if target_w < 50: target_w = 50 # Minimum size
        
        watermark_clip = watermark_clip.resized(width=target_w)
        
        # Opacity
        watermark_clip = watermark_clip.with_opacity(config.watermark_opacity)
        watermark_clip = watermark_clip.with_duration(duration)

        # Positioning
        margin = int(video_width * 0.05) # 5% margin
        
        pos_map = {
            'top_left': (margin, margin),
            'top_right': (video_width - watermark_clip.w - margin, margin),
            'bottom_left': (margin, video_height - watermark_clip.h - margin),
            'bottom_right': (video_width - watermark_clip.w - margin, video_height - watermark_clip.h - margin),
            'center': ('center', 'center'),
            'top_center': ('center', margin),
            'bottom_center': ('center', video_height - watermark_clip.h - margin)
        }
        
        # Check if position is a custom dict/object (e.g. from frontend drag)
        final_pos = pos_map.get('bottom_right') # Default
        
        if isinstance(config.watermark_position, str):
             final_pos = pos_map.get(config.watermark_position, final_pos)
        elif isinstance(config.watermark_position, dict):
            # Expects {'x': float, 'y': float} (0.0 - 1.0)
            x_pct = float(config.watermark_position.get('x', 0))
            y_pct = float(config.watermark_position.get('y', 0))
            
            center_x = int(video_width * x_pct)
            center_y = int(video_height * y_pct)
            
            tl_x = center_x - (watermark_clip.w // 2)
            tl_y = center_y - (watermark_clip.h // 2)
            
            final_pos = (tl_x, tl_y)
            
        watermark_clip = watermark_clip.with_position(final_pos)
        
        return watermark_clip

    except Exception as e:
        print(f"  [ERROR] Error creating watermark: {e}")
        return None



def generate_clip_preview(video_path: str, start_time: float, end_time: float, max_size: tuple = (320, 568)) -> str:
    """
    Generate a low-res preview thumbnail for UI display.
    
    Args:
        video_path: Path to the video file
        start_time: Clip start time in seconds
        end_time: Clip end time in seconds
        max_size: Maximum size (width, height) for the preview
        
    Returns:
        Base64-encoded JPEG string for UI embedding
    """
    try:
        import base64
        import io
        
        with video_clip_context(video_path) as video:
            if video is None:
                return ""
            
            # Extract frame from midpoint
            mid_time = (start_time + end_time) / 2
            mid_time = min(max(mid_time, 0), video.duration)
            
            frame = video.get_frame(mid_time)
            
            # Convert to PIL Image
            from PIL import Image
            img = Image.fromarray(frame)
            
            # Resize to thumbnail
            img.thumbnail(max_size, Image.Resampling.LANCZOS)
            
            # Encode as JPEG to base64
            buffer = io.BytesIO()
            img.save(buffer, format='JPEG', quality=85)
            b64_data = base64.b64encode(buffer.getvalue()).decode('utf-8')
            
            return f"data:image/jpeg;base64,{b64_data}"
            
    except Exception as e:
        print(f"[ERROR] Preview generation failed: {e}")
        return ""

def process_single_clip(args, progress_callback=None):
    """
    Worker function executed in separate Process for full isolation.
    
    Args:
        args: Tuple of processing arguments
        progress_callback: Optional function(dict) for progress updates
    """
    (i, clip_info, total_clips, video_path, output_folder, add_subtitles, phrase_timings, subtitle_config, min_duration, smart_crop, use_original_resolution, randomize_metadata, custom_metadata, add_viral_hook, hook_styles, target_resolution, canvas_resolution, cancel_event) = args
    
    # Create a local check function for the worker
    def check_cancelled():
        if cancel_event and cancel_event.is_set():
            return True
        return False
        
    if check_cancelled():
        print(f"[INFO] Clip {i} aborted before start.")
        return None
    
    config = VideoProcessingConfig()
    config.add_watermark = clip_info.get('add_watermark', False)
    if config.add_watermark:
        watermark_config = clip_info.get('watermark_config', {})
        config.watermark_type = watermark_config.get('watermark_type', 'text')
        config.watermark_text = watermark_config.get('watermark_text', '')
        config.watermark_image_path = watermark_config.get('watermark_image_path')
        config.watermark_opacity = float(watermark_config.get('watermark_opacity', 0.5))
        
        raw_pos = watermark_config.get('watermark_position', 'bottom_right')
        if isinstance(raw_pos, str) and raw_pos.strip().startswith('{'):
            try:
                import json
                config.watermark_position = json.loads(raw_pos)
            except Exception as e:
                print(f"[WARN] Failed to parse watermark position JSON: {e}")
                config.watermark_position = raw_pos
        else:
            config.watermark_position = raw_pos
        config.watermark_size = watermark_config.get('watermark_size', 0.3)
        config.watermark_font = watermark_config.get('watermark_font', 'Arial-Bold')

        print(f"[DEBUG] Watermark Configured: Type={config.watermark_type}, Text='{config.watermark_text}', Font={config.watermark_font}, Pos={config.watermark_position}")
    else:
        print(f"[DEBUG] No watermark requested for clip {i}")

    output_path = None
    
    # Unique temp file to avoid collisions
    import tempfile
    temp_dir = tempfile.gettempdir()
    temp_audio_file = os.path.join(
        temp_dir, 
        f'temp-audio-{uuid.uuid4().hex[:8]}-{i}.m4a'
    )
    cleanup_manager.register_temp(temp_audio_file) # Register temp audio
    
    start_time_process = time.perf_counter()
    face_detected_flag = False
    
    def report_progress(stage, progress):
        """Helper to report progress"""
        if progress_callback:
            progress_callback({
                'stage': stage,
                'progress': progress,
                'current_clip': i,
                'total_clips': total_clips
            })
    
    report_progress('initializing', 0.0)
    
    try:
        with video_clip_context(video_path) as video:
            if video is None:
                return None
            
            video_duration = video.duration
            
            start_time = clip_info['start_time']
            end_time = clip_info['end_time']
            topic = clip_info.get('topic', f'clip_{i}')
            
            # Timestamp validation
            start_time = max(0, start_time)
            end_time = min(video_duration, end_time)
            duration = end_time - start_time
            
            # Minimum duration logic
            is_auto = (min_duration == "auto")
            target_min = 30 if is_auto else int(min_duration)
            
            if duration < target_min:
                # Extend logic
                extend_need = target_min - duration
                if end_time + extend_need <= video_duration:
                    end_time += extend_need
                elif start_time - extend_need >= 0:
                    start_time -= extend_need
                duration = end_time - start_time
            
            # Record the "content" end time before adding audio padding
            original_end_time = end_time
            
            # Minimum duration validation
            # For manual mode (min_duration=0), allow very short clips
            # For auto mode, enforce reasonable minimum
            if min_duration == 0:
                # Manual mode: only prevent completely invalid clips
                if duration < 0.1:
                    print(f"  ⚠️ Clip {i} has invalid duration ({duration:.2f}s), skipping")
                    return None
            else:
                # Auto mode: enforce 1-second minimum
                if duration < 1:
                    print(f"  ⚠️ Clip {i} too short ({duration:.2f}s), skipping")
                    return None
                 
            # Safe Filename
            safe_topic = "".join(c for c in topic if c.isalnum() or c in (' ', '-', '_')).rstrip()
            safe_topic = safe_topic[:50]
            output_filename = f"clip_{i}_{safe_topic}.mp4"
            output_path = os.path.join(output_folder, output_filename)
            cleanup_manager.register_output(output_path) # Register partial output
            
            print(f"  [DEBUG] Processing Clip {i}: {start_time:.2f}s -> {end_time:.2f}s (Dur: {duration:.2f}s) | Min: {target_min}s")
            
            # --- Cutting & Processing ---
            
            # Padding for audio smoothness
            padded_end_time = min(end_time + config.audio_padding_sec, video_duration)
            clip = video.subclipped(start_time, padded_end_time)
            
            if padded_end_time > start_time:
                clip = clip.with_effects([AudioFadeOut(duration=config.audio_fadeout_sec)])
            
            # Portrait Conversion
            if use_original_resolution:
                portrait_clip = clip
            else:
                if target_resolution:
                    target_w, target_h = target_resolution
                else:
                    target_w, target_h = config.target_width, config.target_height
                
                # Resize keeping aspect ratio to fill height
                resized_clip = clip.resized(height=target_h)
                current_w = resized_clip.size[0]
                
                if current_w > target_w:
                    # Crop logic
                    detect_confidence = 0
                    x_center = current_w / 2
                    
                    if smart_crop:
                        report_progress('face_detection', 0.25)
                        try:
                            from services.media.face_detector import analyze_face_positions
                            # Enable tracking mode
                            face_analysis = analyze_face_positions(
                                resized_clip, 
                                num_samples=config.face_detection_samples,
                                enable_tracking=True,
                                check_cancelled=check_cancelled
                            )
                            
                            if face_analysis and face_analysis.get('detected'):
                                detect_confidence = face_analysis.get('detection_rate', 0)
                                if detect_confidence >= 0.3:
                                    face_detected_flag = True
                                    
                                    # CHECK FOR TRACKING INTERPOLATOR
                                    if 'interpolator' in face_analysis:
                                        print(f"  [INFO] Applying Dynamic Face Tracking...")
                                        interpolator = face_analysis['interpolator']
                                        
                                        # Use functional x_center for dynamic crop
                                        # Define generator for x1, x2 or use x_center
                                        # MoviePy crop(x_center=func, width=...)
                                        # We need to use resized_clip.crop(...). 
                                        # Note: video_cutter uses .cropped() which might be MoviePy 2 specific method?
                                        # Let's try .crop() which is standard, assuming .cropped is alias or we switch.
                                        # Actually, let's look at signature. if .cropped exists, .crop likely does too.
                                        
                                        def get_center(t):
                                            return interpolator(t)
                                            
                                        # MoviePy v2 doesn't support x_center as function in .cropped()
                                        # Use transform instead for frame-by-frame dynamic cropping
                                        def crop_with_tracking(get_frame, t):
                                            frame = get_frame(t)
                                            h, w = frame.shape[:2]
                                            x_center = int(interpolator(t))
                                            x1 = max(0, x_center - target_w // 2)
                                            x2 = min(w, x1 + target_w)
                                            if x2 - x1 < target_w:
                                                x1 = max(0, x2 - target_w)
                                            return frame[:, x1:x2]
                                        
                                        portrait_clip = resized_clip.transform(crop_with_tracking)
                                        # No need for with_size - transform already returns correct dimensions
                                        
                                        # Skip the static clamp logic below for tracking mode
                                        # (MoviePy handles clamping usually, or we ensure interpolator is safe)
                                        # We should clamp the interpolator result in get_tracking_interpolator really, 
                                        # but MoviePy crop usually clamps or errors? 
                                        # Let's ensure logic is robust.
                                        # We'll use this portrait_clip and skip the static assignment.
                                        
                                    else:
                                        # Fallback to static
                                        x_center = face_analysis['avg_center_x']
                                        x1 = int(x_center - target_w / 2)
                                        x2 = int(x_center + target_w / 2)
                                        # Clamp
                                        if x1 < 0: x1, x2 = 0, target_w
                                        if x2 > current_w: x2, x1 = current_w, current_w - target_w
                                        portrait_clip = resized_clip.cropped(x1=x1, x2=x2)
                                else:
                                    # Low confidence fallback
                                    x1 = int(x_center - target_w / 2)
                                    x2 = int(x_center + target_w / 2)
                                    if x1 < 0: x1, x2 = 0, target_w
                                    if x2 > current_w: x2, x1 = current_w, current_w - target_w
                                    portrait_clip = resized_clip.cropped(x1=x1, x2=x2)
                            else:
                                # Not detected
                                x1 = int(x_center - target_w / 2)
                                x2 = int(x_center + target_w / 2)
                                if x1 < 0: x1, x2 = 0, target_w
                                if x2 > current_w: x2, x1 = current_w, current_w - target_w
                                portrait_clip = resized_clip.cropped(x1=x1, x2=x2)
                                
                        except Exception as e:
                            print(f"  [WARN] Smart crop/tracking warning clip {i}: {e}")
                            traceback.print_exc()
                            # Fallback
                            x1 = int(x_center - target_w / 2)
                            x2 = int(x_center + target_w / 2)
                            portrait_clip = resized_clip.cropped(x1=x1, x2=x2)
                            
                    else:
                        # No smart crop, center static
                        x1 = int(x_center - target_w / 2)
                        x2 = int(x_center + target_w / 2)
                        if x1 < 0: x1, x2 = 0, target_w
                        if x2 > current_w: x2, x1 = current_w, current_w - target_w
                        portrait_clip = resized_clip.cropped(x1=x1, x2=x2)
                    
                else:
                    # Width is too small, fit width and crop height (zoomed in) or just pad?
                    # Standard behavior: Zoom to fill width if width < target
                    # But simpler logic used previously: just resize width
                    portrait_clip = clip.resized(width=target_w)
                    if portrait_clip.h > target_h:
                        y_center = portrait_clip.h / 2
                        y1 = int(y_center - target_h / 2)
                        y2 = int(y_center + target_h / 2)
                        portrait_clip = portrait_clip.cropped(y1=y1, y2=y2)

                # --- Canvas Padding Logic (Social Media Background) ---
                if canvas_resolution:
                    canvas_width, canvas_height = canvas_resolution
                    # Check if we need padding
                    if (canvas_width != target_w) or (canvas_height != target_h):
                        print(f"  🖼️ Applying padding: {target_w}x{target_h} -> {canvas_width}x{canvas_height}")
                        
                        # Apply rounded corners to content before compositing
                        portrait_clip = add_rounded_corners(portrait_clip, radius=32)
                        
                        # Background
                        bg_clip = ColorClip(
                            size=(int(canvas_width), int(canvas_height)), 
                            color=(0, 0, 0)
                        ).with_duration(portrait_clip.duration)
                        
                        # Center the content
                        portrait_clip = CompositeVideoClip([
                            bg_clip, 
                            portrait_clip.with_position("center")
                        ])
            
            # Viral Hook - Update width reference to use actual canvas width if padded
            report_progress('adding_hooks', 0.55)
            current_video_w = portrait_clip.w # Should be canvas_width if padded
            hook_is_intro_only = False
            
            if add_viral_hook:
                final_heading = clip_info.get('hook_heading') or (hook_styles.get('headline') if hook_styles else None)
                final_subheading = clip_info.get('hook_subheading') or (hook_styles.get('subheading') if hook_styles else None)
                final_top_text = clip_info.get('hook_top_text') or (hook_styles.get('top_text') if hook_styles else '')
                
                # Check hook style
                # Check hook style
                hook_style = hook_styles.get('hook_style', 'preset-1') if hook_styles else 'preset-1'
                
                # Resolve Preset 2 content (Prioritize clip specific, then fallback to global)
                final_preset2_content = clip_info.get('preset2_content') or (hook_styles.get('preset2_content', '') if hook_styles else '')
                
                # For Preset 1: need heading and subheading
                # For Preset 2: need preset2_content
                should_render = False
                if hook_style == 'preset-2':
                    should_render = bool(final_preset2_content)
                elif hook_style == 'preset-3':
                    # Preset 3 allows partial fields (e.g. just Headline)
                    should_render = bool(final_heading or final_subheading or final_top_text)
                else:
                    # Default Preset 1 logic (usually requires both for the specific design)
                    should_render = bool(final_heading and final_subheading)

                print(f"  [DEBUG] Hook Check: Style={hook_style}, Render={should_render}")
                print(f"  [DEBUG] Data: Heading='{final_heading}', Sub='{final_subheading}', Top='{final_top_text}'")
                
                if should_render:
                    try:
                        merged_style = hook_styles.copy() if hook_styles else {}
                        merged_style['top_text'] = final_top_text
                        merged_style['preset2_content'] = final_preset2_content # Ensure renderer gets it
                        
                        if clip_info.get('hook_stroke_width'):
                            merged_style['stroke_width'] = clip_info.get('hook_stroke_width')
                        if clip_info.get('hook_stroke_color'):
                            merged_style['stroke_color'] = clip_info.get('hook_stroke_color')
                        
                        # Duration Logic
                        is_full_duration = hook_styles.get('full_duration', False)
                        
                        if is_full_duration:
                            hook_duration = clip.duration # Full clip duration
                            hook_is_intro_only = False
                        else:
                            hook_duration = 3.5 # Default intro duration (User requested to keep 3.5)
                            hook_is_intro_only = True
                        
                        # Style Routing: Check hook_style and use appropriate renderer
                        hook_style = hook_styles.get('hook_style', 'preset-1')
                        
                        if hook_style == 'preset-2':
                            # Use Preset 2 renderer (sentence-style with highlighting)
                            hook_overlay = _render_preset2_hook(
                                config=config,
                                hook_styles=merged_style,
                                video_width=portrait_clip.w,
                                video_height=portrait_clip.h,
                                duration=hook_duration
                            )
                        elif hook_style == 'preset-3':
                            # Use Preset 3 renderer (Viral Stack)
                            hook_overlay = _render_preset3_hook(
                                config=config,
                                hook_styles=merged_style,
                                video_width=portrait_clip.w,
                                video_height=portrait_clip.h,
                                duration=hook_duration
                            )
                        elif hook_style == 'preset-4':
                            # Use Preset 4 renderer (Simple Box)
                            hook_overlay = _render_preset4_hook(
                                config=config,
                                hook_styles=merged_style,
                                video_width=portrait_clip.w,
                                video_height=portrait_clip.h,
                                duration=hook_duration
                            )
                        else:
                            # Use Preset 1 renderer (default: top/heading/sub)
                            hook_overlay = create_viral_hook_overlay(
                                final_heading, 
                                final_subheading, 
                                duration=hook_duration, 
                                width=portrait_clip.w,
                                style_config=merged_style
                            )
                        
                        if hook_overlay:
                            # Validation of overlay size
                            if hook_overlay.w > portrait_clip.w:
                                scale = portrait_clip.w / hook_overlay.w
                                hook_overlay = hook_overlay.resized(scale)
                                
                            portrait_clip = CompositeVideoClip([portrait_clip, hook_overlay])
                            # Ensure duration is maintained
                            portrait_clip.duration = clip.duration
                    except Exception as e:
                        print(f"  [ERROR] Hook error clip {i}: {e}")
            
            # Subtitles
            report_progress('adding_subtitles', 0.70)
            temp_ass_file = None
            ffmpeg_vf_args = []
            
            if add_subtitles and phrase_timings:
                try:
                    # Logic: If Viral Hook is active AND is intro-only, suppress subtitles
                    final_timings = phrase_timings
                    
                    if add_viral_hook and final_heading and final_subheading and hook_is_intro_only: 
                         # Only suppress if it's an intro hook (3.5s)
                         suppress_until = start_time + 3.5 
                         
                         print(f"  [INFO] Suppressing subtitles until {suppress_until:.2f}s (Intro Hook Active)")
                         
                         filtered_timings = []
                         for p in phrase_timings:
                             # Check phrase level overlap first (optimization)
                             if p['end'] <= suppress_until:
                                 continue # Skip phrase entirely
                             
                             # Deep filter words if they exist
                             if 'words' in p:
                                 valid_words = [w for w in p['words'] if w['end'] > suppress_until]
                                 if valid_words:
                                     # Create new phrase object to not mutate original
                                     new_p = p.copy()
                                     new_p['words'] = valid_words
                                     # Adjust phrase start to first visible word if needed
                                     new_p['start'] = valid_words[0]['start']
                                     filtered_timings.append(new_p)
                             else:
                                 # Phrase style (no words)
                                 if p['start'] >= suppress_until:
                                     filtered_timings.append(p)
                                 
                         final_timings = filtered_timings
                    
                    current_config = subtitle_config.copy() if subtitle_config else {}
                    if clip_info.get('highlight_map'):
                         current_config['highlight_map'] = clip_info.get('highlight_map')
                    
                    # Get subtitle style
                    subtitle_style = current_config.get('style', 'word')
                    
                    # ROUTING: Use custom MoviePy rendering for boxies and pod_d, ASS for others
                    # ROUTING: Use custom MoviePy rendering for boxies, pod_d, and shadow
                    if subtitle_style == 'boxies' or subtitle_style == 'pod_d' or subtitle_style == 'shadow':
                        print(f"  [INFO] Applying custom {subtitle_style} subtitles for clip {i}...")
                        
                        # Use custom MoviePy sub rendering from generator.py
                        from services.media.subtitle.generator import add_subtitles_to_video
                        
                        # Add subtitles using custom MoviePy rendering
                        portrait_clip = add_subtitles_to_video(
                            portrait_clip,
                            final_timings,
                            start_time,
                            original_end_time,
                            style_config=current_config
                        )
                        
                    else:
                        # Use ASS subtitles for other styles (rapid, mozi, elegant, rapid_pro, etc.)
                        print(f"  [INFO] Generating ASS subtitles for clip {i}...")
                        
                        # Generate ASS File
                        temp_ass_file = os.path.join(
                            os.path.dirname(temp_audio_file),
                            f"subs_{uuid.uuid4().hex[:8]}.ass"
                        )
                        
                        # Determine clip dimensions
                        # portrait_clip is the final video to be written
                        video_w, video_h = portrait_clip.size
                        
                        success = generate_ass_file(
                            temp_ass_file,
                            final_timings,
                            start_time,
                            original_end_time,
                            (video_w, video_h),
                            style_config=current_config
                        )
                        
                        if success:
                            print(f"  [SUCCESS] ASS file generated: {temp_ass_file}")
                            # Add to ffmpeg params
                            # SMART FONT DIR RESOLUTION
                            # We need to point fontsdir to where the selected font actually lives
                            # (e.g. static/fonts for Poppins, or custom_fonts for uploads)
                            
                            target_font = current_config.get('font', 'Arial')
                            resolved_font_path = get_font_path(target_font)
                            
                            fonts_dir = None
                            
                            if resolved_font_path and os.path.isabs(resolved_font_path):
                                d = os.path.dirname(resolved_font_path)
                                # Avoid pointing fontsdir to system fonts (redundant and blocks access to bundled fonts)
                                is_system = "windows" in d.lower() and "fonts" in d.lower()
                                if not is_system:
                                    fonts_dir = d
                                
                            # Fallback/Default to bundled fonts if system font or resolution failed
                            if not fonts_dir or not os.path.exists(fonts_dir):
                                try:
                                    from app import STATIC_DIR
                                    fonts_dir = os.path.join(STATIC_DIR, 'fonts')
                                except ImportError:
                                    # Fallback relative to this file
                                    # src/services/media/video_cutter.py -> static/fonts
                                    current_file_dir = os.path.dirname(os.path.abspath(__file__))
                                    fonts_dir = os.path.abspath(os.path.join(current_file_dir, "..", "..", "..", "static", "fonts"))
                            
                            print(f"  [FONTS] Selected font: '{target_font}' -> Dir: '{fonts_dir}'")

                            # Ensure absolute paths
                            abs_ass_path = os.path.abspath(temp_ass_file).replace('\\', '/')
                            abs_fonts_dir = os.path.abspath(fonts_dir).replace('\\', '/')
                            
                            def escape_filter_path(path):
                                return path.replace(':', '\\:').replace("'", "\\'")

                            safe_ass = escape_filter_path(abs_ass_path)
                            safe_fonts = escape_filter_path(abs_fonts_dir)
                            
                            vf_string = f"subtitles='{safe_ass}':fontsdir='{safe_fonts}'"
                            ffmpeg_vf_args = ["-vf", vf_string]
                            
                        else:
                            print(f"  [ERROR] Failed to generate ASS file")

                except Exception as e:
                    print(f"  [ERROR] Subtitle error clip {i}: {e}")
                    traceback.print_exc()

            # Watermark Overlay (Apply before encoding, after hook/subs)
            if config.add_watermark:
                try:
                    watermark = create_watermark_overlay(config, portrait_clip.w, portrait_clip.h, portrait_clip.duration)
                    if watermark:
                        # Flatten composition if portrait_clip is already a CompositeVideoClip
                        layers = []
                        if isinstance(portrait_clip, CompositeVideoClip):
                            # Extract existing clips to flatten
                            layers.extend(portrait_clip.clips)
                        else:
                            layers.append(portrait_clip)
                            
                        layers.append(watermark)
                        
                        portrait_clip = CompositeVideoClip(layers, size=portrait_clip.size)
                        portrait_clip.duration = duration
                        print(f"  [INFO] Watermark applied ({config.watermark_type}). Total layers: {len(layers)}")
                except Exception as w_err:
                    print(f"  [ERROR] Watermark failed: {w_err}")

            # Encoding
            ffmpeg_params = ["-metadata", "comment=", "-metadata", "description="]
            
            if randomize_metadata:
                 ffmpeg_params = ["-metadata", f"comment=ID:{uuid.uuid4()}", "-metadata", f"description=AutoClip"]
            
            # Incorporate VF args
            if ffmpeg_vf_args:
                ffmpeg_params.extend(ffmpeg_vf_args)

            video_codec, codec_params = get_optimal_video_codec()
            
            encoding_params = {
                'codec': video_codec,
                'audio_codec': 'aac',
                'fps': config.fps,
                'bitrate': config.video_bitrate,
                'audio_bitrate': config.audio_bitrate,
                'threads': config.encoding_threads,  # 0 = auto (all cores)
                'write_logfile': False,
                'temp_audiofile': temp_audio_file,
                'remove_temp': True,
                'ffmpeg_params': ffmpeg_params
            }
            # Apply encoding preset: codec_params preset takes priority (hardware encoders),
            # otherwise use user-selected preset (only valid for software codecs like libx264)
            if codec_params.get('preset'):
                encoding_params['preset'] = codec_params['preset']
            elif video_codec in ('libx264', 'libx265'):
                encoding_params['preset'] = config.encoding_preset
                log.debug(f"Using encoding preset: {config.encoding_preset}", module="Encoder")
            
            # Add cancellation checking via custom logger
            # MoviePy expects a logger object with iter_bar method or a 'bar' string.
            # We'll use a custom class that wraps tqdm but adds our check.
            
            from proglog import TqdmProgressBarLogger
            
            class CancellationLogger(TqdmProgressBarLogger):
                """Logger that checks for job cancellation during encoding"""
                def __init__(self, check_cancelled_func):
                    super().__init__(print_messages=False) # Let tqdm handle printing if needed, or suppress
                    self.check_cancelled = check_cancelled_func
                    
                def callback(self, **changes):
                    # Check cancellation on every update
                    if self.check_cancelled and self.check_cancelled():
                        print(f"\n[INFO] 🛑 Encoding cancelled by user!")
                        raise KeyboardInterrupt("Job cancelled by user")
                    super().callback(**changes)

            # Use the logger if we have a check_cancelled function
            if check_cancelled:
                encoding_params['logger'] = CancellationLogger(check_cancelled)
            elif clip_info.get('job_id'):
                # Legacy fallback (though we should always have check_cancelled now)
                # But we can't easily implement file-based check inside TqdmProgressBarLogger cleanly without more code
                # Let's stick to the new reliable method.
                pass
                
            try:
                portrait_clip.write_videofile(output_path, **encoding_params)
            except Exception as e:
                print(f"  [ERROR] Encoding failed for clip {i} using codec '{encoding_params.get('codec')}': {e}")
                hardware_codecs = ['h264_nvenc', 'h264_amf', 'h264_qsv', 'h264_videotoolbox']
                success = False

                # FALLBACK 1: Try Software Encoder (CPU) if Hardware Encoder failed
                if encoding_params.get('codec') in hardware_codecs:
                    print(f"  [INFO] Retrying clip {i} with CPU Software Encoder (libx264)...")
                    try:
                        encoding_params['codec'] = 'libx264'
                        encoding_params['preset'] = config.encoding_preset  # Ensure valid software preset
                        portrait_clip.write_videofile(output_path, **encoding_params)
                        print(f"  [SUCCESS] Clip {i} saved (CPU Fallback)")
                        success = True
                    except Exception as he:
                        print(f"  [ERROR] CPU Fallback failed for clip {i}: {he}")
                
                # FALLBACK 2: Try without subtitles if still failing (or if it was CPU from start)
                if not success and ffmpeg_vf_args:
                    print(f"  [INFO] Retrying clip {i} WITHOUT subtitles...")
                    
                    # Filter out subtitle filters
                    current_params = encoding_params.get('ffmpeg_params', [])
                    new_params = []
                    skip_next = False
                    for param in current_params:
                        if skip_next:
                            skip_next = False
                            continue
                        if param == '-vf' or param == '-filter:v':
                            skip_next = True
                            continue 
                        if "subtitles=" in param:
                            continue
                        new_params.append(param)
                            
                    encoding_params['ffmpeg_params'] = new_params
                    
                    try:
                        portrait_clip.write_videofile(output_path, **encoding_params)
                        print(f"  [SUCCESS] Clip {i} saved (WITHOUT subtitles fallback)")
                        success = True
                    except Exception as e2:
                         print(f"  [ERROR] Retry failed for clip {i}: {e2}")
                         raise e2 # Rethrow to trigger main error handler
                         
                if not success:
                    raise e # Rethrow original exception if all fallbacks failed
            
            if os.path.exists(output_path):
                file_size_mb = os.path.getsize(output_path) / (1024 * 1024)
                print(f"  ✅ Clip {i} saved: {output_filename} ({file_size_mb:.2f} MB)")
                
                # Success! Unregister from cleanup
                cleanup_manager.unregister_output(output_path)
            
            # Return result with output path and basic metrics
            return {
                'output_path': output_path,
                'clip_number': i,
                'duration': duration,
                'file_size_mb': file_size_mb,
                'processing_time': time.perf_counter() - start_time_process
            }
            
    except Exception as e:
        print(f"[ERROR] Error processing clip {i}: {e}")
        traceback.print_exc()
        # The CleanupManager (via register_output) will handle deleting the partial file if the process exits/cleans up?
        # Atexit cleanup handles crash/exit.
        # But if we just catch Exception here and continue to next clip, we should proactively clean THIS clip's junk.
        if output_path and os.path.exists(output_path):
             try:
                 os.remove(output_path)
                 cleanup_manager.unregister_output(output_path)
             except: pass
        if temp_audio_file and os.path.exists(temp_audio_file):
             try:
                 os.remove(temp_audio_file)
             except: pass
        return None
    
    finally:
        # Ensure temp files are cleaned up even if an error occurs
        if temp_audio_file and os.path.exists(temp_audio_file):
            try:
                os.remove(temp_audio_file)
            except Exception as e:
                print(f"  [WARNING] Could not remove temp audio file {temp_audio_file}: {e}")
        if temp_ass_file and os.path.exists(temp_ass_file):
            try:
                os.remove(temp_ass_file)
            except Exception as e:
                print(f"  [WARNING] Could not remove temp ASS file {temp_ass_file}: {e}")

def cut_video_clips(video_path, clips_data, output_folder="clips", add_subtitles=False, phrase_timings=None, subtitle_config=None, min_duration=30, smart_crop=True, use_original_resolution=False, randomize_metadata=False, custom_metadata=None, add_viral_hook=False, hook_styles=None, target_resolution=None, canvas_resolution=None, progress_callback=None, check_cancelled=None, max_workers=1, encoding_threads=0, encoding_preset='medium'):
    """
    Cuts video into multiple clips using ProcessPoolExecutor for safety.
    """
    if not clips_data:
        return []
    
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
        
    config = VideoProcessingConfig()
    output_paths = []
    
    print(f"\n{'='*70}")
    # Monitor Resources
    monitor = LocalProcessMonitor()
    monitor.start()
    
    # Update config with passed params
    if max_workers:
        config.max_workers = max_workers
    if encoding_threads is not None:
        config.encoding_threads = encoding_threads  # 0 = auto
    if encoding_preset:
        config.encoding_preset = encoding_preset
        
    print(f"[INFO] VIDEO CUTTING - Starting (Parallel ProcessPool)")
    print(f"   Workers: {config.max_workers}")
    print(f"   Encoding Threads: {config.encoding_threads}")
    
    # Create shared event for cancellation
    manager = multiprocessing.Manager()
    cancel_event = manager.Event()
    
    # --- NON-BLOCKING CANCELLATION MONITOR ---
    # The main thread blocks on future.result(), so we need a separate thread
    # to continuously check the cancel callback and set the event immediately.
    stop_monitor_event = threading.Event()

    def monitor_cancellation():
        while not stop_monitor_event.is_set():
            if check_cancelled and check_cancelled():
                print(f"[INFO] 🛑 Cancellation detected by monitor thread! Signaling workers...")
                cancel_event.set()
                # We can also try to cancel futures here if we had access to executor, 
                # but setting the event is the most critical part for child processes.
                break
            time.sleep(0.5)
            
    monitor_thread = threading.Thread(target=monitor_cancellation, daemon=True)
    monitor_thread.start()
    
    try:
        # Prepare Tasks
        tasks = []
        total_clips = len(clips_data)
        
        for i, clip_info in enumerate(clips_data, 1):
            tasks.append((
                i, clip_info, total_clips, video_path, output_folder, 
                add_subtitles, phrase_timings, subtitle_config, min_duration, 
                smart_crop, use_original_resolution, randomize_metadata, 
                custom_metadata, add_viral_hook, hook_styles, target_resolution, canvas_resolution,
                cancel_event # Pass the shared event
            ))
            
        # Execute
        with concurrent.futures.ProcessPoolExecutor(max_workers=config.max_workers) as executor:
            # Submit all tasks
            futures = {executor.submit(process_single_clip, task): i for i, task in enumerate(tasks, 1)}
            
            # Initialize results array with None to preserve order/indices
            sorted_paths = [None] * total_clips
            failed_clips = []
            
            # Process results as they complete
            for future in concurrent.futures.as_completed(futures):
                idx = futures[future]
                
                # Check for cancellation
                if check_cancelled and check_cancelled():
                    print(f"[INFO] Cancellation detected in cut_video_clips! Shutting down executor...")
                    
                    # Signal all workers to stop
                    cancel_event.set()
                    
                    executor.shutdown(wait=False, cancel_futures=True)
                    # We can't easily kill running processes from here without advanced OS calls,
                    # but shutdown(cancel_futures=True) stops pending ones.
                    # Returning early will exit the 'with' block which calls shutdown(wait=True) by default,
                    # so we might hang unless we forcefully return.
                    # But since we called shutdown(wait=False), the executor is already closing.
                    # The 'with' block might still wait for running tasks.
                    # A return here is the best we can do safely in Python without `os.kill`.
                    return [None] * total_clips

                try:
                    result = future.result()
                    if result is not None:
                        # Extract just the path string as expected by caller
                        sorted_paths[idx-1] = result['output_path']
                        if tqdm:
                            print(f"✓ Clip {idx}/{total_clips} complete")
                    else:
                        failed_clips.append(idx)
                        if tqdm:
                            print(f"✗ Clip {idx} failed")
                    
                    # Report progress
                    if progress_callback:
                        # Count completed (success or fail)
                        completed_count = sum(1 for f in futures if f.done())
                        progress_callback(completed_count / total_clips)
                        
                except Exception as e:
                    print(f"[ERROR] Future {idx} raised exception: {e}")
                    failed_clips.append(idx)
                    if progress_callback:
                        completed_count = sum(1 for f in futures if f.done())
                        progress_callback(completed_count / total_clips)
        
        # Report failures if any
        if failed_clips:
            print(f"\n{'='*70}")
            print(f"⚠️  WARNING: {len(failed_clips)} clip(s) failed to process")
            print(f"{'='*70}")
            print(f"Failed clip numbers: {failed_clips}")
            print(f"Common reasons:")
            print(f"  • Clip duration too short (< 1 second)")
            print(f"  • Invalid timestamp range")
            print(f"  • Video processing error (check logs above)")
            print(f"{'='*70}\n")
        
        # Replace output_paths with our sorted list
        output_paths = sorted_paths
        
    except Exception as e:
        print(f"Critical error in batch processing: {e}")
        traceback.print_exc()
        # Ensure we return a list of None if critical failure
        if not output_paths:
            output_paths = [None] * len(clips_data)
            
    finally:
        # Stop background threads
        stop_monitor_event.set()
        monitor_thread.join(timeout=1.0)
        
        stats = monitor.stop()
        print(f"\n[INFO] Resource Usage:")
        print(f"   Avg CPU: {stats['avg_cpu']:.1f}%")
        print(f"   Peak Memory: {stats['peak_memory_gb']:.2f} GB")
        # Count non-None entries
        success_count = sum(1 for p in output_paths if p is not None)
        print(f"   Success Rate: {success_count}/{len(clips_data)}")

    return output_paths

if __name__ == "__main__":
    print("Video Cutter Module")
    # Basic syntax check
    config = VideoProcessingConfig()
    print(f"Loaded config with {config.max_workers} workers.")
