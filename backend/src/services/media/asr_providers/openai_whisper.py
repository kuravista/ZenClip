"""
OpenAI Whisper Provider (Fallback ASR Provider)

Uses the openai-whisper library for more stable ASR processing
without the the native library issues of compared to Faster Whisper.
"""

import os
import subprocess
import tempfile
import json
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
import logging

from .asr_provider import ASRProvider, TranscriptionResult

log = logging.getLogger(__name__)


class OpenAIWhisperProvider(ASRProvider):
    """
    OpenAI Whisper provider using the official OpenAI Whisper library.

    More stable but slower than Faster Whisper.
    No CTranslate2 dependency.
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

            # Transcribe
            result = model.transcribe(
                audio_path,
                language=language,
                word_timestamps=True
            )

            # Convert to standard format
            phrases = []
            for segment in result["segments"]:
                phrase = {
                    "text": segment.text,
                    "start": segment.start,
                    "end": segment.end,
                    "words": []
                }
                # Extract words if available
                if "words" in segment:
                    for word in segment["words"]:
                        phrase["words"].append({
                            "text": word.word,
                            "start": word.start,
                            "end": word.end
                        })

                phrases.append(phrase)

            return TranscriptionResult(
                phrases=phrases,
                language=result.get("language", "unknown"),
                duration=result.get("segments", 0),
                provider=self.name,
                success=True
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
    OpenAI Whisper API provider (cloud-based).

    Most reliable but requires API key and internet connection.
    """

    def __init__(self, api_key: str, model: str = "whisper-1"):
        self.api_key = api_key
        self.model = model
        self._available = None

    @property
    def name(self) -> str:
        return "whisper-api"

    @property
    def is_available(self) -> bool:
        if self._available is not None:
            return self._available

        return bool(self.api_key and len(self.api_key) > 0)

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
                error="Whisper API not available or            )

        try:
            import openai
            client = openai.OpenAI(api_key=self.api_key)

            # Read audio file
            with open(audio_path, "rb") as audio_file:
                audio_data = audio_file.read()

            # Call API
            response = client.audio.transcriptions.create(
                model=self.model,
                file=audio_data,
                language=language
            )

            # Parse response
            transcript = response.text
            result = json.loads(transcript)

            phrases = []
            for segment in result.get("segments", []):
                phrase = {
                    "text": segment["text"],
                    "start": segment["start"],
                    "end": segment["end"],
                    "words": segment.get("words", [])
                }
                phrases.append(phrase)

            return TranscriptionResult(
                phrases=phrases,
                language=result.get("language", "unknown"),
                duration=result.get("duration", 0),
                provider=self.name,
                success=True
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
    Subprocess-based ASR provider.

    Runs transcription in isolated process to prevent main process crashes.
    Most reliable fallback.
    """

    def __init__(self, python_path: Optional[str] = None):
        self.python_path = python_path or sys.executable
        self._available = None

    @property
    def name(self) -> str:
        return "subprocess"

    @property
    def is_available(self) -> bool:
        if self._available is not None:
            return self._available

        # Check if python is available
        try:
            result = subprocess.run(
                [self.python_path or "python", "-c", "import whisper; print('ok')"],
                capture_output=True,
                timeout=5
            )
            self._available = True
        except Exception:
            self._available = False

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
                error="Subprocess ASR not available"
            )

        try:
            # Run transcription in subprocess
            script = f"""
import whisper
import json
import sys

model = whisper.load_model("base")
            result = model.transcribe("{audio_path}", language="{language or ''}", word_timestamps=True)

            phrases = []
            for segment in result["segments"]:
                phrase = {{
                    "text": segment.text,
                    "start": segment.start,
                    "end": segment.end,
                    "words": []
                }}
                if "words" in segment:
                    for word in segment["words"]:
                        phrase["words"].append({{
                            "text": word.word,
                            "start": word.start,
                            "end": word.end
                        }})
                phrases.append(phrase)

            output = {{
                "phrases": phrases,
                "language": result.get("language", "unknown"),
                "duration": result.get("segments", [{{"end": 0}}])[-1].get("end", 1) if result.get("segments") else 1
            }}

            print(json.dumps(output))
            """

            result = subprocess.run(
                [self.python_path, "-c", script.replace("{audio_path}", audio_path).replace("{language}", language or "")],
                capture_output=True,
                timeout=300,
                text=True
            )

            data = json.loads(result.stdout)
            return TranscriptionResult(
                phrases=data["phrases"],
                language=data["language"],
                duration=data["duration"],
                provider=self.name,
                success=True
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


# Provider selection
def get_asr_provider(
    preferred: Optional[str] = None,
    fallback: bool = True
) -> Optional[ASRProvider]:
    """
    Get ASR provider based on availability and preference.

    Args:
        preferred: Preferred provider name
        fallback: If True, try next provider if preferred fails

    Returns:
        ASRProvider or None if no providers available
    """
    providers = [
        ("faster-whisper", FasterWhisperProvider),
        ("openai-whisper", OpenAIWhisperProvider),
        ("subprocess", SubprocessASRProvider),
    ]

    # Check preferred first
    if preferred:
        for name, cls in providers:
            if name == preferred:
                provider = cls()
                if provider.is_available:
                    return provider
                elif not fallback:
                    return None

    # Try providers in order
    for name, cls in providers:
        provider = cls()
        if provider.is_available:
            return provider

    return None


def transcribe_audio(
    audio_path: str,
    language: Optional[str] = None,
    provider: Optional[str] = None,
) -> TranscriptionResult:
    """
    Transcribe audio file using best available ASR provider.

    Args:
        audio_path: Path to audio file
        language: Optional language hint
        provider: Optional preferred provider name

    Returns:
        TranscriptionResult with phrases and metadata
    """
    asr = get_asr_provider(preferred=provider)

    if asr is None:
        return TranscriptionResult(
            phrases=[],
            language="",
            duration=0,
            provider="none",
            success=False,
            error="No ASR provider available"
        )

    return asr.transcribe(audio_path, language=language)
