"""
ASR Provider Abstraction Layer

Provides a unified interface for multiple Automatic Speech Recognition providers:
- FasterWhisperProvider (CTranslate2) - Primary, but may crash on some systems
- OpenAIWhisperProvider (openai/whisper) - Fallback, more stable
- WhisperAPIProvider - Cloud-based fallback

Usage:
    from services.media.asr_provider import get_asr_provider, ASRProvider

    provider = get_asr_provider()
    if provider.is_available():
        result = provider.transcribe(video_path)
"""
import os
import subprocess
import json
import tempfile
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from pathlib import Path
import logging

log = logging.getLogger(__name__)


@dataclass
class TranscriptionResult:
    """Result from ASR transcription."""
    phrases: List[Dict[str, Any]]
    language: str
    duration: float
    provider: str
    success: bool = True
    error: Optional[str] = None


class ASRProvider(ABC):
    """Abstract base class for ASR providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name."""
        pass

    @property
    @abstractmethod
    def is_available(self) -> bool:
        """Check if provider is available."""
        pass

    @abstractmethod
    def transcribe(
        self,
        audio_path: str,
        language: Optional[str] = None,
        **kwargs
    ) -> TranscriptionResult:
        """
        Transcribe audio file.

        Args:
            audio_path: Path to audio file
            language: Optional language hint (e.g., 'en', 'id')
            **kwargs: Provider-specific options

        Returns:
            TranscriptionResult with phrases and metadata
        """
        pass


class FasterWhisperProvider(ASRProvider):
    """
    Faster Whisper provider using CTranslate2.

    Fast but may crash on some systems due to native library issues.
    """

    def __init__(self, model_size: str = "base", device: str = "auto"):
        self.model_size = model_size
        self.device = device
        self._model = None
        self._available = None

    @property
    def name(self) -> str:
        return "faster-whisper"

    @property
    def is_available(self) -> bool:
        if self._available is not None:
            return self._available

        try:
            import faster_whisper
            self._available = True
        except ImportError:
            self._available = False

        return self._available

    def _load_model(self):
        """Load model lazily."""
        if self._model is None:
            from faster_whisper import WhisperModel
            self._model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type="auto"
            )
        return self._model

    def transcribe(
        self,
        audio_path: str,
        language: Optional[str] = None,
        **kwargs
    ) -> TranscriptionResult:
        if not self.is_available:
            return TranscriptionResult(
                phrases=[],
                language="",
                duration=0,
                provider=self.name,
                success=False,
                error="Faster Whisper not available"
            )

        try:
            model = self._load_model()

            segments, info = model.transcribe(
                audio_path,
                language=language,
                beam_size=5,
                vad_filter=True
            )

            phrases = []
            for segment in segments:
                words = []
                if hasattr(segment, 'words') and segment.words:
                    words = [
                        {
                            "text": w.word,
                            "start": w.start,
                            "end": w.end,
                            "probability": getattr(w, 'probability', 1.0)
                        }
                        for w in segment.words
                    ]

                phrases.append({
                    "text": segment.text.strip(),
                    "start": segment.start,
                    "end": segment.end,
                    "words": words
                })

            return TranscriptionResult(
                phrases=phrases,
                language=info.language,
                duration=info.duration,
                provider=self.name
            )

        except Exception as e:
            return TranscriptionResult(
                phrases=[],
                language="",
                duration=0,
                provider=self.name,
                success=False,
                error=str(e)
            )


