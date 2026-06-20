# -*- coding: utf-8 -*-
"""Audio transcription utilities.

The public entry point is :func:`transcribe_audio`, which accepts a local
audio file path and dispatches to the configured ASR backend. Existing
Whisper API and local Whisper behavior is kept, while newer online and local
providers live behind the same file-based interface.
"""

from __future__ import annotations

import asyncio
import base64
import gzip
import inspect
import json
import logging
import mimetypes
import os
import shutil
import struct
import subprocess
import tempfile
import threading
import time
import uuid
import wave
from contextvars import ContextVar
from pathlib import Path
from typing import Any, List, Optional, Tuple

import httpx

logger = logging.getLogger(__name__)

ASR_SECRET_FIELDS = frozenset({"api_key", "access_key"})
_provider_config_override: ContextVar[Optional[dict[str, dict[str, Any]]]] = (
    ContextVar("provider_config_override", default=None)
)

SUPPORTED_TRANSCRIPTION_PROVIDER_TYPES = {
    "disabled",
    "whisper_api",
    "local_whisper",
    "doubao_seedasr_stream",
    "dashscope_qwen3_flash",
    "dashscope_qwen3_filetrans",
    "mimo_asr",
    "sensevoice_local",
}

REMOTE_ASR_PROVIDER_DEFAULTS: dict[str, dict[str, Any]] = {
    "doubao_seedasr_stream": {
        "name": "Doubao Streaming ASR 2.0",
        "model": "bigmodel",
        "base_url": (
            "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async"
        ),
        "api_key_env": "DOUBAO_AUDIO_API_KEY",
        "resource_id": "volc.seedasr.sauc.duration",
    },
    "dashscope_qwen3_flash": {
        "name": "DashScope Qwen3 ASR Flash",
        "model": "qwen3-asr-flash",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "api_key_env": "DASHSCOPE_API_KEY",
    },
    "dashscope_qwen3_filetrans": {
        "name": "DashScope Qwen3 ASR FileTrans",
        "model": "qwen3-asr-flash-filetrans",
        "base_url": (
            "https://dashscope.aliyuncs.com/api/v1/services/audio/asr/"
            "transcription"
        ),
        "api_key_env": "DASHSCOPE_API_KEY",
    },
    "mimo_asr": {
        "name": "MiMo V2.5 ASR",
        "model": "mimo-v2.5-asr",
        "base_url": "https://api.xiaomimimo.com/v1",
        "api_key_env": "MIMO_API_KEY",
    },
}

PROVIDER_TYPE_METADATA: list[dict[str, Any]] = [
    {
        "id": "disabled",
        "name": "Disabled",
        "local": False,
        "requires_key": False,
        "description": "Do not transcribe audio.",
    },
    {
        "id": "whisper_api",
        "name": "Whisper API",
        "local": False,
        "requires_key": False,
        "description": "OpenAI-compatible /v1/audio/transcriptions.",
    },
    {
        "id": "local_whisper",
        "name": "Local Whisper",
        "local": True,
        "requires_key": False,
        "description": "Local openai-whisper package.",
    },
    {
        "id": "doubao_seedasr_stream",
        "name": "Doubao Streaming ASR 2.0",
        "local": False,
        "requires_key": True,
        "description": "Volcengine SeedASR streaming WebSocket backend.",
    },
    {
        "id": "dashscope_qwen3_flash",
        "name": "Qwen3 ASR Flash",
        "local": False,
        "requires_key": True,
        "description": "DashScope short-audio OpenAI-compatible backend.",
    },
    {
        "id": "dashscope_qwen3_filetrans",
        "name": "Qwen3 ASR FileTrans",
        "local": False,
        "requires_key": True,
        "description": "DashScope async file transcription for public URLs.",
    },
    {
        "id": "mimo_asr",
        "name": "MiMo V2.5 ASR",
        "local": False,
        "requires_key": True,
        "description": "Xiaomi MiMo V2.5 ASR OpenAI-compatible backend.",
    },
    {
        "id": "sensevoice_local",
        "name": "SenseVoiceSmall",
        "local": True,
        "requires_key": False,
        "description": "Local SenseVoiceSmall via FunASR.",
    },
]


# ------------------------------------------------------------------
# Cached local model singletons
# ------------------------------------------------------------------

_local_whisper_model = None
_local_whisper_lock = threading.Lock()
_sensevoice_model = None
_sensevoice_model_key = ""
_sensevoice_lock = threading.Lock()


def _get_local_whisper_model():
    """Return a cached whisper model, loading it on first call."""
    global _local_whisper_model  # noqa: PLW0603
    if _local_whisper_model is not None:
        return _local_whisper_model
    with _local_whisper_lock:
        if _local_whisper_model is not None:
            return _local_whisper_model
        import whisper

        _local_whisper_model = whisper.load_model("base")
        return _local_whisper_model


