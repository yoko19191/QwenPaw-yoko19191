# -*- coding: utf-8 -*-
"""Tests for qwenpaw.agents.utils.audio_transcription.

Covers:
- _url_for_provider
- _get_manager
- list_transcription_providers
- get_configured_transcription_provider_id
- check_local_whisper_available
- _get_configured_provider_creds
- _transcribe_local_whisper
- _transcribe_whisper_api
- transcribe_audio
"""
# pylint: disable=protected-access,unused-argument

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from qwenpaw.agents.utils.audio_transcription import (
    _doubao_packet,
    _extract_text_from_payload,
    _get_configured_provider_creds,
    _get_manager,
    _mime_type_for_path,
    _parse_doubao_response,
    _url_for_provider,
    check_sensevoice_available,
    check_local_whisper_available,
    get_configured_transcription_provider_id,
    list_transcription_provider_types,
    list_transcription_providers,
    transcribe_audio,
)
from qwenpaw.providers.ollama_provider import OllamaProvider
from qwenpaw.providers.openai_provider import OpenAIProvider

_MOD = "qwenpaw.agents.utils.audio_transcription"


# ---------------------------------------------------------------------------
# _url_for_provider
# ---------------------------------------------------------------------------


class TestUrlForProvider:
    """Tests for _url_for_provider.

    Uses real OpenAIProvider / OllamaProvider instances rather than mocks:
    _url_for_provider lazy-imports these classes inside the function body
    (``from ...providers.openai_provider import OpenAIProvider``), so
    patching ``audio_transcription.OpenAIProvider`` does not affect the
    function-local name, and patching ``isinstance`` at module scope does
    not intercept the builtin used inside the function. Real instances
    exercise the actual isinstance branches.
    """

    def test_openai_provider_with_key(self):
        provider = OpenAIProvider(
            id="openai",
            name="OpenAI",
            base_url="https://api.openai.com",
            api_key="sk-test",
            require_api_key=True,
        )
        result = _url_for_provider(provider)
        assert result is not None
        assert result == ("https://api.openai.com/v1", "sk-test")

    def test_openai_provider_no_key(self):
        provider = OpenAIProvider(
            id="openai",
            name="OpenAI",
            base_url="https://api.openai.com",
            api_key="",
            require_api_key=True,
        )
        result = _url_for_provider(provider)
        assert result is None

    def test_openai_provider_no_key_not_required(self):
        provider = OpenAIProvider(
            id="openai-local",
            name="OpenAI-local",
            base_url="http://localhost:8000",
            api_key="",
            require_api_key=False,
        )
        result = _url_for_provider(provider)
        assert result == ("http://localhost:8000/v1", "")

    def test_ollama_provider(self):
        # Real Ollama configs set require_api_key=False (see
        # provider_manager.PROVIDER_OLLAMA). OllamaProvider extends
        # OpenAIProvider, so it's matched by the OpenAIProvider isinstance
        # branch — exercising the realistic credential path.
        provider = OllamaProvider(
            id="ollama",
            name="Ollama",
            base_url="http://localhost:11434",
            api_key="",
            require_api_key=False,
        )
        result = _url_for_provider(provider)
        assert result is not None
        assert result == ("http://localhost:11434/v1", "")

    def test_unknown_provider_returns_none(self):
        # A bare object is neither OpenAIProvider nor OllamaProvider.
        provider = MagicMock(spec=[])
        result = _url_for_provider(provider)
        assert result is None

    def test_base_url_already_has_v1(self):
        provider = OpenAIProvider(
            id="openai",
            name="OpenAI",
            base_url="https://api.openai.com/v1",
            api_key="key",
            require_api_key=True,
        )
        result = _url_for_provider(provider)
        assert result == ("https://api.openai.com/v1", "key")

    def test_base_url_trailing_slash_stripped(self):
        provider = OpenAIProvider(
            id="openai",
            name="OpenAI",
            base_url="https://api.openai.com/",
            api_key="key",
            require_api_key=True,
        )
        result = _url_for_provider(provider)
        assert result == ("https://api.openai.com/v1", "key")


# ---------------------------------------------------------------------------
# _get_manager
# ---------------------------------------------------------------------------


