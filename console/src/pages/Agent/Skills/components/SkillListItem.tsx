import { Button, Checkbox, Switch } from "@agentscope-ai/design";
import { useTranslation } from "react-i18next";
import type { SkillSpec } from "../../../../api/types";
import { isSkillBuiltin } from "@/utils/skill";
import { getSkillVisual } from "./SkillCard";
import dayjs from "dayjs";
import relativeTime from "dayjs/plugin/relativeTime";
import styles from "../index.module.less";

dayjs.extend(relativeTime);

interface SkillListItemProps {
  skill: SkillSpec;
  batchModeEnabled: boolean;
  isSelected: boolean;
  onSelect: () => void;
  onClick: () => void;
  onToggleEnabled: () => Promise<void>;
  onDelete: () => void;
  onArchive?: () => void;
  onTogglePinned?: () => void;
}

export function SkillListItem({
  skill,
  batchModeEnabled,
  isSelected,
  onSelect,
  onClick,
  onToggleEnabled,
  onDelete,
  onArchive,
  onTogglePinned,
}: SkillListItemProps) {
  const { t } = useTranslation();
  const isBuiltin = isSkillBuiltin(skill.source);
  const channels = (skill.channels || ["all"])
    .map((ch) => (ch === "all" ? t("skills.allChannels") : ch))
    .join(", ");

  return (
    <div
      className={`${styles.skillListItem} ${
        isSelected ? styles.selectedListItem : ""
      }`}
      onClick={() => {
        if (batchModeEnabled) onSelect();
        else onClick();
      }}
    >
      {batchModeEnabled && (
        <Checkbox
          checked={isSelected}
          onClick={(e) => {
            e.stopPropagation();
            onSelect();
          }}
        />
      )}
      <div className={styles.listItemLeft}>
        <span className={styles.fileIcon}>
          {getSkillVisual(skill.name, skill.emoji)}
        </span>
        <div className={styles.listItemInfo}>
          <div className={styles.listItemHeader}>
            <span className={styles.skillTitle}>{skill.name}</span>
            <span className={styles.typeBadge}>
              {isBuiltin ? t("skills.builtin") : t("skills.custom")}
            </span>
            <span className={styles.channelBadge}>{channels}</span>
            {skill.last_updated && (
              <span className={styles.listItemTime}>
                {t("skills.lastUpdated")} {dayjs(skill.last_updated).fromNow()}
              </span>
            )}
          </div>
          <p className={styles.listItemDesc}>{skill.description || "-"}</p>
          <div className={styles.listItemUsage}>
            {t("skills.usage")}: {skill.use_count || 0}
            {skill.last_used_at
              ? ` · ${dayjs(skill.last_used_at).fromNow()}`
              : ""}
            {skill.pinned ? ` · ${t("skills.pinned")}` : ""}
          </div>
          {!!skill.tags?.length && (
            <div className={styles.listItemTags}>
              {skill.tags.map((tag) => (
                <span key={tag} className={styles.tagChip}>
                  {tag}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>
      <div className={styles.listItemRight}>
        <span onClick={(e) => e.stopPropagation()}>
          <Switch
            checked={skill.enabled}
            disabled={batchModeEnabled}
            onChange={onToggleEnabled}
          />
        </span>
        <Button
          danger
          disabled={batchModeEnabled}
          onClick={(e) => {
            e.stopPropagation();
            onDelete();
          }}
        >
          {t("common.delete")}
        </Button>
        {onArchive && (
          <Button
            disabled={batchModeEnabled}
            onClick={(e) => {
              e.stopPropagation();
              onArchive();
            }}
          >
            {t("skills.archive")}
          </Button>
        )}
        {onTogglePinned && (
          <Button
            disabled={batchModeEnabled}
            onClick={(e) => {
              e.stopPropagation();
              onTogglePinned();
            }}
          >
            {skill.pinned ? t("skills.unpin") : t("skills.pin")}
          </Button>
        )}
      </div>
    </div>
  );
}