def _get_sensevoice_model(model_name: str, device: str = "cpu"):
    """Return a cached SenseVoice/FunASR model."""
    global _sensevoice_model, _sensevoice_model_key  # noqa: PLW0603
    cache_key = f"{model_name}|{device}"
    if _sensevoice_model is not None and _sensevoice_model_key == cache_key:
        return _sensevoice_model
    with _sensevoice_lock:
        if (
            _sensevoice_model is not None
            and _sensevoice_model_key == cache_key
        ):
            return _sensevoice_model
        from funasr import AutoModel

        _sensevoice_model = AutoModel(
            model=model_name,
            vad_model="fsmn-vad",
            device=device,
        )
        _sensevoice_model_key = cache_key
        return _sensevoice_model


# ------------------------------------------------------------------
# Provider helpers
# ------------------------------------------------------------------


def _url_for_provider(provider) -> Optional[Tuple[str, str]]:
    """Return ``(base_url, api_key)`` if *provider* can serve transcription.

    Supports providers that do not require an API key (e.g. local Ollama).
    """
    from ...providers.openai_provider import OpenAIProvider
    from ...providers.ollama_provider import OllamaProvider

    if isinstance(provider, OpenAIProvider):
        requires_key = getattr(provider, "require_api_key", True)
        key = provider.api_key or ""
        if requires_key and not key:
            return None
        base = provider.base_url.rstrip("/")
        if not base.endswith("/v1"):
            base += "/v1"
        return (base, key or "")
    if isinstance(provider, OllamaProvider):
        base = provider.base_url.rstrip("/")
        if not base.endswith("/v1"):
            base += "/v1"
        return (base, provider.api_key or "")
    return None


def _get_manager():
    """Return ProviderManager singleton or None."""
    try:
        from ...providers.provider_manager import ProviderManager

        return ProviderManager.get_instance()
    except Exception:
        logger.debug("ProviderManager not initialised yet")
        return None


def _validate_provider_type(provider_type: str) -> str:
    provider_type = (provider_type or "").strip().lower()
    if provider_type not in SUPPORTED_TRANSCRIPTION_PROVIDER_TYPES:
        raise ValueError(f"Invalid transcription provider type: {provider_type}")
    return provider_type


def _default_for(provider_type: str, field: str, fallback: str = "") -> str:
    value = REMOTE_ASR_PROVIDER_DEFAULTS.get(provider_type, {}).get(field)
    return str(value or fallback)


def _get_raw_provider_config(provider_type: str):
    from ...config import load_config
    from ...config.config import TranscriptionProviderConfig

    config = load_config()
    stored = config.agents.transcription_provider_configs.get(provider_type)
    if stored is None:
        return TranscriptionProviderConfig()
    return stored


def _secret_value(value: str) -> str:
    if not value:
        return ""
    from ...security.secret_store import decrypt

    return decrypt(value)


def _effective_provider_config(provider_type: str) -> dict[str, Any]:
    """Return provider config with defaults applied and secrets decrypted."""
    provider_type = _validate_provider_type(provider_type)
    overrides = _provider_config_override.get()
    if overrides and provider_type in overrides:
        return dict(overrides[provider_type])

    raw = _get_raw_provider_config(provider_type)
    data = raw.model_dump(mode="json")
    data["api_key"] = _secret_value(data.get("api_key", ""))
    data["access_key"] = _secret_value(data.get("access_key", ""))

    for field in ("model", "base_url", "api_key_env", "resource_id"):
        if not data.get(field):
            data[field] = _default_for(provider_type, field)
    if not data.get("language"):
        data["language"] = "auto"

    env_name = data.get("api_key_env") or _default_for(
        provider_type,
        "api_key_env",
    )
    if not data.get("api_key") and env_name:
        data["api_key"] = os.environ.get(env_name, "")
    if not data.get("access_key") and data.get("extra", {}).get(
        "access_key_env",
    ):
        data["access_key"] = os.environ.get(
            str(data["extra"]["access_key_env"]),
            "",
        )
    return data


def get_sanitized_provider_config(provider_type: str) -> dict[str, Any]:
    """Return provider config without exposing stored secret values."""
    raw = _get_raw_provider_config(provider_type)
    data = raw.model_dump(mode="json")
    data["model"] = data.get("model") or _default_for(provider_type, "model")
    data["base_url"] = data.get("base_url") or _default_for(
        provider_type,
        "base_url",
    )
    data["api_key_env"] = data.get("api_key_env") or _default_for(
        provider_type,
        "api_key_env",
    )
    data["resource_id"] = data.get("resource_id") or _default_for(
        provider_type,
        "resource_id",
    )
    data["api_key_configured"] = bool(
        raw.api_key
        or os.environ.get(data.get("api_key_env") or ""),
    )
    data["access_key_configured"] = bool(raw.access_key)
    data.pop("api_key", None)
    data.pop("access_key", None)
    return data


