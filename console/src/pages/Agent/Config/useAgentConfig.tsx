import { useState, useEffect, useCallback, useRef } from "react";
import { Form, Modal } from "@agentscope-ai/design";
import { useTranslation } from "react-i18next";
import api from "../../../api";
import type { AgentsRunningConfig } from "../../../api/types";
import { useAppMessage } from "../../../hooks/useAppMessage";
import { useAgentStore } from "../../../stores/agentStore";
import {
  CONTEXT_MANAGER_BACKEND_MAPPINGS,
  MEMORY_MANAGER_BACKEND_MAPPINGS,
} from "../../../constants/backendMappings";
import type { ToolExecutionLevel } from "./components/ToolExecutionLevelCard";

const DEFAULT_MARKDOWN_MEMORY_CONFIG = {
  enabled: true,
  migrate_legacy_root_files: true,
  max_prompt_chars: 24000,
  review_enabled: true,
  review_interval_turns: 5,
  curator_enabled: true,
  curator_cron: "0 3 * * 0",
  llm_consolidation_enabled: false,
};

const DEFAULT_PROCEDURAL_SKILL_MEMORY_CONFIG = {
  enabled: true,
  review_enabled: true,
  review_interval_turns: 10,
  foreground_skill_manage_enabled: false,
  curator_enabled: true,
  curator_cron: "0 4 * * 0",
  auto_archive_enabled: true,
  archive_after_days: 30,
  archive_min_uses: 2,
  stale_passes_before_archive: 2,
  merge_proposals_enabled: true,
  auto_merge_enabled: false,
};

