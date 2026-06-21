import {
  Form,
  Card,
  Switch,
  InputNumber,
  Input,
  Collapse,
  Alert,
} from "@agentscope-ai/design";
import { useTranslation } from "react-i18next";
import { SliderWithValue } from "./SliderWithValue";
import styles from "../index.module.less";

export function ReMeLightMemoryCard() {
  const { t } = useTranslation();

  const baseUrl = Form.useWatch([
    "reme_light_memory_config",
    "embedding_model_config",
    "base_url",
  ]);
  const modelName = Form.useWatch([
    "reme_light_memory_config",
    "embedding_model_config",
    "model_name",
  ]);
  const embeddingEnabled = !!(baseUrl?.trim() && modelName?.trim());

  return (
    <Card
      className={styles.formCard}
      title={t("agentConfig.remeLightMemoryTitle")}
    >
      <Form.Item
        label={t("agentConfig.summarizeWhenCompact")}
        name={["reme_light_memory_config", "summarize_when_compact"]}
        valuePropName="checked"
        tooltip={t("agentConfig.summarizeWhenCompactTooltip")}
      >
        <Switch />
      </Form.Item>

      <Form.Item
        label={t("agentConfig.autoMemoryInterval")}
        name={["reme_light_memory_config", "auto_memory_interval"]}
        tooltip={t("agentConfig.autoMemoryIntervalTooltip")}
      >
        <InputNumber
          style={{ width: "100%" }}
          min={1}
          step={1}
          placeholder={t("agentConfig.autoMemoryIntervalPlaceholder")}
        />
      </Form.Item>

      <Form.Item
        label={t("agentConfig.dreamCron")}
        name={["reme_light_memory_config", "dream_cron"]}
        tooltip={t("agentConfig.dreamCronTooltip")}
        normalize={(value) => value ?? ""}
      >
        <Input placeholder={t("agentConfig.dreamCronPlaceholder")} />
      </Form.Item>

      <Form.Item
        label={t("agentConfig.rebuildMemoryIndexOnStart")}
        name={["reme_light_memory_config", "rebuild_memory_index_on_start"]}
        valuePropName="checked"
        tooltip={t("agentConfig.rebuildMemoryIndexOnStartTooltip")}
      >
        <Switch />
      </Form.Item>

      <Form.Item
        label={t("agentConfig.recursiveFileWatcher")}
        name={["reme_light_memory_config", "recursive_file_watcher"]}
        valuePropName="checked"
        tooltip={t("agentConfig.recursiveFileWatcherTooltip")}
      >
        <Switch />
      </Form.Item>

      <Collapse
        items={[
          {
            key: "markdownMemory",
            label: t("agentConfig.markdownMemoryCollapseLabel"),
            forceRender: true,
            children: (
              <>
                <Form.Item
                  label={t("agentConfig.markdownMemoryEnabled")}
                  name={["markdown_memory_config", "enabled"]}
                  valuePropName="checked"
                  tooltip={t("agentConfig.markdownMemoryEnabledTooltip")}
                >
                  <Switch />
                </Form.Item>

                <Form.Item
                  label={t("agentConfig.markdownMemoryMigrateLegacy")}
                  name={["markdown_memory_config", "migrate_legacy_root_files"]}
                  valuePropName="checked"
                  tooltip={t("agentConfig.markdownMemoryMigrateLegacyTooltip")}
                >
                  <Switch />
                </Form.Item>

                <Form.Item
                  label={t("agentConfig.markdownMemoryMaxPromptChars")}
                  name={["markdown_memory_config", "max_prompt_chars"]}
                  tooltip={t("agentConfig.markdownMemoryMaxPromptCharsTooltip")}
                >
                  <InputNumber
                    style={{ width: "100%" }}
                    min={1000}
                    step={1000}
                  />
                </Form.Item>

                <Form.Item
                  label={t("agentConfig.markdownMemoryReviewEnabled")}
                  name={["markdown_memory_config", "review_enabled"]}
                  valuePropName="checked"
                >
                  <Switch />
                </Form.Item>

                <Form.Item
                  label={t("agentConfig.markdownMemoryReviewInterval")}
                  name={["markdown_memory_config", "review_interval_turns"]}
                >
                  <InputNumber style={{ width: "100%" }} min={1} step={1} />
                </Form.Item>

                <Form.Item
                  label={t("agentConfig.markdownMemoryCuratorEnabled")}
                  name={["markdown_memory_config", "curator_enabled"]}
                  valuePropName="checked"
                >
                  <Switch />
                </Form.Item>

                <Form.Item
                  label={t("agentConfig.markdownMemoryCuratorCron")}
                  name={["markdown_memory_config", "curator_cron"]}
                  normalize={(value) => value ?? ""}
                >
                  <Input placeholder="0 3 * * 0" />
                </Form.Item>

                <Form.Item
                  label={t("agentConfig.markdownMemoryLlmConsolidation")}
                  name={["markdown_memory_config", "llm_consolidation_enabled"]}
                  valuePropName="checked"
                >
                  <Switch />
                </Form.Item>
              </>
            ),
          },
          {
            key: "proceduralSkillMemory",
            label: t("agentConfig.proceduralSkillMemoryCollapseLabel"),
            forceRender: true,
            children: (
              <>
                <Form.Item
                  label={t("agentConfig.proceduralSkillMemoryEnabled")}
                  name={["procedural_skill_memory_config", "enabled"]}
                  valuePropName="checked"
                >
                  <Switch />
                </Form.Item>

                <Form.Item
                  label={t("agentConfig.proceduralSkillReviewEnabled")}
                  name={["procedural_skill_memory_config", "review_enabled"]}
                  valuePropName="checked"
                >
                  <Switch />
                </Form.Item>

                <Form.Item
                  label={t("agentConfig.proceduralSkillReviewInterval")}
                  name={[
                    "procedural_skill_memory_config",
                    "review_interval_turns",
                  ]}
                >
                  <InputNumber style={{ width: "100%" }} min={1} step={1} />
                </Form.Item>

                <Form.Item
                  label={t("agentConfig.foregroundSkillManageEnabled")}
                  name={[
                    "procedural_skill_memory_config",
                    "foreground_skill_manage_enabled",
                  ]}
                  valuePropName="checked"
                  tooltip={t("agentConfig.foregroundSkillManageEnabledTooltip")}
                >
                  <Switch />
                </Form.Item>

                <Form.Item
                  label={t("agentConfig.proceduralSkillCuratorEnabled")}
                  name={["procedural_skill_memory_config", "curator_enabled"]}
                  valuePropName="checked"
                >
                  <Switch />
                </Form.Item>

                <Form.Item
                  label={t("agentConfig.proceduralSkillCuratorCron")}
                  name={["procedural_skill_memory_config", "curator_cron"]}
                  normalize={(value) => value ?? ""}
                >
                  <Input placeholder="0 4 * * 0" />
                </Form.Item>

                <Form.Item
                  label={t("agentConfig.skillAutoArchiveEnabled")}
                  name={[
                    "procedural_skill_memory_config",
                    "auto_archive_enabled",
                  ]}
                  valuePropName="checked"
                >
                  <Switch />
                </Form.Item>

                <Form.Item
                  label={t("agentConfig.skillArchiveAfterDays")}
                  name={[
                    "procedural_skill_memory_config",
                    "archive_after_days",
                  ]}
                >
                  <InputNumber style={{ width: "100%" }} min={1} step={1} />
                </Form.Item>

                <Form.Item
                  label={t("agentConfig.skillArchiveMinUses")}
                  name={["procedural_skill_memory_config", "archive_min_uses"]}
                >
                  <InputNumber style={{ width: "100%" }} min={0} step={1} />
                </Form.Item>

                <Form.Item
                  label={t("agentConfig.skillStalePassesBeforeArchive")}
                  name={[
                    "procedural_skill_memory_config",
                    "stale_passes_before_archive",
                  ]}
                >
                  <InputNumber style={{ width: "100%" }} min={1} step={1} />
                </Form.Item>

                <Form.Item
                  label={t("agentConfig.skillMergeProposalsEnabled")}
                  name={[
                    "procedural_skill_memory_config",
                    "merge_proposals_enabled",
                  ]}
                  valuePropName="checked"
                >
                  <Switch />
                </Form.Item>

                <Form.Item
                  label={t("agentConfig.skillAutoMergeEnabled")}
                  name={[
                    "procedural_skill_memory_config",
                    "auto_merge_enabled",
                  ]}
                  valuePropName="checked"
                  tooltip={t("agentConfig.skillAutoMergeEnabledTooltip")}
                >
                  <Switch />
                </Form.Item>
              </>
            ),
          },
          {
            key: "autoMemorySearch",
            label: t("agentConfig.autoMemorySearchCollapseLabel"),
            forceRender: true,
            children: (
              <>
                <Form.Item
                  label={t("agentConfig.autoMemorySearch")}
                  name={[
                    "reme_light_memory_config",
                    "auto_memory_search_config",
                    "enabled",
                  ]}
                  valuePropName="checked"
                  tooltip={t("agentConfig.autoMemorySearchTooltip")}
                >
                  <Switch />
                </Form.Item>

                <Form.Item
                  label={t("agentConfig.autoMaxResults")}
                  name={[
                    "reme_light_memory_config",
                    "auto_memory_search_config",
                    "max_results",
                  ]}
                  rules={[
                    {
                      required: true,
                      message: t("agentConfig.autoMaxResultsRequired"),
                    },
                    {
                      type: "number",
                      min: 1,
                      message: t("agentConfig.autoMaxResultsMin"),
                    },
                  ]}
                  tooltip={t("agentConfig.autoMaxResultsTooltip")}
                >
                  <InputNumber style={{ width: "100%" }} min={1} step={1} />
                </Form.Item>

                <Form.Item
                  label={t("agentConfig.autoMinScore")}
                  name={[
                    "reme_light_memory_config",
                    "auto_memory_search_config",
                    "min_score",
                  ]}
                  rules={[
                    {
                      required: true,
                      message: t("agentConfig.autoMinScoreRequired"),
                    },
                  ]}
                  tooltip={t("agentConfig.autoMinScoreTooltip")}
                >
                  <SliderWithValue
                    min={0}
                    max={1}
                    step={0.05}
                    marks={{ 0: "0", 0.5: "0.5", 1: "1" }}
                  />
                </Form.Item>
              </>
            ),
          },
          {
            key: "embeddingConfig",
            label: t("agentConfig.embeddingConfigCollapseLabel"),
            forceRender: true,
            children: (
              <>
                <Alert
                  type="warning"
                  showIcon
                  message={`${t("agentConfig.embeddingEnableHint")} ${t(
                    "agentConfig.embeddingRestartWarning",
                  )}`}
                  style={{ marginBottom: 16 }}
                />

                <Form.Item
                  label={t("agentConfig.embeddingBaseUrl")}
                  name={[
                    "reme_light_memory_config",
                    "embedding_model_config",
                    "base_url",
                  ]}
                  tooltip={t("agentConfig.embeddingBaseUrlTooltip")}
                >
                  <Input
                    placeholder={t("agentConfig.embeddingBaseUrlPlaceholder")}
                  />
                </Form.Item>

                <Form.Item
                  label={t("agentConfig.embeddingModelName")}
                  name={[
                    "reme_light_memory_config",
                    "embedding_model_config",
                    "model_name",
                  ]}
                  tooltip={t("agentConfig.embeddingModelNameTooltip")}
                >
                  <Input
                    placeholder={t("agentConfig.embeddingModelNamePlaceholder")}
                  />
                </Form.Item>

                <Form.Item
                  label={t("agentConfig.embeddingApiKey")}
                  name={[
                    "reme_light_memory_config",
                    "embedding_model_config",
                    "api_key",
                  ]}
                  tooltip={t("agentConfig.embeddingApiKeyTooltip")}
                >
                  <Input.Password
                    placeholder={t("agentConfig.embeddingApiKeyPlaceholder")}
                  />
                </Form.Item>

                <Form.Item
                  label={t("agentConfig.embeddingDimensions")}
                  name={[
                    "reme_light_memory_config",
                    "embedding_model_config",
                    "dimensions",
                  ]}
                  rules={[
                    {
                      required: true,
                      message: t("agentConfig.embeddingDimensionsRequired"),
                    },
                    {
                      type: "number",
                      min: 1,
                      message: t("agentConfig.embeddingDimensionsMin"),
                    },
                  ]}
                  tooltip={t("agentConfig.embeddingDimensionsTooltip")}
                >
                  <InputNumber
                    style={{ width: "100%" }}
                    min={1}
                    step={256}
                    disabled={!embeddingEnabled}
                  />
                </Form.Item>

                <Form.Item
                  label={t("agentConfig.embeddingEnableCache")}
                  name={[
                    "reme_light_memory_config",
                    "embedding_model_config",
                    "enable_cache",
                  ]}
                  valuePropName="checked"
                  tooltip={t("agentConfig.embeddingEnableCacheTooltip")}
                >
                  <Switch disabled={!embeddingEnabled} />
                </Form.Item>

                <Form.Item
                  label={t("agentConfig.embeddingMaxCacheSize")}
                  name={[
                    "reme_light_memory_config",
                    "embedding_model_config",
                    "max_cache_size",
                  ]}
                  rules={[
                    {
                      required: true,
                      message: t("agentConfig.embeddingMaxCacheSizeRequired"),
                    },
                  ]}
                  tooltip={t("agentConfig.embeddingMaxCacheSizeTooltip")}
                >
                  <InputNumber
                    style={{ width: "100%" }}
                    min={1}
                    step={100}
                    disabled={!embeddingEnabled}
                  />
                </Form.Item>

                <Form.Item
                  label={t("agentConfig.embeddingMaxInputLength")}
                  name={[
                    "reme_light_memory_config",
                    "embedding_model_config",
                    "max_input_length",
                  ]}
                  rules={[
                    {
                      required: true,
                      message: t("agentConfig.embeddingMaxInputLengthRequired"),
                    },
                  ]}
                  tooltip={t("agentConfig.embeddingMaxInputLengthTooltip")}
                >
                  <InputNumber
                    style={{ width: "100%" }}
                    min={1}
                    step={1024}
                    disabled={!embeddingEnabled}
                  />
                </Form.Item>

                <Form.Item
                  label={t("agentConfig.embeddingMaxBatchSize")}
                  name={[
                    "reme_light_memory_config",
                    "embedding_model_config",
                    "max_batch_size",
                  ]}
                  rules={[
                    {
                      required: true,
                      message: t("agentConfig.embeddingMaxBatchSizeRequired"),
                    },
                  ]}
                  tooltip={t("agentConfig.embeddingMaxBatchSizeTooltip")}
                >
                  <InputNumber
                    style={{ width: "100%" }}
                    min={1}
                    step={1}
                    disabled={!embeddingEnabled}
                  />
                </Form.Item>
              </>
            ),
          },
        ]}
      />
    </Card>
  );
}