def list_transcription_provider_types() -> list[dict[str, Any]]:
    """Return supported transcription backend metadata for the UI."""
    items: list[dict[str, Any]] = []
    for item in PROVIDER_TYPE_METADATA:
        entry = dict(item)
        provider_type = entry["id"]
        if provider_type == "local_whisper":
            entry["status"] = check_local_whisper_available()
        elif provider_type == "sensevoice_local":
            entry["status"] = check_sensevoice_available()
        elif provider_type in REMOTE_ASR_PROVIDER_DEFAULTS:
            cfg = get_sanitized_provider_config(provider_type)
            entry["default_model"] = cfg.get("model")
            entry["default_env"] = cfg.get("api_key_env")
            entry["available"] = bool(cfg.get("api_key_configured"))
        else:
            entry["available"] = True
        items.append(entry)
    return items


# ------------------------------------------------------------------
# Public helpers for API / Console UI
# ------------------------------------------------------------------


def list_transcription_providers() -> List[dict]:
    """Return providers capable of Whisper API transcription.

    Each entry is ``{"id": ..., "name": ..., "available": bool}``.
    Availability is based on whether the provider has usable credentials.
    This helper is kept for compatibility with the existing Whisper UI/API.
    """
    manager = _get_manager()
    if manager is None:
        return []

    results: list[dict] = []
    all_providers = {
        **getattr(manager, "builtin_providers", {}),
        **getattr(manager, "custom_providers", {}),
    }
    for provider in all_providers.values():
        creds = _url_for_provider(provider)
        if creds is not None:
            results.append(
                {
                    "id": provider.id,
                    "name": provider.name,
                    "available": True,
                },
            )
    return results


def get_configured_transcription_provider_id() -> str:
    """Return the explicitly configured provider ID (raw config value)."""
    from ...config import load_config

    return load_config().agents.transcription_provider_id


def check_local_whisper_available() -> dict:
    """Check whether the local whisper provider can be used."""
    ffmpeg_ok = shutil.which("ffmpeg") is not None

    whisper_ok = False
    try:
        import whisper as _whisper  # noqa: F401

        whisper_ok = True
    except ImportError:
        pass

    return {
        "available": ffmpeg_ok and whisper_ok,
        "ffmpeg_installed": ffmpeg_ok,
        "whisper_installed": whisper_ok,
    }


def check_sensevoice_available() -> dict:
    """Check whether local SenseVoice/FunASR can be used."""
    funasr_ok = False
    try:
        import funasr as _funasr  # noqa: F401

        funasr_ok = True
    except ImportError:
        pass

    return {
        "available": funasr_ok,
        "funasr_installed": funasr_ok,
        "install_hint": 'pip install "qwenpaw[sensevoice]"',
    }


def get_local_asr_status() -> dict:
    """Return all local ASR dependency checks."""
    return {
        "local_whisper": check_local_whisper_available(),
        "sensevoice": check_sensevoice_available(),
    }


def build_transcription_settings_response() -> dict[str, Any]:
    """Return the complete, sanitized ASR settings payload."""
    from ...config import load_config

    config = load_config()
    return {
        "audio_mode": config.agents.audio_mode,
        "transcription_provider_type": (
            config.agents.transcription_provider_type
        ),
        "transcription_provider_id": config.agents.transcription_provider_id,
        "transcription_model": config.agents.transcription_model,
        "provider_types": list_transcription_provider_types(),
        "provider_configs": {
            provider_type: get_sanitized_provider_config(provider_type)
            for provider_type in SUPPORTED_TRANSCRIPTION_PROVIDER_TYPES
            if provider_type != "disabled"
        },
        "whisper_api_providers": list_transcription_providers(),
        "local_status": get_local_asr_status(),
    }


# ------------------------------------------------------------------
# Audio preparation
# ------------------------------------------------------------------


def _mime_type_for_path(file_path: str) -> str:
    explicit = {
        ".amr": "audio/amr",
        ".flac": "audio/flac",
        ".m4a": "audio/mp4",
        ".mp3": "audio/mpeg",
        ".ogg": "audio/ogg",
        ".oga": "audio/ogg",
        ".wav": "audio/wav",
        ".wave": "audio/wav",
        ".webm": "audio/webm",
    }
    ext = Path(file_path).suffix.lower()
    if ext in explicit:
        return explicit[ext]
    mime, _encoding = mimetypes.guess_type(file_path)
    if mime == "audio/x-wav":
        return "audio/wav"
    return mime or "audio/wav"