export function useAgentConfig() {
  const { t } = useTranslation();
  const { message } = useAppMessage();
  const { selectedAgent } = useAgentStore();
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [language, setLanguage] = useState<string>("zh");
  const [savingLang, setSavingLang] = useState(false);
  const [timezone, setTimezone] = useState<string>("UTC");
  const [savingTimezone, setSavingTimezone] = useState(false);
  const [approvalLevel, setApprovalLevel] =
    useState<ToolExecutionLevel>("AUTO");
  const originalConfigRef = useRef<AgentsRunningConfig | null>(null);

  const fetchConfig = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [config, langResp, tzResp] = await Promise.all([
        api.getAgentRunningConfig(),
        api.getAgentLanguage(),
        api.getUserTimezone(),
      ]);
      const loadedLevel = (
        config.approval_level || "AUTO"
      ).toUpperCase() as ToolExecutionLevel;
      setApprovalLevel(loadedLevel);
      const contextBackend =
        config.context_manager_backend in CONTEXT_MANAGER_BACKEND_MAPPINGS
          ? config.context_manager_backend
          : "light";
      const memoryBackend =
        config.memory_manager_backend in MEMORY_MANAGER_BACKEND_MAPPINGS
          ? config.memory_manager_backend
          : "remelight";
      form.setFieldsValue({
        max_iters: config.max_iters,
        auto_continue_on_text_only: config.auto_continue_on_text_only ?? false,
        shell_command_timeout: config.shell_command_timeout ?? 60.0,
        shell_command_executable: config.shell_command_executable ?? "",
        llm_retry_enabled: config.llm_retry_enabled,
        llm_max_retries: config.llm_max_retries,
        llm_backoff_base: config.llm_backoff_base,
        llm_backoff_cap: config.llm_backoff_cap,
        llm_max_concurrent: config.llm_max_concurrent,
        llm_max_qpm: config.llm_max_qpm,
        llm_rate_limit_pause: config.llm_rate_limit_pause,
        llm_rate_limit_jitter: config.llm_rate_limit_jitter,
        llm_acquire_timeout: config.llm_acquire_timeout,
        history_max_length: config.history_max_length,
        context_manager_backend: contextBackend,
        light_context_config: config.light_context_config,
        memory_manager_backend: memoryBackend,
        reme_light_memory_config: config.reme_light_memory_config,
        markdown_memory_config:
          config.markdown_memory_config ?? DEFAULT_MARKDOWN_MEMORY_CONFIG,
        procedural_skill_memory_config:
          config.procedural_skill_memory_config ??
          DEFAULT_PROCEDURAL_SKILL_MEMORY_CONFIG,
        adbpg_memory_config: config.adbpg_memory_config,
        auto_title_config: config.auto_title_config ?? {
          enabled: true,
          timeout_seconds: 30.0,
        },
      });

      // Store original config for complete save
      originalConfigRef.current = config;

      setLanguage(langResp.language);
      setTimezone(tzResp.timezone || "UTC");
    } catch (err) {
      const errMsg =
        err instanceof Error ? err.message : t("agentConfig.loadFailed");
      setError(errMsg);
    } finally {
      setLoading(false);
    }
  }, [form, t, selectedAgent]);

  useEffect(() => {
    fetchConfig();
  }, [fetchConfig]);

  const handleSave = useCallback(async () => {
    try {
      const values = await form.validateFields();
      setSaving(true);

      // Deep-merge nested config objects so that collapsed (unrendered)
      // Collapse panels don't lose their saved values.  Shallow spread
      // would overwrite the entire nested object with only the rendered
      // fields, dropping anything inside a collapsed panel.
      const original = originalConfigRef.current!;
      const formValues = values as AgentsRunningConfig;

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const deepMergeConfig = <T,>(
        base: T | undefined | null,
        override: T | undefined | null,
      ): T | undefined => {
        if (!base) return override ?? undefined;
        if (!override) return base;
        const result = { ...(base as any) };
        for (const key of Object.keys(override as any)) {
          const overrideVal = (override as any)[key];
          const baseVal = (base as any)[key];
          if (
            overrideVal != null &&
            typeof overrideVal === "object" &&
            !Array.isArray(overrideVal) &&
            baseVal != null &&
            typeof baseVal === "object" &&
            !Array.isArray(baseVal)
          ) {
            result[key] = deepMergeConfig(baseVal, overrideVal);
          } else {
            result[key] = overrideVal;
          }
        }
        return result as T;
      };

      const configToSave: AgentsRunningConfig = {
        ...original,
        ...formValues,
        // Deep-merge nested config sections to preserve collapsed fields
        reme_light_memory_config: deepMergeConfig(
          original.reme_light_memory_config,
          formValues.reme_light_memory_config,
        ) as typeof original.reme_light_memory_config,
        light_context_config: deepMergeConfig(
          original.light_context_config,
          formValues.light_context_config,
        ) as typeof original.light_context_config,
        adbpg_memory_config: deepMergeConfig(
          original.adbpg_memory_config,
          formValues.adbpg_memory_config,
        ) as typeof original.adbpg_memory_config,
        markdown_memory_config: deepMergeConfig(
          original.markdown_memory_config,
          formValues.markdown_memory_config,
        ) as typeof original.markdown_memory_config,
        procedural_skill_memory_config: deepMergeConfig(
          original.procedural_skill_memory_config,
          formValues.procedural_skill_memory_config,
        ) as typeof original.procedural_skill_memory_config,
        auto_title_config: deepMergeConfig(
          original.auto_title_config,
          formValues.auto_title_config,
        ) as typeof original.auto_title_config,
        approval_level: approvalLevel,
      };

      await api.updateAgentRunningConfig(configToSave);

      // Update original config after successful save
      originalConfigRef.current = configToSave;
      message.success(t("agentConfig.saveSuccess"));
    } catch (err) {
      if (err instanceof Error && "errorFields" in err) return;
      const errMsg =
        err instanceof Error ? err.message : t("agentConfig.saveFailed");
      message.error(errMsg);
    } finally {
      setSaving(false);
    }
  }, [form, t, selectedAgent, approvalLevel]);

  const handleLanguageChange = useCallback(
    (value: string): void => {
      if (value === language) return;
      Modal.confirm({
        title: t("agentConfig.languageConfirmTitle"),
        content: (
          <span style={{ whiteSpace: "pre-line" }}>
            {t("agentConfig.languageConfirmContent")}
          </span>
        ),
        okText: t("agentConfig.languageConfirmOk"),
        cancelText: t("common.cancel"),
        onOk: async () => {
          setSavingLang(true);
          try {
            const resp = await api.updateAgentLanguage(value);
            setLanguage(resp.language);
            if (resp.copied_files && resp.copied_files.length > 0) {
              message.success(
                t("agentConfig.languageSaveSuccessWithFiles", {
                  count: resp.copied_files.length,
                }),
              );
            } else {
              message.success(t("agentConfig.languageSaveSuccess"));
            }
          } catch (err) {
            const errMsg =
              err instanceof Error
                ? err.message
                : t("agentConfig.languageSaveFailed");
            message.error(errMsg);
          } finally {
            setSavingLang(false);
          }
        },
      });
    },
    [language, t],
  );

  const handleTimezoneChange = useCallback(
    async (value: string) => {
      if (value === timezone) return;
      setSavingTimezone(true);
      try {
        await api.updateUserTimezone(value);
        setTimezone(value);
        message.success(t("agentConfig.timezoneSaveSuccess"));
      } catch (err) {
        const errMsg =
          err instanceof Error
            ? err.message
            : t("agentConfig.timezoneSaveFailed");
        message.error(errMsg);
      } finally {
        setSavingTimezone(false);
      }
    },
    [timezone, t],
  );

  return {
    form,
    loading,
    saving,
    error,
    language,
    savingLang,
    timezone,
    savingTimezone,
    approvalLevel,
    setApprovalLevel,
    fetchConfig,
    handleSave,
    handleLanguageChange,
    handleTimezoneChange,
  };
}
