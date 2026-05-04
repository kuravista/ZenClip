from utils.logger import log
"""
Video Encoding Utilities
Provides platform-specific optimized video codec selection for hardware-accelerated encoding.
"""

import platform
import sys


def get_optimal_video_codec():
    """
    Detects platform and returns optimal video codec with parameters.
    
    Returns:
        tuple: (codec_name, extra_params_dict)
            - codec_name (str): FFmpeg codec name ('h264_videotoolbox' or 'libx264')
            - extra_params_dict (dict): Codec-specific parameters
    
    Examples:
        >>> codec, params = get_optimal_video_codec()
        >>> # On macOS: ('h264_videotoolbox', {'preset': None})
        >>> # On Windows/Linux: ('libx264', {'preset': 'medium'})
    """
    system = platform.system()
    
    if system == 'Darwin':  # macOS
        # Use VideoToolbox hardware encoder on macOS (Apple Silicon & Intel)
        # VideoToolbox leverages GPU for much faster encoding
        return 'h264_videotoolbox', {
            'preset': None,  # VideoToolbox doesn't use x264 presets
        }
    elif system == 'Windows':
        if check_nvidia_gpu():
            log.info("NVIDIA GPU detected, using h264_nvenc", module="VideoEncoder")
            return 'h264_nvenc', {'preset': 'p4', 'gpu': 0}

        if check_amd_gpu():
            log.info("AMD GPU detected, using h264_amf", module="VideoEncoder")
            return 'h264_amf', {'usage': 'transcoding'}
        
        if check_intel_qsv():
             log.info("Intel QuickSync detected, using h264_qsv", module="VideoEncoder")
             return 'h264_qsv', {'preset': 'medium'}
             
        # Use libx264 software encoder on Windows as fallback
        return 'libx264', {'preset': 'medium'}
    else:  # Linux and others
        if check_nvidia_gpu():
            return 'h264_nvenc', {'preset': 'p4'}
        return 'libx264', {'preset': 'medium'}

def check_nvidia_gpu():
    try:
        import subprocess
        import os
        # Fast fail: Check using nvidia-smi
        result = subprocess.run(['nvidia-smi'], capture_output=True, text=True)
        if result.returncode != 0:
            return False
            
        # Actual validation: Test if ffmpeg can use NVENC (catches old drivers)
        from services.core.binary_manager import get_ffmpeg_path
        ffmpeg_exe = get_ffmpeg_path()
        null_file = 'NUL' if os.name == 'nt' else '/dev/null'
        
        test_result = subprocess.run([
            ffmpeg_exe, '-y', '-v', 'error',
            '-f', 'lavfi', '-i', 'color=black:s=64x64:d=0.1',
            '-c:v', 'h264_nvenc',
            '-f', 'null', null_file
        ], capture_output=True, text=True, timeout=5)
        
        if test_result.returncode == 0:
            return True
        else:
            log.warning(f"NVENC test failed (driver too old/unsupported?): {test_result.stderr.strip()}", module="VideoEncoder")
            return False
    except Exception as e:
        return False

def check_amd_gpu():
    """Check for AMD GPU with AMF support using actual initialization"""
    try:
        import subprocess
        import os
        from services.core.binary_manager import get_ffmpeg_path
        ffmpeg_exe = get_ffmpeg_path()
        null_file = 'NUL' if os.name == 'nt' else '/dev/null'
        
        test_result = subprocess.run([
            ffmpeg_exe, '-y', '-v', 'error',
            '-f', 'lavfi', '-i', 'color=black:s=64x64:d=0.1',
            '-c:v', 'h264_amf',
            '-f', 'null', null_file
        ], capture_output=True, text=True, timeout=5)
        
        if test_result.returncode == 0:
            return True
        else:
            log.warning(f"AMF test failed (driver too old/unsupported?): {test_result.stderr.strip()}", module="VideoEncoder")
            return False
    except Exception as e:
        return False

def check_intel_qsv():
    # Simple check for QuickSync availability could be complex, 
    # but often safe to assume on modern Intel CPUs if ffmpeg supports it.
    # However, to be safe, we disable unless confident or user enables it.
    # For now, simplistic check:
    return False # Disable by default unless we implement robust ffmpeg capability check


def get_encoding_params(codec_name, base_params):
    """
    Returns optimized encoding parameters for the given codec.
    Removes incompatible parameters for hardware encoders.
    
    Args:
        codec_name (str): Name of the codec ('h264_videotoolbox' or 'libx264')
        base_params (dict): Base parameters dict from caller
        
    Returns:
        dict: Complete encoding parameters with codec-specific optimizations
        
    Examples:
        >>> params = {'preset': 'medium', 'bitrate': '5000k'}
        >>> optimized = get_encoding_params('h264_videotoolbox', params)
        >>> # Returns params without 'preset' for VideoToolbox
    """
    params = base_params.copy()
    
    if codec_name == 'h264_videotoolbox':
        # VideoToolbox-specific optimizations
        # Remove x264-specific params that VideoToolbox doesn't support
        if 'preset' in params:
            del params['preset']
        
        # VideoToolbox uses different quality control mechanisms
        # The 'bitrate' parameter works, but preset doesn't apply
        
    elif codec_name == 'h264_nvenc':
        # NVIDIA NVENC hardware encoder
        # Remove x264 presets, use NVENC presets (p1-p7)
        # 'preset' is already set correctly in get_optimal_video_codec
        pass

    elif codec_name == 'h264_amf':
        # AMD AMF hardware encoder
        # Remove incompatible x264 'preset'
        if 'preset' in params:
            del params['preset']
        
        # Ensure usage is set for optimal quality/speed
        if 'usage' not in params:
            params['usage'] = 'transcoding'
        
    elif codec_name == 'h264_qsv':
        # Intel QuickSync hardware encoder
        # Similar to x264 but with hardware acceleration
        if 'preset' not in params:
            params['preset'] = 'medium'
            
    elif codec_name == 'libx264':
        # libx264 supports all standard parameters
        # Ensure preset is set for optimal encoding
        if 'preset' not in params:
            params['preset'] = 'medium'
    
    return params


def get_codec_display_name(codec_name):
    """
    Returns user-friendly display name for codec.
    
    Args:
        codec_name (str): FFmpeg codec name
        
    Returns:
        str: Human-readable codec name
    """
    codec_names = {
        'h264_videotoolbox': 'H.264 VideoToolbox (Hardware Accelerated)',
        'libx264': 'H.264 libx264 (Software)',
        'h264_nvenc': 'H.264 NVENC (NVIDIA GPU)',
        'h264_amf': 'H.264 AMF (AMD GPU)',
        'h264_qsv': 'H.264 Quick Sync (Intel GPU)',
    }
    return codec_names.get(codec_name, codec_name)


# Export public API
__all__ = [
    'get_optimal_video_codec',
    'get_encoding_params',
    'get_codec_display_name',
]