def _audio_data_url(file_path: str) -> str:
    with open(file_path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode("ascii")
    return f"data:{_mime_type_for_path(file_path)};base64,{encoded}"


def _convert_with_ffmpeg(src_path: str, suffix: str, args: list[str]) -> str:
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg is required for audio conversion")
    fd, dst_path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-loglevel",
                "error",
                "-i",
                src_path,
                *args,
                dst_path,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=60,
            check=True,
        )
        return dst_path
    except Exception:
        try:
            os.unlink(dst_path)
        except OSError:
            pass
        raise


def _prepare_for_data_url(
    file_path: str,
    allowed_exts: set[str],
) -> tuple[str, bool]:
    ext = Path(file_path).suffix.lower()
    if ext in allowed_exts:
        return file_path, False
    converted = _convert_with_ffmpeg(
        file_path,
        ".wav",
        ["-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1"],
    )
    return converted, True


def _prepare_pcm16(file_path: str) -> tuple[str, bool]:
    converted = _convert_with_ffmpeg(
        file_path,
        ".pcm",
        ["-f", "s16le", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1"],
    )
    return converted, True


def _iter_file_chunks(file_path: str, chunk_size: int):
    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            yield chunk


def _cleanup_temp(path: str, should_cleanup: bool) -> None:
    if not should_cleanup:
        return
    try:
        os.unlink(path)
    except OSError:
        pass


def _create_test_wav() -> str:
    """Create a short WAV file for manual provider connectivity tests."""
    fd, wav_path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)

    if shutil.which("say") and shutil.which("ffmpeg"):
        aiff_fd, aiff_path = tempfile.mkstemp(suffix=".aiff")
        os.close(aiff_fd)
        try:
            subprocess.run(
                ["say", "-o", aiff_path, "hello qwen paw"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
                check=True,
            )
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-loglevel",
                    "error",
                    "-i",
                    aiff_path,
                    "-acodec",
                    "pcm_s16le",
                    "-ar",
                    "16000",
                    "-ac",
                    "1",
                    wav_path,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=15,
                check=True,
            )
            return wav_path
        except Exception:
            pass
        finally:
            try:
                os.unlink(aiff_path)
            except OSError:
                pass

    with wave.open(wav_path, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\x00\x00" * 16000)
    return wav_path


# ------------------------------------------------------------------
# Transcription backends
# ------------------------------------------------------------------


async def _transcribe_local_whisper(file_path: str) -> Optional[str]:
    """Transcribe using the locally installed ``openai-whisper`` library."""
    status = check_local_whisper_available()
    if not status["available"]:
        missing = []
        if not status["ffmpeg_installed"]:
            missing.append("ffmpeg")
        if not status["whisper_installed"]:
            missing.append("openai-whisper")
        logger.warning(
            "Local Whisper unavailable (missing: %s).",
            ", ".join(missing),
        )
        return None

    def _run():
        model = _get_local_whisper_model()
        result = model.transcribe(file_path)
        return (result.get("text") or "").strip()

    try:
        text = await asyncio.to_thread(_run)
        if text:
            logger.debug("Local Whisper transcribed %s: %s", file_path, text[:80])
            return text
        logger.warning("Local Whisper returned empty text for %s", file_path)
        return None
    except Exception:
        logger.warning(
            "Local Whisper transcription failed for %s",
            file_path,
            exc_info=True,
        )
        return None


async def _transcribe_sensevoice(file_path: str) -> Optional[str]:
    cfg = _effective_provider_config("sensevoice_local")
    status = check_sensevoice_available()
    if not status["available"]:
        logger.warning(
            "SenseVoice unavailable. Install with: %s",
            status["install_hint"],
        )
        return None

    model_name = cfg.get("model") or "iic/SenseVoiceSmall"
    device = str(cfg.get("extra", {}).get("device") or "cpu")
    language = cfg.get("language") or "auto"

    def _run():
        model = _get_sensevoice_model(model_name, device=device)
        result = model.generate(
            input=file_path,
            language=language,
            use_itn=True,
            batch_size_s=60,
        )
        text = _extract_text_from_payload(result)
        try:
            from funasr.utils.postprocess_utils import (
                rich_transcription_postprocess,
            )

            text = rich_transcription_postprocess(text)
        except Exception:
            pass
        return text.strip()

    try:
        text = await asyncio.to_thread(_run)
        return text or None
    except Exception:
        logger.warning(
            "SenseVoice transcription failed for %s",
            file_path,
            exc_info=True,
        )
        return None


def _get_configured_provider_creds() -> Optional[Tuple[str, str]]:
    """Return ``(base_url, api_key)`` for the configured Whisper provider."""
    from ...config import load_config

    configured_id = load_config().agents.transcription_provider_id
    if not configured_id:
        return None

    manager = _get_manager()
    if manager is None:
        return None

    provider = manager.get_provider(configured_id)
    if provider is None:
        logger.warning(
            "Configured transcription provider '%s' not found",
            configured_id,
        )
        return None

    creds = _url_for_provider(provider)
    if creds is None:
        logger.warning(
            "Configured transcription provider '%s' has no usable credentials",
            configured_id,
        )
    return creds


async def _transcribe_whisper_api(file_path: str) -> Optional[str]:
    """Transcribe using an OpenAI-compatible Whisper endpoint."""
    creds = _get_configured_provider_creds()
    if creds is None:
        logger.warning("No transcription provider configured")
        return None

    base_url, api_key = creds

    try:
        from openai import AsyncOpenAI
    except ImportError:
        logger.warning("openai package not installed")
        return None

    from ...config import load_config

    model_name = load_config().agents.transcription_model or "whisper-1"

    client = AsyncOpenAI(
        base_url=base_url,
        api_key=api_key or "none",
        timeout=60,
    )

    try:
        with open(file_path, "rb") as f:
            transcript = await client.audio.transcriptions.create(
                model=model_name,
                file=f,
            )
        text = transcript.text.strip()
        if text:
            logger.debug("Transcribed audio %s: %s", file_path, text[:80])
            return text
        logger.warning("Transcription returned empty text for %s", file_path)
        return None
    except Exception:
        logger.warning(
            "Audio transcription failed for %s",
            file_path,
            exc_info=True,
        )
        return None


async def _transcribe_openai_audio_chat(
    file_path: str,
    provider_type: str,
) -> Optional[str]:
    """Transcribe through an OpenAI-compatible chat/completions ASR API."""
    try:
        from openai import AsyncOpenAI
    except ImportError:
        logger.warning("openai package not installed")
        return None

    cfg = _effective_provider_config(provider_type)
    api_key = cfg.get("api_key") or ""
    if not api_key:
        logger.warning("%s API key is not configured", provider_type)
        return None

    allowed = {".wav", ".mp3"}
    if provider_type == "dashscope_qwen3_flash":
        allowed = {".wav", ".mp3", ".m4a", ".ogg", ".flac", ".webm", ".amr"}

    prepared_path = file_path
    cleanup = False
    try:
        prepared_path, cleanup = _prepare_for_data_url(file_path, allowed)
        data_url = _audio_data_url(prepared_path)
        if len(data_url.encode("utf-8")) > 10 * 1024 * 1024:
            logger.warning("%s audio data URL exceeds 10 MB", provider_type)
            return None

        client = AsyncOpenAI(
            api_key=api_key,
            base_url=cfg["base_url"],
            timeout=cfg.get("timeout_seconds") or 60,
        )
        extra_body = None
        if provider_type == "mimo_asr":
            extra_body = {
                "asr_options": {"language": cfg.get("language") or "auto"},
            }

        response = await client.chat.completions.create(
            model=cfg["model"],
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_audio",
                            "input_audio": {"data": data_url},
                        },
                    ],
                },
            ],
            stream=False,
            extra_body=extra_body,
        )
        return _extract_text_from_payload(response.model_dump()).strip() or None
    except Exception:
        logger.warning(
            "%s transcription failed for %s",
            provider_type,
            file_path,
            exc_info=True,
        )
        return None
    finally:
        _cleanup_temp(prepared_path, cleanup)


