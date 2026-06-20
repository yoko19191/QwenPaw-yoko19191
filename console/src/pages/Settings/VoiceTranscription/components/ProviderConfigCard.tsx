import { Card, Select, Alert, Input, Space } from "antd";
import { Button } from "@agentscope-ai/design";
import { useTranslation } from "react-i18next";
import type {
  AsrProviderConfig,
  TranscriptionTestResult,
} from "@/api/modules/agent";
import type { TranscriptionProvider } from "../useVoiceTranscription";
import styles from "../index.module.less";

interface ProviderConfigCardProps {
  providerType: string;
  config: AsrProviderConfig;
  availableProviders: TranscriptionProvider[];
  selectedProviderId: string;
  onProviderChange: (id: string) => void;
  transcriptionModel: string;
  onTranscriptionModelChange: (model: string) => void;
  onConfigChange: (
    key: string,
    value: string | number | boolean | Record<string, unknown>,
  ) => void;
  onTest: () => void;
  testing: boolean;
  testResult: TranscriptionTestResult | null;
}

const CLOUD_TYPES = new Set([
  "doubao_seedasr_stream",
  "dashscope_qwen3_flash",
  "dashscope_qwen3_filetrans",
  "mimo_asr",
]);

const LANGUAGE_OPTIONS = [
  { label: "Auto", value: "auto" },
  { label: "Chinese", value: "zh" },
  { label: "English", value: "en" },
  { label: "Mandarin zh-CN", value: "zh-CN" },
  { label: "English en-US", value: "en-US" },
  { label: "Cantonese yue-CN", value: "yue-CN" },
];

export function ProviderConfigCard({
  providerType,
  config,
  availableProviders,
  selectedProviderId,
  onProviderChange,
  transcriptionModel,
  onTranscriptionModelChange,
  onConfigChange,
  onTest,
  testing,
  testResult,
}: ProviderConfigCardProps) {
  const { t } = useTranslation();

  if (providerType === "disabled") {
    return null;
  }

  return (
    <Card className={styles.card}>
      <div className={styles.cardHeaderRow}>
        <div>
          <h3 className={styles.cardTitle}>
            {t("voiceTranscription.providerConfigLabel")}
          </h3>
          <p className={styles.cardDescription}>
            {t("voiceTranscription.providerConfigDescription")}
          </p>
        </div>
        <Button
          onClick={onTest}
          loading={testing}
          disabled={providerType === "disabled"}
        >
          {t("voiceTranscription.testConnection")}
        </Button>
      </div>

      {providerType === "whisper_api" && (
        <>
          {availableProviders.length === 0 ? (
            <Alert
              type="warning"
              showIcon
              message={t("voiceTranscription.noProvidersWarning")}
            />
          ) : (
            <div className={styles.formGrid}>
              <label>
                <span>{t("voiceTranscription.providerLabel")}</span>
                <Select
                  value={selectedProviderId || undefined}
                  onChange={onProviderChange}
                  placeholder={t("voiceTranscription.providerPlaceholder")}
                >
                  {availableProviders.map((p) => (
                    <Select.Option key={p.id} value={p.id}>
                      {p.name}
                    </Select.Option>
                  ))}
                </Select>
              </label>
              <label>
                <span>{t("voiceTranscription.modelLabel")}</span>
                <Input
                  value={transcriptionModel}
                  onChange={(e) => onTranscriptionModelChange(e.target.value)}
                  placeholder="whisper-1"
                />
              </label>
            </div>
          )}
        </>
      )}

      {CLOUD_TYPES.has(providerType) && (
        <div className={styles.formGrid}>
          <label>
            <span>{t("voiceTranscription.modelLabel")}</span>
            <Input
              value={config.model || ""}
              onChange={(e) => onConfigChange("model", e.target.value)}
            />
          </label>
          <label>
            <span>{t("voiceTranscription.baseUrlLabel")}</span>
            <Input
              value={config.base_url || ""}
              onChange={(e) => onConfigChange("base_url", e.target.value)}
            />
          </label>
          <label>
            <span>{t("voiceTranscription.apiKeyEnvLabel")}</span>
            <Input
              value={config.api_key_env || ""}
              onChange={(e) => onConfigChange("api_key_env", e.target.value)}
            />
          </label>
          <label>
            <span>{t("voiceTranscription.apiKeyLabel")}</span>
            <Input.Password
              value={config.api_key || ""}
              onChange={(e) => onConfigChange("api_key", e.target.value)}
              placeholder={
                config.api_key_configured
                  ? t("voiceTranscription.apiKeyConfigured")
                  : t("voiceTranscription.apiKeyPlaceholder")
              }
            />
          </label>
          {providerType === "doubao_seedasr_stream" && (
            <label>
              <span>{t("voiceTranscription.resourceIdLabel")}</span>
              <Input
                value={config.resource_id || ""}
                onChange={(e) => onConfigChange("resource_id", e.target.value)}
              />
            </label>
          )}
          <label>
            <span>{t("voiceTranscription.languageLabel")}</span>
            <Select
              value={config.language || "auto"}
              onChange={(value) => onConfigChange("language", value)}
              options={LANGUAGE_OPTIONS}
            />
          </label>
        </div>
      )}

      {providerType === "sensevoice_local" && (
        <div className={styles.formGrid}>
          <label>
            <span>{t("voiceTranscription.modelLabel")}</span>
            <Input
              value={config.model || "iic/SenseVoiceSmall"}
              onChange={(e) => onConfigChange("model", e.target.value)}
            />
          </label>
          <label>
            <span>{t("voiceTranscription.languageLabel")}</span>
            <Select
              value={config.language || "auto"}
              onChange={(value) => onConfigChange("language", value)}
              options={LANGUAGE_OPTIONS}
            />
          </label>
        </div>
      )}

      {providerType === "dashscope_qwen3_filetrans" && (
        <Alert
          type="info"
          showIcon
          className={styles.inlineAlert}
          message={t("voiceTranscription.fileTransUrlOnly")}
        />
      )}

      {testResult && (
        <Alert
          type={testResult.success ? "success" : "warning"}
          showIcon
          className={styles.inlineAlert}
          message={testResult.message}
          description={
            <Space direction="vertical" size={4}>
              {typeof testResult.latency_ms === "number" && (
                <span>
                  {t("voiceTranscription.latencyLabel")}:{" "}
                  {testResult.latency_ms} ms
                </span>
              )}
              {testResult.text && <span>{testResult.text}</span>}
            </Space>
          }
        />
      )}
    </Card>
  );
}
