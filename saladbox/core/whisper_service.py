"""Speech-to-text service using faster-whisper (CTranslate2)."""

from __future__ import annotations

import base64
import io
import logging
import tempfile
from pathlib import Path

from saladbox.config import WhisperConfig

logger = logging.getLogger(__name__)


class WhisperService:
    """Lazy-loaded faster-whisper transcription service.

    The Whisper model is only loaded on the first transcription request,
    avoiding ~150 MB+ of RAM at startup for users who never use voice input.
    """

    def __init__(self, config: WhisperConfig) -> None:
        self._config = config
        self._model = None  # loaded on first use

    # ── public API ──────────────────────────────────────────

    def transcribe_base64_webm(self, audio_base64: str) -> str:
        """Transcribe base64-encoded WebM audio to text.

        Args:
            audio_base64: Base64-encoded WebM audio data (from browser
                          ``MediaRecorder``).

        Returns:
            Transcribed text string.
        """
        self._ensure_model()

        # 1. Decode base64 → raw bytes
        if not audio_base64 or not audio_base64.strip():
            return ""
        try:
            audio_bytes = base64.b64decode(audio_base64, validate=True)
        except Exception as e:
            raise ValueError(f"Invalid base64 audio data: {e}") from e

        if len(audio_bytes) < 100:
            return ""  # too small to be valid audio

        # 2. Convert WebM → mono 16 kHz WAV via pydub (needs ffmpeg)
        from pydub import AudioSegment

        audio_segment = AudioSegment.from_file(
            io.BytesIO(audio_bytes), format="webm"
        )
        audio_segment = audio_segment.set_channels(1).set_frame_rate(16000)

        # 3. Write temp WAV file (faster-whisper reads from path)
        tmp_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                suffix=".wav", delete=False
            ) as tmp:
                audio_segment.export(tmp.name, format="wav")
                tmp_path = tmp.name

            # 4. Run transcription
            kwargs: dict = {}
            if self._config.language:
                kwargs["language"] = self._config.language

            segments, info = self._model.transcribe(tmp_path, **kwargs)

            # 5. Collect segment texts
            text_parts: list[str] = []
            for segment in segments:
                text_parts.append(segment.text.strip())

            result = " ".join(text_parts).strip()
            logger.info(
                f"Transcription complete: lang={info.language}, "
                f"duration={info.duration:.1f}s, chars={len(result)}"
            )
            return result

        finally:
            # Clean up temp file
            if tmp_path:
                Path(tmp_path).unlink(missing_ok=True)

    # ── internals ───────────────────────────────────────────

    def _ensure_model(self) -> None:
        """Load the Whisper model if not already loaded."""
        if self._model is not None:
            return

        from faster_whisper import WhisperModel

        logger.info(
            f"Loading faster-whisper model: {self._config.model_size} "
            f"(device={self._config.device}, "
            f"compute_type={self._config.compute_type})"
        )

        self._model = WhisperModel(
            self._config.model_size,
            device=self._config.device,
            compute_type=self._config.compute_type,
        )
        logger.info("Whisper model loaded successfully")