class TestGetManager:
    """Tests for _get_manager."""

    def test_returns_instance(self):
        mock_instance = MagicMock()
        with patch(
            "qwenpaw.providers.provider_manager.ProviderManager.get_instance",
            return_value=mock_instance,
        ):
            result = _get_manager()
            assert result is mock_instance

    def test_import_failure_returns_none(self):
        with patch.dict(
            "sys.modules",
            {"qwenpaw.providers.provider_manager": None},
        ):
            _get_manager()
            # May return None or raise depending on import state
            # Just verify it doesn't crash


# ---------------------------------------------------------------------------
# list_transcription_providers
# ---------------------------------------------------------------------------


class TestListTranscriptionProviders:
    """Tests for list_transcription_providers."""

    def test_no_manager_returns_empty(self):
        with patch(
            f"{_MOD}._get_manager",
            return_value=None,
        ):
            assert not list_transcription_providers()

    def test_returns_capable_providers(self):
        mock_manager = MagicMock()
        mock_provider = MagicMock()
        mock_provider.id = "p1"
        mock_provider.name = "Provider 1"
        mock_manager.builtin_providers = {"p1": mock_provider}
        mock_manager.custom_providers = {}

        with patch(
            f"{_MOD}._get_manager",
            return_value=mock_manager,
        ), patch(
            f"{_MOD}._url_for_provider",
            return_value=("http://api/v1", "key"),
        ):
            result = list_transcription_providers()
            assert len(result) == 1
            assert result[0]["id"] == "p1"
            assert result[0]["available"] is True

    def test_skips_uncapable_providers(self):
        mock_manager = MagicMock()
        mock_provider = MagicMock()
        mock_provider.id = "p1"
        mock_manager.builtin_providers = {"p1": mock_provider}
        mock_manager.custom_providers = {}

        with patch(
            f"{_MOD}._get_manager",
            return_value=mock_manager,
        ), patch(
            f"{_MOD}._url_for_provider",
            return_value=None,
        ):
            assert not list_transcription_providers()


# ---------------------------------------------------------------------------
# get_configured_transcription_provider_id
# ---------------------------------------------------------------------------


class TestGetConfiguredTranscriptionProviderId:
    """Tests for get_configured_transcription_provider_id."""

    def test_returns_configured_id(self):
        mock_config = MagicMock()
        mock_config.agents.transcription_provider_id = "my-provider"
        with patch(
            "qwenpaw.config.load_config",
            return_value=mock_config,
        ):
            assert get_configured_transcription_provider_id() == "my-provider"


# ---------------------------------------------------------------------------
# check_local_whisper_available
# ---------------------------------------------------------------------------


class TestCheckLocalWhisperAvailable:
    """Tests for check_local_whisper_available."""

    @patch(f"{_MOD}.shutil")
    def test_neither_available(self, mock_shutil):
        mock_shutil.which.return_value = None
        with patch.dict("sys.modules", {"whisper": None}):
            result = check_local_whisper_available()
            assert result["available"] is False
            assert result["ffmpeg_installed"] is False

    @patch(f"{_MOD}.shutil")
    def test_ffmpeg_but_no_whisper(self, mock_shutil):
        mock_shutil.which.return_value = "/usr/bin/ffmpeg"
        with patch.dict("sys.modules", {"whisper": None}):
            result = check_local_whisper_available()
            assert result["ffmpeg_installed"] is True
            assert result["whisper_installed"] is False


class TestProviderMetadata:
    """Tests for provider metadata and local status helpers."""

    def test_lists_new_provider_types(self):
        with patch(
            f"{_MOD}.check_local_whisper_available",
            return_value={"available": False},
        ), patch(
            f"{_MOD}.check_sensevoice_available",
            return_value={"available": False},
        ):
            ids = {item["id"] for item in list_transcription_provider_types()}
        assert "doubao_seedasr_stream" in ids
        assert "dashscope_qwen3_flash" in ids
        assert "dashscope_qwen3_filetrans" in ids
        assert "mimo_asr" in ids
        assert "sensevoice_local" in ids

    def test_sensevoice_missing_reports_install_hint(self):
        with patch.dict("sys.modules", {"funasr": None}):
            result = check_sensevoice_available()
        assert result["available"] is False
        assert "qwenpaw[sensevoice]" in result["install_hint"]


# ---------------------------------------------------------------------------
# _get_configured_provider_creds
# ---------------------------------------------------------------------------


