import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import api from "../../../api";
import type {
  AsrProviderConfig,
  AsrProviderType,
  TranscriptionTestResult,
} from "../../../api/modules/agent";
import { useAppMessage } from "../../../hooks/useAppMessage";

export interface TranscriptionProvider {
  id: string;
  name: string;
  available: boolean;
}

export interface LocalWhisperStatus {
  available: boolean;
  ffmpeg_installed: boolean;
  whisper_installed: boolean;
}

const DEFAULT_PROVIDER_CONFIGS: Record<string, AsrProviderConfig> = {
  doubao_seedasr_stream: {
    model: "bigmodel",
    base_url: "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async",
    api_key_env: "DOUBAO_AUDIO_API_KEY",
    resource_id: "volc.seedasr.sauc.duration",
    language: "auto",
    timeout_seconds: 60,
  },
  dashscope_qwen3_flash: {
    model: "qwen3-asr-flash",
    base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1",
    api_key_env: "DASHSCOPE_API_KEY",
    language: "auto",
    timeout_seconds: 60,
  },
  dashscope_qwen3_filetrans: {
    model: "qwen3-asr-flash-filetrans",
    base_url:
      "https://dashscope.aliyuncs.com/api/v1/services/audio/asr/transcription",
    api_key_env: "DASHSCOPE_API_KEY",
    language: "auto",
    timeout_seconds: 60,
  },
  mimo_asr: {
    model: "mimo-v2.5-asr",
    base_url: "https://api.xiaomimimo.com/v1",
    api_key_env: "MIMO_API_KEY",
    language: "auto",
    timeout_seconds: 60,
  },
  sensevoice_local: {
    model: "iic/SenseVoiceSmall",
    language: "auto",
    timeout_seconds: 60,
  },
};

function mergeConfig(
  providerType: string,
  config?: AsrProviderConfig,
): AsrProviderConfig {
  return {
    ...(DEFAULT_PROVIDER_CONFIGS[providerType] ?? {}),
    ...(config ?? {}),
  };
}

export function useVoiceTranscription() {
  const { t } = useTranslation();
  const { message } = useAppMessage();

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [audioMode, setAudioMode] = useState("auto");
  const [providerType, setProviderType] = useState("disabled");
  const [providerTypes, setProviderTypes] = useState<AsrProviderType[]>([]);
  const [providers, setProviders] = useState<TranscriptionProvider[]>([]);
  const [selectedProviderId, setSelectedProviderId] = useState("");
  const [transcriptionModel, setTranscriptionModel] = useState("whisper-1");
  const [providerConfigs, setProviderConfigs] = useState<
    Record<string, AsrProviderConfig>
  >({});
  const [localWhisperStatus, setLocalWhisperStatus] =
    useState<LocalWhisperStatus | null>(null);
  const [localStatus, setLocalStatus] = useState<Record<string, unknown>>({});
  const [testResult, setTestResult] = useState<TranscriptionTestResult | null>(
    null,
  );

  const fetchSettings = async () => {
    setLoading(true);
    try {
      const config = await api.getTranscriptionConfig();
      setAudioMode(config.audio_mode ?? "auto");
      setProviderType(config.transcription_provider_type ?? "disabled");
      setProviderTypes(config.provider_types ?? []);
      setProviders(config.whisper_api_providers ?? []);
      setSelectedProviderId(config.transcription_provider_id ?? "");
      setTranscriptionModel(config.transcription_model ?? "whisper-1");
      setProviderConfigs(config.provider_configs ?? {});
      setLocalStatus(config.local_status ?? {});
      setLocalWhisperStatus(
        (config.local_status?.local_whisper as unknown as LocalWhisperStatus) ??
          null,
      );
      setTestResult(null);
    } catch (err) {
      console.error("Failed to load voice transcription settings:", err);
      message.error(t("voiceTranscription.loadFailed"));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSettings();
  }, []);

  const updateProviderConfig = (
    key: string,
    value: string | number | boolean | Record<string, unknown>,
  ) => {
    setProviderConfigs((prev) => ({
      ...prev,
      [providerType]: {
        ...mergeConfig(providerType, prev[providerType]),
        [key]: value,
      },
    }));
  };

  const currentProviderConfig = useMemo(
    () => mergeConfig(providerType, providerConfigs[providerType]),
    [providerConfigs, providerType],
  );

  const handleSave = async () => {
    setSaving(true);
    try {
      const activeConfig = currentProviderConfig;
      await api.updateTranscriptionConfig({
        audio_mode: audioMode,
        transcription_provider_type: providerType,
        transcription_provider_id: selectedProviderId,
        transcription_model: transcriptionModel,
        provider_configs:
          providerType === "disabled" ? {} : { [providerType]: activeConfig },
      });
      message.success(t("voiceTranscription.saveSuccess"));
      await fetchSettings();
    } catch (err) {
      console.error("Failed to save voice transcription settings:", err);
      message.error(t("voiceTranscription.saveFailed"));
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const result = await api.testTranscriptionProvider({
        transcription_provider_type: providerType,
        provider_config: currentProviderConfig,
      });
      setTestResult(result);
      if (result.success) {
        message.success(t("voiceTranscription.testSuccess"));
      } else {
        message.warning(result.message || t("voiceTranscription.testFailed"));
      }
    } catch (err) {
      console.error("Failed to test transcription provider:", err);
      message.error(t("voiceTranscription.testFailed"));
    } finally {
      setTesting(false);
    }
  };

  const availableProviders = providers.filter((p) => p.available);
  const showProviderSection = audioMode !== "native";
  const isLocalWhisper = providerType === "local_whisper";
  const isSenseVoice = providerType === "sensevoice_local";

  return {
    loading,
    saving,
    testing,
    audioMode,
    setAudioMode,
    providerType,
    setProviderType,
    providerTypes,
    selectedProviderId,
    setSelectedProviderId,
    transcriptionModel,
    setTranscriptionModel,
    currentProviderConfig,
    updateProviderConfig,
    localWhisperStatus,
    localStatus,
    availableProviders,
    showProviderSection,
    isLocalWhisper,
    isSenseVoice,
    testResult,
    fetchSettings,
    handleSave,
    handleTest,
  };
}
