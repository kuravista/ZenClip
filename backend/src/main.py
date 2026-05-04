import os
import certifi
from dotenv import load_dotenv

from services.ai.llm_analyzer import analyze_transcript_with_llm
from services.media.time_alignment import snap_to_phrase_boundaries
from services.ai.smart_metadata import generate_fallback_smart_metadata

# Load environment variables from .env file
load_dotenv()

# Set SSL certificate environment variable
os.environ['SSL_CERT_FILE'] = certifi.where()

# Expose functions that might be imported by app.py
__all__ = [
    'analyze_transcript_with_llm',
    'snap_to_phrase_boundaries',
    'generate_fallback_smart_metadata'
]