class OpenAIWhisperProvider(ASRProvider):
    """
    OpenAI Whisper provider using the original whisper package.

    More stable but slower than Faster Whisper.
    """

    def __init__(self, model_size: str = "base"):
        self.model_size = model_size
        self._model = None
        self._available = None

    @property
    def name(self) -> str:
        return "openai-whisper"

    @property
    def is_available(self) -> bool:
        if self._available is not None:
            return self._available

        try:
            import whisper
            self._available = True
        except ImportError:
            self._available = False

        return self._available

    def _load_model(self):
        """Load model lazily."""
        if self._model is None:
            import whisper
            self._model = whisper.load_model(self.model_size)
        return self._model

    def transcribe(
        self,
        audio_path: str,
        language: Optional[str] = None,
        **kwargs
    ) -> TranscriptionResult:
        if not self.is_available:
            return TranscriptionResult(
                phrases=[],
                language="",
                duration=0,
                provider=self.name,
                success=False,
                error="OpenAI Whisper not available"
            )

        try:
            model = self._load_model()

            options = {}
            if language:
                options["language"] = language

            result = model.transcribe(audio_path, **options)

            phrases = []
            for segment in result.get("segments", []):
                words = []
                if "words" in segment:
                    words = [
                        {
                            "text": w.get("word", ""),
                            "start": w.get("start", 0),
                            "end": w.get("end", 0)
                        }
                        for w in segment["words"]
                    ]

                phrases.append({
                    "text": segment["text"].strip(),
                    "start": segment["start"],
                    "end": segment["end"],
                    "words": words
                })

            duration = result.get("segments", [{}])[-1].get("end", 0) if phrases else 0

            return TranscriptionResult(
                phrases=phrases,
                language=result.get("language", "unknown"),
                duration=duration,
                provider=self.name
            )

        except Exception as e:
            return TranscriptionResult(
                phrases=[],
                language="",
                duration=0,
                provider=self.name,
                success=False,
                error=str(e)
            )


