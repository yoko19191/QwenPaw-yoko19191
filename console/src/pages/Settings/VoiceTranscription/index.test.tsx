import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { renderWithProviders } from "@/test/common_setup";
import VoiceTranscriptionPage from "./index";

const apiMocks = vi.hoisted(() => ({
  getTranscriptionConfig: vi.fn(),
  updateTranscriptionConfig: vi.fn(),
  testTranscriptionProvider: vi.fn(),
}));

vi.mock("../../../api", () => ({
  default: apiMocks,
  api: apiMocks,
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

const transcriptionSettings = {
  audio_mode: "auto",
  transcription_provider_type: "disabled",
  transcription_provider_id: "",
  transcription_model: "whisper-1",
  provider_types: [
    {
      id: "disabled",
      name: "Disabled",
      local: false,
      requires_key: false,
      description: "Do not transcribe audio.",
    },
    {
      id: "dashscope_qwen3_flash",
      name: "Qwen3 ASR Flash",
      local: false,
      requires_key: true,
      description: "DashScope short-audio OpenAI-compatible backend.",
    },
    {
      id: "doubao_seedasr_stream",
      name: "Doubao Streaming ASR 2.0",
      local: false,
      requires_key: true,
      description: "Volcengine SeedASR streaming WebSocket backend.",
    },
    {
      id: "mimo_asr",
      name: "MiMo V2.5 ASR",
      local: false,
      requires_key: true,
      description: "Xiaomi MiMo V2.5 ASR OpenAI-compatible backend.",
    },
    {
      id: "sensevoice_local",
      name: "SenseVoiceSmall",
      local: true,
      requires_key: false,
      description: "Local SenseVoiceSmall via FunASR.",
    },
  ],
  provider_configs: {
    dashscope_qwen3_flash: {
      model: "qwen3-asr-flash",
      base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1",
      api_key_env: "DASHSCOPE_API_KEY",
      language: "auto",
      timeout_seconds: 60,
      extra: {},
      api_key_configured: true,
    },
    doubao_seedasr_stream: {
      model: "bigmodel",
      base_url: "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async",
      api_key_env: "DOUBAO_AUDIO_API_KEY",
      resource_id: "volc.seedasr.sauc.duration",
      language: "auto",
      timeout_seconds: 60,
      extra: {},
      api_key_configured: true,
    },
    mimo_asr: {
      model: "mimo-v2.5-asr",
      base_url: "https://api.xiaomimimo.com/v1",
      api_key_env: "MIMO_API_KEY",
      language: "auto",
      timeout_seconds: 60,
      extra: {},
      api_key_configured: true,
    },
    sensevoice_local: {
      model: "iic/SenseVoiceSmall",
      language: "auto",
      timeout_seconds: 60,
      extra: {},
    },
  },
  whisper_api_providers: [],
  local_status: {
    local_whisper: {
      available: false,
      ffmpeg_installed: true,
      whisper_installed: false,
    },
    sensevoice: {
      available: false,
      funasr_installed: false,
      install_hint: 'pip install "qwenpaw[sensevoice]"',
    },
  },
};

describe("VoiceTranscriptionPage", () => {
  beforeEach(() => {
    apiMocks.getTranscriptionConfig.mockResolvedValue(transcriptionSettings);
    apiMocks.updateTranscriptionConfig.mockResolvedValue(transcriptionSettings);
    apiMocks.testTranscriptionProvider.mockResolvedValue({
      success: true,
      message: "Transcription provider is reachable.",
      latency_ms: 123,
      text: "ok transcript",
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renders cloud ASR config, tests connectivity, and saves provider config", async () => {
    const user = userEvent.setup();
    renderWithProviders(<VoiceTranscriptionPage />);

    expect(
      await screen.findByText("voiceTranscription.providerTypeLabel"),
    ).toBeInTheDocument();
    expect(screen.getByText("Qwen3 ASR Flash")).toBeInTheDocument();
    expect(screen.getByText("Doubao Streaming ASR 2.0")).toBeInTheDocument();
    expect(screen.getByText("MiMo V2.5 ASR")).toBeInTheDocument();
    expect(screen.getByText("SenseVoiceSmall")).toBeInTheDocument();

    await user.click(screen.getByText("Qwen3 ASR Flash"));

    const modelInput = await screen.findByDisplayValue("qwen3-asr-flash");
    expect(
      screen.getByDisplayValue(
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
      ),
    ).toBeInTheDocument();
    expect(screen.getByDisplayValue("DASHSCOPE_API_KEY")).toBeInTheDocument();

    await user.clear(modelInput);
    await user.type(modelInput, "qwen3-asr-flash-custom");
    await user.click(
      screen.getByRole("button", {
        name: "voiceTranscription.testConnection",
      }),
    );

    await waitFor(() => {
      expect(apiMocks.testTranscriptionProvider).toHaveBeenCalledWith({
        transcription_provider_type: "dashscope_qwen3_flash",
        provider_config: expect.objectContaining({
          model: "qwen3-asr-flash-custom",
          base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1",
          api_key_env: "DASHSCOPE_API_KEY",
          language: "auto",
        }),
      });
    });
    expect(await screen.findByText("ok transcript")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "common.save" }));

    await waitFor(() => {
      expect(apiMocks.updateTranscriptionConfig).toHaveBeenCalledWith(
        expect.objectContaining({
          audio_mode: "auto",
          transcription_provider_type: "dashscope_qwen3_flash",
          provider_configs: {
            dashscope_qwen3_flash: expect.objectContaining({
              model: "qwen3-asr-flash-custom",
              base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1",
              api_key_env: "DASHSCOPE_API_KEY",
              language: "auto",
            }),
          },
        }),
      );
    });
  });
});
