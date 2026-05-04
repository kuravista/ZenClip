import sys
import io
import os

def force_utf8_std():
    """
    Force sys.stdout and sys.stderr to use UTF-8 encoding.
    This prevents UnicodeEncodeError on Windows consoles when printing emojis.
    Safe to call multiple times.
    """
    if sys.stdout and not isinstance(sys.stdout, io.TextIOWrapper):
        # Can't wrap if not a buffer/file-like, e.g. if already captured by something weird
        pass
    
    # Only wrap if we can access buffer and encoding isn't already utf-8
    try:
        if sys.stdout and hasattr(sys.stdout, 'buffer'):
            # check if encoding is already utf-8 (case insensitive)
            if not sys.stdout.encoding or sys.stdout.encoding.lower() != 'utf-8':
                sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
                
        if sys.stderr and hasattr(sys.stderr, 'buffer'):
            if not sys.stderr.encoding or sys.stderr.encoding.lower() != 'utf-8':
                sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
    except Exception as e:
        # If we fail, safe to ignore, but maybe log to file if we could
        pass

# Auto-execute on import
force_utf8_std()
