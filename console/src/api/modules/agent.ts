import { request } from "../request";
import { getApiUrl } from "../config";
import { buildAuthHeaders } from "../authHeaders";
import type { AgentRequest, AgentsRunningConfig } from "../types";

export type TranscriptionErrorCode =
  | "TRANSCRIPTION_DISABLED"
  | "FILE_TOO_LARGE"
  | "UNSUPPORTED_FILE_TYPE";

export interface AsrProviderConfig {
  model?: string;
  base_url?: string;
  api_key?: string;
  api_key_env?: string;
  api_key_configured?: boolean;
  language?: string;
  resource_id?: string;
  app_key?: string;
  access_key?: string;
  access_key_configured?: boolean;
  timeout_seconds?: number;
  extra?: Record<string, unknown>;
}

export interface AsrProviderType {
  id: string;
  name: string;
  local: boolean;
  requires_key: boolean;
  description: string;
  available?: boolean;
  default_model?: string;
  default_env?: string;
  status?: Record<string, unknown>;
}

export interface TranscriptionSettings {
  audio_mode: string;
  transcription_provider_type: string;
  transcription_provider_id: string;
  transcription_model: string;
  provider_types: AsrProviderType[];
  provider_configs: Record<string, AsrProviderConfig>;
  whisper_api_providers: { id: string; name: string; available: boolean }[];
  local_status: {
    local_whisper?: Record<string, unknown>;
    sensevoice?: Record<string, unknown>;
  };
}

export interface TranscriptionTestResult {
  success: boolean;
  message: string;
  latency_ms?: number;
  text?: string;
  status?: Record<string, unknown>;
}

export class TranscriptionError extends Error {
  status: number;
  code?: TranscriptionErrorCode;
  constructor(status: number, msg: string, code?: TranscriptionErrorCode) {
    super(`Transcription failed: ${status} ${msg}`);
    this.name = "TranscriptionError";
    this.status = status;
    this.code = code;
  }
}

// Agent API
export const agentApi = {
  agentRoot: () => request<unknown>("/agent/"),

  healthCheck: () => request<unknown>("/agent/health"),

  agentApi: (body: AgentRequest) =>
    request<unknown>("/agent/process", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  getProcessStatus: () => request<unknown>("/agent/admin/status"),

  shutdownSimple: () =>
    request<void>("/agent/shutdown", {
      method: "POST",
    }),

  shutdown: () =>
    request<void>("/agent/admin/shutdown", {
      method: "POST",
    }),

  getAgentRunningConfig: () =>
    request<AgentsRunningConfig>("/workspace/running-config"),

  updateAgentRunningConfig: (config: AgentsRunningConfig) =>
    request<AgentsRunningConfig>("/workspace/running-config", {
      method: "PUT",
      body: JSON.stringify(config),
    }),

  getAgentLanguage: () => request<{ language: string }>("/workspace/language"),

  updateAgentLanguage: (language: string) =>
    request<{ language: string; copied_files: string[] }>(
      "/workspace/language",
      {
        method: "PUT",
        body: JSON.stringify({ language }),
      },
    ),

  getAudioMode: () => request<{ audio_mode: string }>("/workspace/audio-mode"),

  updateAudioMode: (audio_mode: string) =>
    request<{ audio_mode: string }>("/workspace/audio-mode", {
      method: "PUT",
      body: JSON.stringify({ audio_mode }),
    }),

  getTranscriptionProviders: () =>
    request<{
      providers: { id: string; name: string; available: boolean }[];
      configured_provider_id: string;
    }>("/workspace/transcription-providers"),

  updateTranscriptionProvider: (provider_id: string) =>
    request<{ provider_id: string }>("/workspace/transcription-provider", {
      method: "PUT",
      body: JSON.stringify({ provider_id }),
    }),

  getTranscriptionProviderType: () =>
    request<{ transcription_provider_type: string }>(
      "/workspace/transcription-provider-type",
    ),

  updateTranscriptionProviderType: (transcription_provider_type: string) =>
    request<{ transcription_provider_type: string }>(
      "/workspace/transcription-provider-type",
      {
        method: "PUT",
        body: JSON.stringify({ transcription_provider_type }),
      },
    ),

  getTranscriptionConfig: () =>
    request<TranscriptionSettings>("/workspace/transcription-config"),

  updateTranscriptionConfig: (settings: Partial<TranscriptionSettings>) =>
    request<TranscriptionSettings>("/workspace/transcription-config", {
      method: "PUT",
      body: JSON.stringify(settings),
    }),

  testTranscriptionProvider: (body: {
    transcription_provider_type: string;
    provider_config?: AsrProviderConfig;
    source_url?: string;
  }) =>
    request<TranscriptionTestResult>("/workspace/transcription-test", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  getLocalWhisperStatus: () =>
    request<{
      available: boolean;
      ffmpeg_installed: boolean;
      whisper_installed: boolean;
    }>("/workspace/local-whisper-status"),

  getLocalAsrStatus: () =>
    request<{
      local_whisper: Record<string, unknown>;
      sensevoice: Record<string, unknown>;
    }>("/workspace/local-asr-status"),

  transcribeAudio: async (file: File | Blob): Promise<{ text: string }> => {
    const formData = new FormData();
    formData.append("file", file);
    const response = await fetch(getApiUrl("/workspace/transcribe"), {
      method: "POST",
      headers: buildAuthHeaders(),
      body: formData,
    });
    if (!response.ok) {
      let msg = response.statusText;
      let code: TranscriptionErrorCode | undefined;
      try {
        const body = await response.json();
        if (typeof body?.detail === "object" && body.detail !== null) {
          code = body.detail.code;
          msg = body.detail.message || msg;
        } else if (typeof body?.detail === "string") {
          msg = body.detail;
        }
      } catch {
        // response body not JSON, use status text
      }
      throw new TranscriptionError(response.status, msg, code);
    }
    return response.json();
  },
};