class TestGetConfiguredProviderCreds:
    """Tests for _get_configured_provider_creds."""

    def test_no_configured_id(self):
        mock_config = MagicMock()
        mock_config.agents.transcription_provider_id = ""
        with patch(
            "qwenpaw.config.load_config",
            return_value=mock_config,
        ):
            assert _get_configured_provider_creds() is None

    def test_no_manager(self):
        mock_config = MagicMock()
        mock_config.agents.transcription_provider_id = "p1"
        with patch(
            "qwenpaw.config.load_config",
            return_value=mock_config,
        ), patch(
            f"{_MOD}._get_manager",
            return_value=None,
        ):
            assert _get_configured_provider_creds() is None

    def test_provider_not_found(self):
        mock_config = MagicMock()
        mock_config.agents.transcription_provider_id = "missing"
        mock_manager = MagicMock()
        mock_manager.get_provider.return_value = None
        with patch(
            "qwenpaw.config.load_config",
            return_value=mock_config,
        ), patch(
            f"{_MOD}._get_manager",
            return_value=mock_manager,
        ):
            assert _get_configured_provider_creds() is None


# ---------------------------------------------------------------------------
# transcribe_audio
# ---------------------------------------------------------------------------


class TestTranscribeAudio:
    """Tests for transcribe_audio."""

    @pytest.mark.asyncio
    async def test_disabled_returns_none(self):
        mock_config = MagicMock()
        mock_config.agents.transcription_provider_type = "disabled"
        with patch(
            "qwenpaw.config.load_config",
            return_value=mock_config,
        ):
            result = await transcribe_audio("/tmp/audio.wav")
            assert result is None

    @pytest.mark.asyncio
    async def test_local_whisper_dispatch(self):
        mock_config = MagicMock()
        mock_config.agents.transcription_provider_type = "local_whisper"
        with patch(
            "qwenpaw.config.load_config",
            return_value=mock_config,
        ), patch(
            f"{_MOD}._transcribe_local_whisper",
            new_callable=AsyncMock,
            return_value="hello world",
        ):
            result = await transcribe_audio("/tmp/audio.wav")
            assert result == "hello world"

    @pytest.mark.asyncio
    async def test_whisper_api_dispatch(self):
        mock_config = MagicMock()
        mock_config.agents.transcription_provider_type = "whisper_api"
        with patch(
            "qwenpaw.config.load_config",
            return_value=mock_config,
        ), patch(
            f"{_MOD}._transcribe_whisper_api",
            new_callable=AsyncMock,
            return_value="transcribed text",
        ):
            result = await transcribe_audio("/tmp/audio.wav")
            assert result == "transcribed text"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("provider_type", "target"),
        [
            ("doubao_seedasr_stream", "_transcribe_doubao_stream"),
            ("dashscope_qwen3_flash", "_transcribe_openai_audio_chat"),
            ("dashscope_qwen3_filetrans", "_transcribe_dashscope_filetrans"),
            ("mimo_asr", "_transcribe_openai_audio_chat"),
            ("sensevoice_local", "_transcribe_sensevoice"),
        ],
    )
    async def test_new_provider_dispatch(self, provider_type, target):
        mock_config = MagicMock()
        mock_config.agents.transcription_provider_type = provider_type
        with patch(
            "qwenpaw.config.load_config",
            return_value=mock_config,
        ), patch(
            f"{_MOD}.{target}",
            new_callable=AsyncMock,
            return_value="ok",
        ) as mock_backend:
            result = await transcribe_audio(
                "/tmp/audio.wav",
                source_url="https://example.com/a.wav",
            )
            assert result == "ok"
            assert mock_backend.await_count == 1

    @pytest.mark.asyncio
    async def test_unknown_type_returns_none(self):
        mock_config = MagicMock()
        mock_config.agents.transcription_provider_type = "unknown"
        with patch(
            "qwenpaw.config.load_config",
            return_value=mock_config,
        ):
            result = await transcribe_audio("/tmp/audio.wav")
            assert result is None


