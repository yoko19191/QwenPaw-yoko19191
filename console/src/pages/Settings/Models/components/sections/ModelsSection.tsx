import React, { useState, useEffect, useMemo, useRef } from "react";
import {
  ArrowDownOutlined,
  ArrowUpOutlined,
  DeleteOutlined,
  HolderOutlined,
  PlusOutlined,
  SaveOutlined,
} from "@ant-design/icons";
import { Select, Button, Tooltip } from "@agentscope-ai/design";
import type {
  ActiveModelsInfo,
  ModelSlotConfig,
  ModelSlotRequest,
} from "../../../../../api/types";
import api from "../../../../../api";
import { useTranslation } from "react-i18next";
import { useAppMessage } from "../../../../../hooks/useAppMessage";
import { confirmFreeModelSwitch } from "@/utils/freeModelSwitchWarning";
import styles from "../../index.module.less";

interface ModelsSectionProps {
  providers: Array<{
    id: string;
    name: string;
    models?: Array<{ id: string; name: string; is_free?: boolean }>;
    extra_models?: Array<{ id: string; name: string; is_free?: boolean }>;
    base_url?: string;
    api_key?: string;
    is_custom: boolean;
    is_local?: boolean;
    require_api_key?: boolean;
  }>;
  activeModels: ActiveModelsInfo | null;
  onSaved: () => void;
}

interface SlotRow {
  id: string;
  provider_id?: string;
  model?: string;
}

let rowCounter = 0;

const makeRowId = () => {
  rowCounter += 1;
  return `llm-slot-${Date.now()}-${rowCounter}`;
};

const slotKey = (slot: Pick<ModelSlotConfig, "provider_id" | "model">) =>
  `${slot.provider_id}::${slot.model}`;