class WhisperAPIProvider(ASRProvider):
    """
    Cloud-based Whisper API provider.

    Uses OpenAI's Whisper API for transcription.
    Requires API key.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self._available = None

    @property
    def name(self) -> str:
        return "whisper-api"

    @property
    def is_available(self) -> bool:
        if self._available is not None:
            return self._available

        self._available = bool(self.api_key)
        return self._available

    def transcribe(
        self,
        audio_path: str,
        language: Optional[str] = None,
        **kwargs
    ) -> TranscriptionResult:
        if not self.is_available:
            return TranscriptionResult(
                phrases=[],
                language="",
                duration=0,
                provider=self.name,
                success=False,
                error="OpenAI API key not configured"
            )

        try:
            import openai

            client = openai.OpenAI(api_key=self.api_key)

            with open(audio_path, "rb") as audio_file:
                options = {}
                if language:
                    options["language"] = language

                transcript = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    response_format="verbose_json",
                    **options
                )

            phrases = []
            if hasattr(transcript, 'segments'):
                for segment in transcript.segments:
                    phrases.append({
                        "text": segment.text.strip(),
                        "start": segment.start,
                        "end": segment.end,
                        "words": []
                    })

            return TranscriptionResult(
                phrases=phrases,
                language=getattr(transcript, 'language', 'unknown'),
                duration=getattr(transcript, 'duration', 0),
                provider=self.name
            )

        except Exception as e:
            return TranscriptionResult(
                phrases=[],
                language="",
                duration=0,
                provider=self.name,
                success=False,
                error=str(e)
            )


class SubprocessASRProvider(ASRProvider):
    """
    Isolated subprocess ASR provider.

    Runs transcription in a separate process to prevent crashes
    from affecting the main server.
    """

    def __init__(self, provider_type: str = "faster-whisper"):
        self.provider_type = provider_type
        self._available = None

    @property
    def name(self) -> str:
        return f"subprocess-{self.provider_type}"

    @property
    def is_available(self) -> bool:
        return True  # Always available, will fail gracefully

    def transcribe(
        self,
        audio_path: str,
        language: Optional[str] = None,
        **kwargs
    ) -> TranscriptionResult:
        try:
            # Create subprocess script
            script = f'''
import sys
import json

audio_path = {repr(audio_path)}
language = {repr(language)}
provider_type = {repr(self.provider_type)}

try:
    if provider_type == "faster-whisper":
        from faster_whisper import WhisperModel
        model = WhisperModel("base", device="cpu", compute_type="int8")
        segments, info = model.transcribe(audio_path, language=language)
        phrases = [
            {{"text": s.text.strip(), "start": s.start, "end": s.end, "words": []}}
            for s in segments
        ]
        result = {{"success": True, "phrases": phrases, "language": info.language, "duration": info.duration}}
    elif provider_type == "openai-whisper":
        import whisper
        model = whisper.load_model("base")
        result_raw = model.transcribe(audio_path, language=language)
        phrases = [
            {{"text": s["text"].strip(), "start": s["start"], "end": s["end"], "words": []}}
            for s in result_raw.get("segments", [])
        ]
        duration = result_raw.get("segments", [{{}}])[-1].get("end", 0) if phrases else 0
        result = {{"success": True, "phrases": phrases, "language": result_raw.get("language", "unknown"), "duration": duration}}
    else:
        result = {{"success": False, "error": f"Unknown provider: {{provider_type}}"}}
except Exception as e:
    result = {{"success": False, "error": str(e)}}

print(json.dumps(result))
'''

            result = subprocess.run(
                [sys.executable, "-c", script],
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )

            if result.returncode != 0:
                return TranscriptionResult(
                    phrases=[],
                    language="",
                    duration=0,
                    provider=self.name,
                    success=False,
                    error=result.stderr or "Subprocess failed"
                )

            data = json.loads(result.stdout.strip())

            if not data.get("success", False):
                return TranscriptionResult(
                    phrases=[],
                    language="",
                    duration=0,
                    provider=self.name,
                    success=False,
                    error=data.get("error", "Unknown error")
                )

            return TranscriptionResult(
                phrases=data.get("phrases", []),
                language=data.get("language", "unknown"),
                duration=data.get("duration", 0),
                provider=self.name
            )

        except subprocess.TimeoutExpired:
            return TranscriptionResult(
                phrases=[],
                language="",
                duration=0,
                provider=self.name,
                success=False,
                error="Transcription timeout"
            )
        except Exception as e:
            return TranscriptionResult(
                phrases=[],
                language="",
                duration=0,
                provider=self.name,
                success=False,
                error=str(e)
            )


def get_asr_provider(preferred: Optional[str] = None) -> ASRProvider:
    """
    Get ASR provider based on preference and availability.

    Args:
        preferred: Preferred provider type
            - "faster-whisper" (default)
            - "openai-whisper"
            - "whisper-api"
            - "subprocess" (isolated)

    Returns:
        Best available ASR provider
    """
    provider_type = preferred or os.environ.get("CLIP_ASR_PROVIDER", "faster-whisper")

    if provider_type == "faster-whisper":
        provider = FasterWhisperProvider()
        if provider.is_available:
            return provider

        # Fall back to subprocess
        return SubprocessASRProvider("faster-whisper")

    elif provider_type == "openai-whisper":
        provider = OpenAIWhisperProvider()
        if provider.is_available:
            return provider

        # Fall back to subprocess
        return SubprocessASRProvider("openai-whisper")

    elif provider_type == "whisper-api":
        return WhisperAPIProvider()

    elif provider_type == "subprocess":
        return SubprocessASRProvider("faster-whisper")

    else:
        # Default to subprocess for safety
        return SubprocessASRProvider("faster-whisper")


def probe_asr_runtime() -> Dict[str, Any]:
    """
    Probe available ASR providers and their status.

    Returns:
        Dict with provider availability info
    """
    providers = {}

    # Check Faster Whisper
    try:
        fw = FasterWhisperProvider()
        providers["faster-whisper"] = {
            "available": fw.is_available,
            "name": fw.name
        }
    except Exception as e:
        providers["faster-whisper"] = {"available": False, "error": str(e)}

    # Check OpenAI Whisper
    try:
        ow = OpenAIWhisperProvider()
        providers["openai-whisper"] = {
            "available": ow.is_available,
            "name": ow.name
        }
    except Exception as e:
        providers["openai-whisper"] = {"available": False, "error": str(e)}

    # Check Whisper API
    try:
        wa = WhisperAPIProvider()
        providers["whisper-api"] = {
            "available": wa.is_available,
            "name": wa.name
        }
    except Exception as e:
        providers["whisper-api"] = {"available": False, "error": str(e)}

    # Subprocess is always available
    providers["subprocess"] = {
        "available": True,
        "name": "subprocess-isolated"
    }

    return providers