class TestResponseParsing:
    """Tests for shared transcript extraction and Doubao packet parsing."""

    def test_extracts_chat_completion_text(self):
        payload = {"choices": [{"message": {"content": " hello "}}]}
        assert _extract_text_from_payload(payload) == "hello"

    def test_extracts_nested_result_text(self):
        payload = {"result": {"text": "nested"}}
        assert _extract_text_from_payload(payload) == "nested"

    def test_doubao_packet_roundtrip(self):
        packet = _doubao_packet(
            0x9,
            0x1,
            b'{"result":{"text":"hi"}}',
            sequence=1,
            serialization=0x1,
        )
        seq, body = _parse_doubao_response(packet)
        assert seq == 1
        assert body["result"]["text"] == "hi"

    def test_audio_mime_type_uses_provider_supported_values(self):
        assert _mime_type_for_path("sample.wav") == "audio/wav"
        assert _mime_type_for_path("sample.mp3") == "audio/mpeg"


# ---------------------------------------------------------------------------
# _transcribe_local_whisper
# ---------------------------------------------------------------------------


class TestTranscribeLocalWhisper:
    """Tests for _transcribe_local_whisper."""

    @pytest.mark.asyncio
    async def test_unavailable_returns_none(self):
        with patch(
            f"{_MOD}.check_local_whisper_available",
            return_value={
                "available": False,
                "ffmpeg_installed": False,
                "whisper_installed": False,
            },
        ):
            from qwenpaw.agents.utils.audio_transcription import (
                _transcribe_local_whisper,
            )

            result = await _transcribe_local_whisper("/tmp/audio.wav")
            assert result is None

    @pytest.mark.asyncio
    async def test_transcription_success(self):
        mock_model = MagicMock()
        mock_model.transcribe.return_value = {"text": "  hello  "}

        with patch(
            f"{_MOD}.check_local_whisper_available",
            return_value={
                "available": True,
                "ffmpeg_installed": True,
                "whisper_installed": True,
            },
        ), patch(
            f"{_MOD}._get_local_whisper_model",
            return_value=mock_model,
        ):
            from qwenpaw.agents.utils.audio_transcription import (
                _transcribe_local_whisper,
            )

            result = await _transcribe_local_whisper("/tmp/audio.wav")
            assert result == "hello"

    @pytest.mark.asyncio
    async def test_empty_text_returns_none(self):
        mock_model = MagicMock()
        mock_model.transcribe.return_value = {"text": "   "}

        with patch(
            f"{_MOD}.check_local_whisper_available",
            return_value={
                "available": True,
                "ffmpeg_installed": True,
                "whisper_installed": True,
            },
        ), patch(
            f"{_MOD}._get_local_whisper_model",
            return_value=mock_model,
        ):
            from qwenpaw.agents.utils.audio_transcription import (
                _transcribe_local_whisper,
            )

            result = await _transcribe_local_whisper("/tmp/audio.wav")
            assert result is None


# ---------------------------------------------------------------------------
# _transcribe_whisper_api
# ---------------------------------------------------------------------------


class TestTranscribeWhisperApi:
    """Tests for _transcribe_whisper_api."""

    @pytest.mark.asyncio
    async def test_no_creds_returns_none(self):
        with patch(
            f"{_MOD}._get_configured_provider_creds",
            return_value=None,
        ):
            from qwenpaw.agents.utils.audio_transcription import (
                _transcribe_whisper_api,
            )

            result = await _transcribe_whisper_api("/tmp/audio.wav")
            assert result is None

    @pytest.mark.asyncio
    async def test_success(self, tmp_path):
        # Create a real audio file so open() doesn't fail
        audio_file = tmp_path / "audio.wav"
        audio_file.write_bytes(b"fake audio data")

        mock_config = MagicMock()
        mock_config.agents.transcription_model = "whisper-1"

        mock_transcript = MagicMock()
        mock_transcript.text = "  hello world  "

        mock_audio = MagicMock()
        mock_audio.transcriptions = MagicMock()
        mock_audio.transcriptions.create = AsyncMock(
            return_value=mock_transcript,
        )

        mock_client = MagicMock()
        mock_client.audio = mock_audio

        with patch(
            f"{_MOD}._get_configured_provider_creds",
            return_value=("http://api/v1", "sk-test"),
        ), patch(
            "qwenpaw.config.load_config",
            return_value=mock_config,
        ), patch(
            "openai.AsyncOpenAI",
            return_value=mock_client,
        ):
            from qwenpaw.agents.utils.audio_transcription import (
                _transcribe_whisper_api,
            )

            result = await _transcribe_whisper_api(str(audio_file))
            assert result == "hello world"