async def _transcribe_dashscope_filetrans(
    source_url: Optional[str],
) -> Optional[str]:
    """Transcribe a public audio URL through DashScope async filetrans."""
    if not source_url or not source_url.startswith(("http://", "https://")):
        logger.warning(
            "qwen3-asr-flash-filetrans requires a public http(s) source_url",
        )
        return None

    cfg = _effective_provider_config("dashscope_qwen3_filetrans")
    api_key = cfg.get("api_key") or ""
    if not api_key:
        logger.warning("DashScope API key is not configured")
        return None

    submit_url = cfg["base_url"]
    task_url_base = "https://dashscope.aliyuncs.com/api/v1/tasks"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "X-DashScope-Async": "enable",
    }
    payload = {
        "model": cfg["model"],
        "input": {"file_url": source_url},
    }
    timeout = httpx.Timeout(float(cfg.get("timeout_seconds") or 60))

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            submit = await client.post(
                submit_url,
                headers=headers,
                json=payload,
            )
            submit.raise_for_status()
            submit_body = submit.json()
            task_id = (
                submit_body.get("output", {}).get("task_id")
                or submit_body.get("task_id")
            )
            if not task_id:
                logger.warning("DashScope filetrans response missing task_id")
                return None

            deadline = time.monotonic() + float(
                cfg.get("timeout_seconds") or 60,
            )
            last_body: dict[str, Any] = {}
            while time.monotonic() < deadline:
                await asyncio.sleep(1.5)
                query = await client.get(
                    f"{task_url_base}/{task_id}",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                query.raise_for_status()
                last_body = query.json()
                status = (
                    last_body.get("output", {}).get("task_status")
                    or last_body.get("task_status")
                    or ""
                )
                if str(status).upper() == "SUCCEEDED":
                    result_url = (
                        last_body.get("output", {})
                        .get("result", {})
                        .get("transcription_url")
                        or last_body.get("output", {}).get("transcription_url")
                    )
                    if not result_url:
                        return _extract_text_from_payload(last_body) or None
                    result = await client.get(result_url)
                    result.raise_for_status()
                    return (
                        _extract_text_from_payload(result.json()).strip()
                        or None
                    )
                if str(status).upper() in {"FAILED", "CANCELED"}:
                    logger.warning("DashScope filetrans failed: %s", last_body)
                    return None
            logger.warning("DashScope filetrans task timed out: %s", task_id)
            return None
    except Exception:
        logger.warning(
            "DashScope filetrans failed for %s",
            source_url,
            exc_info=True,
        )
        return None


def _doubao_header(message_type: int, flags: int, serialization: int = 0) -> bytes:
    return bytes(
        [
            0x11,
            (message_type << 4) | flags,
            (serialization << 4) | 0x01,
            0x00,
        ],
    )


def _doubao_packet(
    message_type: int,
    flags: int,
    payload: bytes,
    *,
    sequence: Optional[int] = None,
    serialization: int = 0,
) -> bytes:
    compressed = gzip.compress(payload)
    parts = [_doubao_header(message_type, flags, serialization)]
    if sequence is not None:
        parts.append(struct.pack(">i", sequence))
    parts.append(struct.pack(">I", len(compressed)))
    parts.append(compressed)
    return b"".join(parts)


def _doubao_full_request(cfg: dict[str, Any]) -> bytes:
    request = {
        "user": {"uid": "qwenpaw"},
        "audio": {
            "format": "pcm",
            "codec": "raw",
            "rate": 16000,
            "bits": 16,
            "channel": 1,
        },
        "request": {
            "model_name": cfg.get("model") or "bigmodel",
            "enable_itn": True,
            "enable_punc": True,
            "enable_nonstream": True,
            "show_utterances": True,
        },
    }
    return _doubao_packet(
        0x1,
        0x0,
        json.dumps(request).encode("utf-8"),
        serialization=0x1,
    )


def _parse_doubao_response(data: bytes) -> tuple[Optional[int], dict[str, Any]]:
    if len(data) < 8:
        return None, {}
    header_size = (data[0] & 0x0F) * 4
    message_type = data[1] >> 4
    flags = data[1] & 0x0F
    compression = data[2] & 0x0F
    offset = header_size
    sequence: Optional[int] = None

    if message_type == 0xF:
        if len(data) < offset + 8:
            return None, {}
        error_code = struct.unpack(">i", data[offset : offset + 4])[0]
        offset += 4
        size = struct.unpack(">I", data[offset : offset + 4])[0]
        offset += 4
        payload = data[offset : offset + size]
        if compression == 0x1:
            payload = gzip.decompress(payload)
        try:
            body = json.loads(payload.decode("utf-8"))
        except Exception:
            body = {"message": payload.decode("utf-8", errors="replace")}
        body["error_code"] = error_code
        return None, body

    if flags in {0x1, 0x3} or message_type == 0x9:
        if len(data) < offset + 4:
            return None, {}
        sequence = struct.unpack(">i", data[offset : offset + 4])[0]
        offset += 4
    if len(data) < offset + 4:
        return sequence, {}
    size = struct.unpack(">I", data[offset : offset + 4])[0]
    offset += 4
    payload = data[offset : offset + size]
    if compression == 0x1:
        payload = gzip.decompress(payload)
    try:
        return sequence, json.loads(payload.decode("utf-8"))
    except Exception:
        return sequence, {}


async def _connect_websocket(
    url: str,
    headers: dict[str, str],
    *,
    open_timeout: float = 10.0,
):
    import websockets

    kwargs: dict[str, Any] = {
        "open_timeout": open_timeout,
        "ping_interval": 20,
        "close_timeout": 5,
        "max_size": 8 * 1024 * 1024,
    }
    params = inspect.signature(websockets.connect).parameters
    if "proxy" in params:
        kwargs["proxy"] = None
    if "additional_headers" in params:
        kwargs["additional_headers"] = headers
    else:
        kwargs["extra_headers"] = headers
    return websockets.connect(url, **kwargs)


async def _drain_doubao_responses(ws, timeout: float) -> list[dict[str, Any]]:
    bodies: list[dict[str, Any]] = []
    while True:
        try:
            message = await asyncio.wait_for(ws.recv(), timeout=timeout)
        except asyncio.TimeoutError:
            break
        except Exception as exc:
            if exc.__class__.__name__.startswith("ConnectionClosed"):
                logger.debug("Doubao websocket closed while draining")
                break
            raise
        if isinstance(message, str):
            continue
        sequence, body = _parse_doubao_response(message)
        if body:
            bodies.append(body)
        if sequence is not None and sequence < 0:
            break
        timeout = 0.05
    return bodies


async def _transcribe_doubao_stream(file_path: str) -> Optional[str]:
    cfg = _effective_provider_config("doubao_seedasr_stream")
    api_key = cfg.get("api_key") or ""
    if not api_key and not (cfg.get("app_key") and cfg.get("access_key")):
        logger.warning("Doubao ASR API key is not configured")
        return None

    prepared_path = file_path
    cleanup = False
    try:
        prepared_path, cleanup = _prepare_pcm16(file_path)
        request_id = str(uuid.uuid4())
        headers = {
            "X-Api-Resource-Id": cfg.get("resource_id")
            or "volc.seedasr.sauc.duration",
            "X-Api-Request-Id": request_id,
            "X-Api-Connect-Id": request_id,
            "X-Api-Sequence": "-1",
        }
        if api_key:
            headers["X-Api-Key"] = api_key
        else:
            headers["X-Api-App-Key"] = str(cfg.get("app_key") or "")
            headers["X-Api-Access-Key"] = str(cfg.get("access_key") or "")

        connect = await _connect_websocket(
            cfg["base_url"],
            headers,
            open_timeout=min(float(cfg.get("timeout_seconds") or 60), 30.0),
        )
        async with connect as ws:
            await ws.send(_doubao_full_request(cfg))
            bodies: list[dict[str, Any]] = []
            chunks = list(_iter_file_chunks(prepared_path, 6400))
            if not chunks:
                chunks = [b""]
            for index, chunk in enumerate(chunks, start=1):
                is_last = index == len(chunks)
                await ws.send(
                    _doubao_packet(
                        0x2,
                        0x2 if is_last else 0x0,
                        chunk,
                        serialization=0x0,
                    ),
                )
                bodies.extend(await _drain_doubao_responses(ws, 0.05))
                if any(body.get("error_code") is not None for body in bodies):
                    break
            bodies.extend(
                await _drain_doubao_responses(
                    ws,
                    min(float(cfg.get("timeout_seconds") or 60), 30.0),
                ),
            )

        for body in bodies:
            if body.get("error_code") is not None:
                logger.warning("Doubao ASR returned error: %s", body)
                return None

        last_text = ""
        for body in bodies:
            text = _extract_text_from_payload(body)
            if text:
                last_text = text
        return last_text.strip() or None
    except Exception:
        logger.warning(
            "Doubao streaming transcription failed for %s",
            file_path,
            exc_info=True,
        )
        return None
    finally:
        _cleanup_temp(prepared_path, cleanup)


# ------------------------------------------------------------------
# Text extraction
# ------------------------------------------------------------------


def _extract_text_from_payload(payload: Any) -> str:
    """Best-effort transcript extraction across ASR response shapes."""
    if payload is None:
        return ""
    if isinstance(payload, str):
        return payload
    if isinstance(payload, list):
        parts = [_extract_text_from_payload(item) for item in payload]
        return "\n".join(part for part in parts if part).strip()
    if not isinstance(payload, dict):
        return ""

    choices = payload.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            message = first.get("message") or {}
            content = message.get("content") if isinstance(message, dict) else None
            if isinstance(content, str):
                return content.strip()

    for key in ("text", "transcript", "sentence", "content"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    result = payload.get("result")
    if isinstance(result, dict):
        text = _extract_text_from_payload(result)
        if text:
            return text
        utterances = result.get("utterances")
        if isinstance(utterances, list):
            parts = [
                str(item.get("text", "")).strip()
                for item in utterances
                if isinstance(item, dict) and item.get("text")
            ]
            if parts:
                return "".join(parts).strip()
    elif isinstance(result, list):
        text = _extract_text_from_payload(result)
        if text:
            return text

    output = payload.get("output")
    if isinstance(output, dict):
        text = _extract_text_from_payload(output)
        if text:
            return text

    for key in ("transcripts", "sentences", "utterances"):
        value = payload.get(key)
        if isinstance(value, list):
            text = _extract_text_from_payload(value)
            if text:
                return text
    return ""


# ------------------------------------------------------------------
# Config update and connectivity helpers
# ------------------------------------------------------------------


def _copy_config_with_overrides(
    provider_type: str,
    provider_config: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    cfg = _effective_provider_config(provider_type)
    if provider_config:
        for key, value in provider_config.items():
            if value is None:
                continue
            if key in ASR_SECRET_FIELDS:
                cfg[key] = str(value)
            elif key == "extra" and isinstance(value, dict):
                merged = dict(cfg.get("extra") or {})
                merged.update(value)
                cfg["extra"] = merged
            else:
                cfg[key] = value
    return cfg


async def test_transcription_connection(
    provider_type: Optional[str] = None,
    provider_config: Optional[dict[str, Any]] = None,
    *,
    file_path: Optional[str] = None,
    source_url: Optional[str] = None,
) -> dict[str, Any]:
    """Run a provider connectivity test and return a UI-friendly result."""
    from ...config import load_config

    active_type = provider_type or load_config().agents.transcription_provider_type
    active_type = _validate_provider_type(active_type)

    if active_type == "disabled":
        return {
            "success": False,
            "message": "Transcription is disabled.",
        }
    if active_type == "local_whisper":
        status = check_local_whisper_available()
        return {
            "success": bool(status["available"]),
            "message": (
                "Local Whisper is available."
                if status["available"]
                else "Local Whisper dependencies are missing."
            ),
            "status": status,
        }
    if active_type == "sensevoice_local":
        status = check_sensevoice_available()
        return {
            "success": bool(status["available"]),
            "message": (
                "SenseVoice dependencies are available."
                if status["available"]
                else status["install_hint"]
            ),
            "status": status,
        }

    cfg = _copy_config_with_overrides(active_type, provider_config)
    if active_type in REMOTE_ASR_PROVIDER_DEFAULTS and not cfg.get("api_key"):
        env_name = cfg.get("api_key_env") or _default_for(
            active_type,
            "api_key_env",
        )
        return {
            "success": False,
            "message": f"API key is not configured. Set {env_name} or save one.",
        }

    tmp_path = file_path
    owns_tmp = False
    if tmp_path is None:
        tmp_path = _create_test_wav()
        owns_tmp = True

    start = time.perf_counter()
    token = _provider_config_override.set({active_type: cfg})
    try:
        text = await _transcribe_with_provider(
            active_type,
            tmp_path,
            source_url=source_url,
        )
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        if text:
            return {
                "success": True,
                "message": "Transcription provider is reachable.",
                "latency_ms": elapsed_ms,
                "text": text[:200],
            }
        return {
            "success": False,
            "message": "Provider was reached but returned no transcript.",
            "latency_ms": elapsed_ms,
        }
    except Exception as exc:
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        return {
            "success": False,
            "message": str(exc),
            "latency_ms": elapsed_ms,
        }
    finally:
        _provider_config_override.reset(token)
        if owns_tmp and tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


async def _transcribe_with_provider(
    provider_type: str,
    file_path: str,
    *,
    source_url: Optional[str] = None,
) -> Optional[str]:
    if provider_type == "local_whisper":
        return await _transcribe_local_whisper(file_path)
    if provider_type == "whisper_api":
        return await _transcribe_whisper_api(file_path)
    if provider_type == "doubao_seedasr_stream":
        return await _transcribe_doubao_stream(file_path)
    if provider_type == "dashscope_qwen3_flash":
        return await _transcribe_openai_audio_chat(
            file_path,
            "dashscope_qwen3_flash",
        )
    if provider_type == "dashscope_qwen3_filetrans":
        return await _transcribe_dashscope_filetrans(source_url)
    if provider_type == "mimo_asr":
        return await _transcribe_openai_audio_chat(file_path, "mimo_asr")
    if provider_type == "sensevoice_local":
        return await _transcribe_sensevoice(file_path)
    return None


# ------------------------------------------------------------------
# Public entry point
# ------------------------------------------------------------------


async def transcribe_audio(
    file_path: str,
    *,
    source_url: Optional[str] = None,
) -> Optional[str]:
    """Transcribe an audio file to text using the configured backend."""
    from ...config import load_config

    provider_type = load_config().agents.transcription_provider_type

    if provider_type == "disabled":
        logger.debug("Transcription is disabled; skipping")
        return None
    if provider_type not in SUPPORTED_TRANSCRIPTION_PROVIDER_TYPES:
        logger.warning("Unknown transcription_provider_type: %s", provider_type)
        return None
    return await _transcribe_with_provider(
        provider_type,
        file_path,
        source_url=source_url,
    )