const toRows = (
  activeModels: ModelsSectionProps["activeModels"],
): SlotRow[] => {
  const slots: ModelSlotConfig[] = [];
  const primary = activeModels?.active_llm;
  if (primary?.provider_id && primary.model) {
    slots.push({ provider_id: primary.provider_id, model: primary.model });
  }
  for (const fallback of activeModels?.fallback_llms ?? []) {
    if (fallback.provider_id && fallback.model) {
      slots.push({
        provider_id: fallback.provider_id,
        model: fallback.model,
      });
    }
  }
  if (slots.length === 0) {
    return [{ id: makeRowId() }];
  }
  const seen = new Set<string>();
  return slots
    .filter((slot) => {
      const key = slotKey(slot);
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .map((slot) => ({ ...slot, id: makeRowId() }));
};

const reorderRows = (rows: SlotRow[], fromIndex: number, toIndex: number) => {
  const next = [...rows];
  const [moved] = next.splice(fromIndex, 1);
  next.splice(toIndex, 0, moved);
  return next;
};

const selectFilter = (
  input: string,
  option?: { searchText?: string; label?: React.ReactNode },
) => {
  const haystack =
    option?.searchText ??
    (typeof option?.label === "string" ? option.label : "");
  return haystack.toLowerCase().includes(input.toLowerCase());
};

const renderSelectLabel = (text: string, tooltip: string) => (
  <Tooltip title={tooltip}>
    <span className={styles.fallbackSelectLabel}>{text}</span>
  </Tooltip>
);

export const ModelsSection = React.memo(function ModelsSection({
  providers,
  activeModels,
  onSaved,
}: ModelsSectionProps) {
  const { t } = useTranslation();
  const [saving, setSaving] = useState(false);
  const [rows, setRows] = useState<SlotRow[]>(() => toRows(activeModels));
  const [dirty, setDirty] = useState(false);
  const [dragOverId, setDragOverId] = useState<string | null>(null);
  const dragItemIdRef = useRef<string | null>(null);
  const { message } = useAppMessage();

  const currentSlot = activeModels?.active_llm;

  const eligible = useMemo(
    () =>
      providers.filter((p) => {
        const hasModels =
          (p.models?.length ?? 0) + (p.extra_models?.length ?? 0) > 0;
        if (!hasModels) return false;
        if (p.require_api_key === false) return !!p.base_url;
        if (p.is_custom) return !!p.base_url;
        if (p.require_api_key ?? true) return !!p.api_key;
        return true;
      }),
    [providers],
  );

  useEffect(() => {
    setRows(toRows(activeModels));
    setDirty(false);
  }, [
    currentSlot?.provider_id,
    currentSlot?.model,
    activeModels?.fallback_llms,
  ]);

  const getModelOptions = (providerId?: string) => {
    const chosenProvider = providers.find((p) => p.id === providerId);
    return [
      ...(chosenProvider?.models ?? []),
      ...(chosenProvider?.extra_models ?? []),
    ];
  };

  const updateRow = (id: string, patch: Partial<SlotRow>) => {
    setRows((prev) =>
      prev.map((row) => (row.id === id ? { ...row, ...patch } : row)),
    );
    setDirty(true);
  };

  const handleProviderChange = (id: string, pid: string) => {
    updateRow(id, { provider_id: pid, model: undefined });
  };

  const handleModelChange = (id: string, model: string) => {
    updateRow(id, { model });
  };

  const addFallbackRow = () => {
    setRows((prev) => [...prev, { id: makeRowId() }]);
    setDirty(true);
  };

  const removeRow = (id: string) => {
    setRows((prev) => {
      if (prev.length <= 1) {
        return [{ id: makeRowId() }];
      }
      return prev.filter((row) => row.id !== id);
    });
    setDirty(true);
  };

  const moveRow = (id: string, direction: -1 | 1) => {
    setRows((prev) => {
      const index = prev.findIndex((row) => row.id === id);
      const nextIndex = index + direction;
      if (index < 0 || nextIndex < 0 || nextIndex >= prev.length) return prev;
      return reorderRows(prev, index, nextIndex);
    });
    setDirty(true);
  };

  const handleDragStart = (id: string) => {
    dragItemIdRef.current = id;
  };

  const handleDragOver = (event: React.DragEvent, id: string) => {
    event.preventDefault();
    setDragOverId(id);
  };

  const handleDrop = (id: string) => {
    const fromId = dragItemIdRef.current;
    dragItemIdRef.current = null;
    setDragOverId(null);
    if (!fromId || fromId === id) return;
    setRows((prev) => {
      const fromIndex = prev.findIndex((row) => row.id === fromId);
      const toIndex = prev.findIndex((row) => row.id === id);
      if (fromIndex < 0 || toIndex < 0) return prev;
      return reorderRows(prev, fromIndex, toIndex);
    });
    setDirty(true);
  };

  const completeRows = rows.filter((row) => row.provider_id && row.model);
  const hasIncompleteRow = rows.some(
    (row) => Boolean(row.provider_id) !== Boolean(row.model),
  );
  const duplicateCount =
    completeRows.length -
    new Set(
      completeRows.map((row) =>
        slotKey({
          provider_id: row.provider_id || "",
          model: row.model || "",
        }),
      ),
    ).size;

  const handleSave = async () => {
    const primary = rows[0];
    if (!primary?.provider_id || !primary.model) return;
    if (hasIncompleteRow || duplicateCount > 0) {
      message.error(t("models.fallbackOrderInvalid"));
      return;
    }

    for (const row of completeRows) {
      const selectedProvider = providers.find((p) => p.id === row.provider_id);
      const selectedModelInfo = getModelOptions(row.provider_id).find(
        (model) => model.id === row.model,
      );
      if (!selectedProvider || !selectedModelInfo) continue;
      const confirmed = await confirmFreeModelSwitch({
        provider: selectedProvider,
        model: selectedModelInfo,
        t,
      });
      if (!confirmed) return;
    }

    const body: ModelSlotRequest = {
      provider_id: primary.provider_id,
      model: primary.model,
      scope: "global",
      fallback_llms: completeRows.slice(1).map((row) => ({
        provider_id: row.provider_id || "",
        model: row.model || "",
      })),
    };

    setSaving(true);
    try {
      await api.setActiveLlm(body);
      message.success(t("models.llmModelUpdated"));
      setDirty(false);
      onSaved();
    } catch (error) {
      const errMsg =
        error instanceof Error ? error.message : t("models.failedToSave");
      message.error(errMsg);
    } finally {
      setSaving(false);
    }
  };

  const canSave =
    dirty &&
    !!rows[0]?.provider_id &&
    !!rows[0]?.model &&
    !hasIncompleteRow &&
    duplicateCount === 0;

  return (
    <div className={styles.defaultLlmBody}>
      <p className={styles.llmDescription}>{t("models.llmDescription")}</p>

      <div className={styles.fallbackList}>
        {rows.map((row, index) => {
          const modelOptions = getModelOptions(row.provider_id);
          const hasModels = modelOptions.length > 0;
          const isDragOver = dragOverId === row.id;
          return (
            <div
              key={row.id}
              className={[
                styles.fallbackRow,
                isDragOver ? styles.fallbackRowDragOver : "",
              ].join(" ")}
              onDragOver={(event) => handleDragOver(event, row.id)}
              onDrop={() => handleDrop(row.id)}
              onDragEnd={() => {
                dragItemIdRef.current = null;
                setDragOverId(null);
              }}
            >
              <div
                className={styles.fallbackDragHandle}
                draggable={rows.length > 1}
                onDragStart={() => handleDragStart(row.id)}
                title={t("models.dragToReorder")}
              >
                <HolderOutlined />
              </div>
              <div className={styles.fallbackRank}>
                {index === 0
                  ? t("models.primaryModel")
                  : t("models.fallbackModel", { index })}
              </div>
              <div className={styles.fallbackSelects}>
                <Select
                  style={{ width: "100%" }}
                  placeholder={t("models.selectProvider")}
                  value={row.provider_id}
                  onChange={(pid) => handleProviderChange(row.id, pid)}
                  showSearch
                  filterOption={selectFilter}
                  options={eligible.map((p) => ({
                    value: p.id,
                    searchText: `${p.name} ${p.id}`,
                    label: renderSelectLabel(p.name, `${p.name} (${p.id})`),
                  }))}
                />
                <Select
                  style={{ width: "100%" }}
                  placeholder={
                    hasModels
                      ? t("models.selectModel")
                      : t("models.addModelFirst")
                  }
                  disabled={!hasModels}
                  showSearch
                  filterOption={selectFilter}
                  value={row.model}
                  onChange={(model) => handleModelChange(row.id, model)}
                  options={modelOptions.map((m) => ({
                    value: m.id,
                    searchText: `${m.name} ${m.id}`,
                    label: renderSelectLabel(
                      `${m.name} (${m.id})`,
                      `${m.name} (${m.id})`,
                    ),
                  }))}
                />
              </div>
              <div className={styles.fallbackRowActions}>
                <Button
                  icon={<ArrowUpOutlined />}
                  disabled={index === 0}
                  onClick={() => moveRow(row.id, -1)}
                  title={t("models.moveUp")}
                />
                <Button
                  icon={<ArrowDownOutlined />}
                  disabled={index === rows.length - 1}
                  onClick={() => moveRow(row.id, 1)}
                  title={t("models.moveDown")}
                />
                <Button
                  icon={<DeleteOutlined />}
                  disabled={rows.length === 1 && index === 0}
                  onClick={() => removeRow(row.id)}
                  title={t("models.removeFallback")}
                />
              </div>
            </div>
          );
        })}
      </div>

      {duplicateCount > 0 && (
        <div className={styles.fallbackError}>
          {t("models.fallbackDuplicate")}
        </div>
      )}
      {hasIncompleteRow && (
        <div className={styles.fallbackError}>
          {t("models.fallbackIncomplete")}
        </div>
      )}

      <div className={styles.fallbackFooter}>
        <Button icon={<PlusOutlined />} onClick={addFallbackRow}>
          {t("models.addFallback")}
        </Button>
        <Button
          type="primary"
          loading={saving}
          disabled={!canSave}
          onClick={handleSave}
          icon={<SaveOutlined />}
        >
          {t("models.saveFallbackOrder")}
        </Button>
      </div>
    </div>
  );
});
