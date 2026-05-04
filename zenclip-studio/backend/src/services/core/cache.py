import os
import json
import hashlib
import time
import sys

# Determine a writable cache directory depending on environment
# In production (sidecar or frozen), os.getcwd() may be read-only bundled dir.
def _get_cache_dir():
    override_app_data_dir = os.environ.get('CLIP_APP_DATA_DIR')
    default_app_data_dir = os.environ.get('CLIP_DEFAULT_APP_DATA_DIR')
    if override_app_data_dir:
        from pathlib import Path
        return str(Path(override_app_data_dir) / 'cache')
    if default_app_data_dir:
        from pathlib import Path
        return str(Path(default_app_data_dir) / 'cache')
    if getattr(sys, 'frozen', False) or os.environ.get('CLIP_SIDECAR_DIR'):
        # Production: write to Documents/SnipieAI/cache
        from pathlib import Path
        return str(Path.home() / 'Documents' / 'SnipieAI' / 'cache')
    else:
        # Dev: use project-relative path (same as before)
        return os.path.join(os.getcwd(), 'cache')

CACHE_DIR = _get_cache_dir()
os.makedirs(CACHE_DIR, exist_ok=True)

def get_file_hash(filepath):
    """
    Calculate SHA256 hash of a file to uniquely identify it.
    Reads in chunks to handle large files efficiently.
    """
    sha256_hash = hashlib.sha256()
    try:
        with open(filepath, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    except Exception as e:
        print(f"Error calculating hash: {e}")
        return None

def get_cache_path(identifier):
    """Generate a file path for the cache based on an identifier (hash or video_id)"""
    return os.path.join(CACHE_DIR, f"{identifier}.json")

def get_cached_transcript(identifier):
    """
    Retrieve transcript from cache if it exists.
    Returns the phrase_timings list or None.
    """
    cache_path = get_cache_path(identifier)
    if os.path.exists(cache_path):
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            print(f"✅ Cache Hit! Loaded transcript for {identifier}")
            return data.get('phrase_timings'), data.get('meta', {}).get('language', 'en')
        except Exception as e:
            print(f"Error reading cache: {e}")
            return None
    return None

def save_transcript_to_cache(identifier, phrase_timings, source_type='upload', extra_meta=None, language='en'):
    """
    Save transcript to cache.
    """
    cache_path = get_cache_path(identifier)
    meta = extra_meta or {}
    meta['language'] = language
    
    data = {
        'identifier': identifier,
        'source_type': source_type,
        'created_at': time.time(),
        'phrase_timings': phrase_timings,
        'phrase_timings': phrase_timings,
        'meta': meta
    }
    try:
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"💾 Transcript cached for {identifier}")
    except Exception as e:
        print(f"Error saving cache: {e}")
