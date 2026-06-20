import { Card, Radio, Space, Alert, Tag } from "antd";
import { useTranslation } from "react-i18next";
import type { AsrProviderType } from "@/api/modules/agent";
import type { LocalWhisperStatus } from "../useVoiceTranscription";
import styles from "../index.module.less";

interface ProviderTypeCardProps {
  providerType: string;
  providerTypes: AsrProviderType[];
  onProviderTypeChange: (value: string) => void;
  isLocalWhisper: boolean;
  isSenseVoice: boolean;
  localWhisperStatus: LocalWhisperStatus | null;
  localStatus: Record<string, unknown>;
}

const FALLBACK_PROVIDER_TYPES: AsrProviderType[] = [
  {
    id: "disabled",
    name: "Disabled",
    local: false,
    requires_key: false,
    description: "Do not transcribe audio.",
  },
  {
    id: "whisper_api",
    name: "Whisper API",
    local: false,
    requires_key: false,
    description: "OpenAI-compatible Whisper endpoint.",
  },
  {
    id: "local_whisper",
    name: "Local Whisper",
    local: true,
    requires_key: false,
    description: "Local openai-whisper package.",
  },
];

export function ProviderTypeCard({
  providerType,
  providerTypes,
  onProviderTypeChange,
  isLocalWhisper,
  isSenseVoice,
  localWhisperStatus,
  localStatus,
}: ProviderTypeCardProps) {
  const { t } = useTranslation();
  const items =
    providerTypes.length > 0 ? providerTypes : FALLBACK_PROVIDER_TYPES;
  const sensevoiceStatus = localStatus?.sensevoice as
    | { available?: boolean; install_hint?: string }
    | undefined;

  return (
    <Card className={styles.card}>
      <h3 className={styles.cardTitle}>
        {t("voiceTranscription.providerTypeLabel")}
      </h3>
      <p className={styles.cardDescription}>
        {t("voiceTranscription.providerTypeDescription")}
      </p>
      <Radio.Group
        value={providerType}
        onChange={(e) => onProviderTypeChange(e.target.value)}
      >
        <Space direction="vertical" size="middle">
          {items.map((item) => (
            <Radio key={item.id} value={item.id}>
              <span className={styles.optionLabel}>{item.name}</span>
              {item.local && <Tag>{t("voiceTranscription.localTag")}</Tag>}
              {item.requires_key && (
                <Tag color="orange">{t("voiceTranscription.apiKeyTag")}</Tag>
              )}
              <span className={styles.optionDescription}>
                {item.description}
              </span>
            </Radio>
          ))}
        </Space>
      </Radio.Group>

      {isLocalWhisper && localWhisperStatus && (
        <div style={{ marginTop: 12 }}>
          {localWhisperStatus.available ? (
            <Alert
              type="success"
              showIcon
              message={t("voiceTranscription.localWhisperReady")}
            />
          ) : (
            <Alert
              type="warning"
              showIcon
              message={t("voiceTranscription.localWhisperMissing")}
              description={t("voiceTranscription.localWhisperMissingDesc", {
                ffmpeg: localWhisperStatus.ffmpeg_installed
                  ? t("common.enabled")
                  : t("common.disabled"),
                whisper: localWhisperStatus.whisper_installed
                  ? t("common.enabled")
                  : t("common.disabled"),
              })}
            />
          )}
        </div>
      )}

      {isSenseVoice && sensevoiceStatus && (
        <div style={{ marginTop: 12 }}>
          {sensevoiceStatus.available ? (
            <Alert
              type="success"
              showIcon
              message={t("voiceTranscription.senseVoiceReady")}
            />
          ) : (
            <Alert
              type="warning"
              showIcon
              message={t("voiceTranscription.senseVoiceMissing")}
              description={
                sensevoiceStatus.install_hint ||
                'pip install "qwenpaw[sensevoice]"'
              }
            />
          )}
        </div>
      )}
    </Card>
  );
}
