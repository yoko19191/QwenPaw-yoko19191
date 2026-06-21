import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import api from "../../../api";
import type { InboxEvent } from "../../../api/modules/console";
import type { HarvestViewOutput } from "../../../api/types";
import { useAgentStore } from "../../../stores/agentStore";
import {
  DEFAULT_AGENT_ID,
  getAgentDisplayName,
} from "../../../utils/agentDisplayName";
import type {
  CreateHarvestValues,
  HarvestInstance,
  InboxSummary,
  PushMessage,
} from "../types";

const PUSH_POLLING_INTERVAL_MS = 6000;

const mapPriority = (text: string): "low" | "normal" | "high" | "urgent" => {
  if (text.includes("❌") || text.toLowerCase().includes("error")) {
    return "high";
  }
  return "normal";
};

const stripExecutionTimeText = (text: string): string =>
  text.replace(/\s*duration=\d+ms\.?/gi, "").trim();

const getHeartbeatSummary = (status?: string): string => {
  const normalizedStatus = (status || "").toLowerCase();
  if (normalizedStatus === "success") {
    return "Heartbeat 执行成功";
  }
  if (normalizedStatus === "timeout") {
    return "Heartbeat 执行超时";
  }
  if (normalizedStatus === "cancelled") {
    return "Heartbeat 已取消";
  }
  return "Heartbeat 执行失败";
};

const mapEventToPushMessage = (
  event: InboxEvent,
  resolveAgentName: (agentId: string) => string,
): PushMessage => ({
  id: event.id,
  channelType:
    event.source_type === "heartbeat"
      ? "heartbeat"
      : event.source_type === "harvest"
      ? "harvest"
      : event.source_type === "cron"
      ? "wechat"
      : "email",
  channelName:
    event.source_type === "heartbeat"
      ? "Heartbeat"
      : event.source_type === "harvest"
      ? "Harvest"
      : event.source_type === "cron"
      ? "Cron"
      : "System",
  title: event.title,
  content:
    event.source_type === "heartbeat"
      ? getHeartbeatSummary(event.status)
      : stripExecutionTimeText(event.body),
  sender: {
    userId: event.agent_id || "default",
    username: resolveAgentName(event.agent_id || DEFAULT_AGENT_ID),
  },
  createdAt: new Date((event.created_at || Date.now() / 1000) * 1000),
  read: Boolean(event.read),
  metadata: {
    priority:
      event.severity === "error" || event.status === "error"
        ? "high"
        : mapPriority(event.body),
    sourceType: event.source_type,
    sourceId: event.source_id,
    eventType: event.event_type,
    status: event.status,
    severity: event.severity,
    trigger:
      typeof event.payload?.trigger === "string"
        ? (event.payload.trigger as string)
        : undefined,
    agentId: event.agent_id,
    payload:
      event.payload && typeof event.payload === "object"
        ? event.payload
        : undefined,
  },
});

const mapHarvestView = (item: HarvestViewOutput): HarvestInstance => {
  const schedule = item.schedule || { type: "cron", cron: "", timezone: "UTC" };
  const nextRun =
    item.next_run_at ||
    (schedule.type === "once" ? schedule.run_at : undefined) ||
    new Date().toISOString();
  return {
    id: item.id,
    name: item.name,
    templateId: item.template_id,
    emoji: item.emoji,
    schedule: {
      cron: schedule.type === "cron" ? schedule.cron : "once",
      timezone: schedule.timezone || "UTC",
      nextRun: new Date(nextRun),
    },
    status: item.status,
    lastGenerated: item.last_generated
      ? {
          timestamp: new Date(item.last_generated.timestamp),
          success: item.last_generated.success,
        }
      : undefined,
    stats: {
      totalGenerated: item.stats.total_generated,
      successRate: item.stats.success_rate,
      consecutiveDays: item.stats.consecutive_days,
    },
  };
};

const buildHarvestPrompt = (values: CreateHarvestValues): string => {
  const keywords = values.keywords.trim();
  return [
    `Create an Inbox harvest for: ${keywords}.`,
    "Return a concise markdown briefing with key updates, why they matter, and recommended next actions.",
    `Template: ${values.templateId}. Frequency: ${values.frequency}.`,
  ].join("\n");
};

export const useInboxData = () => {
  const { t } = useTranslation();
  const agents = useAgentStore((state) => state.agents);
  const agentsById = useMemo(
    () => new Map(agents.map((agent) => [agent.id, agent])),
    [agents],
  );
  const resolveAgentName = useCallback(
    (agentId: string) => {
      const normalizedId = agentId || DEFAULT_AGENT_ID;
      const agent = agentsById.get(normalizedId);
      if (agent) {
        return getAgentDisplayName(agent, t);
      }
      if (normalizedId === DEFAULT_AGENT_ID) {
        return t("agent.defaultDisplayName");
      }
      return normalizedId;
    },
    [agentsById, t],
  );
  const resolveAgentNameRef = useRef(resolveAgentName);
  resolveAgentNameRef.current = resolveAgentName;
  const [summary, setSummary] = useState<InboxSummary>({
    approvals: { total: 0, urgent: 0 },
    pushMessages: { total: 0, unread: 0 },
    harvests: { total: 0, active: 0 },
  });
  const [pushMessages, setPushMessages] = useState<PushMessage[]>([]);
  const pushMessagesRef = useRef(pushMessages);
  pushMessagesRef.current = pushMessages;
  const [harvests, setHarvests] = useState<HarvestInstance[]>([]);

  const loadHarvests = useCallback(async () => {
    try {
      const items = await api.listHarvests();
      const nextHarvests = (items || []).map(mapHarvestView);
      setHarvests(nextHarvests);
      setSummary((prev) => ({
        ...prev,
        harvests: {
          total: nextHarvests.length,
          active: nextHarvests.filter((item) => item.status === "active")
            .length,
        },
      }));
    } catch (error) {
      console.error("Failed to fetch harvest data", error);
    }
  }, []);

  const loadPushMessages = useCallback(async () => {
    try {
      const res = await api.getInboxEvents({ limit: 200 });
      const events = [...(res?.events || [])].filter((event) =>
        ["cron", "heartbeat", "harvest"].includes(event.source_type),
      );
      events.sort((a, b) => (b.created_at || 0) - (a.created_at || 0));
      const nextItems: PushMessage[] = events.map((event) =>
        mapEventToPushMessage(event, resolveAgentNameRef.current),
      );
      setPushMessages(nextItems);
      setSummary((prev) => ({
        ...prev,
        pushMessages: {
          total: nextItems.length,
          unread: nextItems.filter((m) => !m.read).length,
        },
      }));
    } catch (error) {
      console.error("Failed to fetch push inbox data", error);
    }
  }, []);

  useEffect(() => {
    void loadPushMessages();
    void loadHarvests();

    let timer: number | null = null;

    const startPolling = () => {
      if (timer) return;
      timer = window.setInterval(() => {
        void loadPushMessages();
        void loadHarvests();
      }, PUSH_POLLING_INTERVAL_MS);
    };

    const stopPolling = () => {
      if (timer) {
        window.clearInterval(timer);
        timer = null;
      }
    };

    const handleVisibilityChange = () => {
      if (document.visibilityState === "visible") {
        void loadPushMessages();
        void loadHarvests();
        startPolling();
      } else {
        stopPolling();
      }
    };

    if (document.visibilityState === "visible") {
      startPolling();
    }

    document.addEventListener("visibilitychange", handleVisibilityChange);
    return () => {
      stopPolling();
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [loadHarvests, loadPushMessages]);

  const markMessageAsRead = useCallback((messageId: string) => {
    void api.markInboxRead({ event_ids: [messageId] });
    setPushMessages((prev) =>
      prev.map((message) =>
        message.id === messageId ? { ...message, read: true } : message,
      ),
    );
    setSummary((prev) => ({
      ...prev,
      pushMessages: {
        ...prev.pushMessages,
        unread: Math.max(prev.pushMessages.unread - 1, 0),
      },
    }));
  }, []);

  const markAllMessagesAsRead = useCallback(async (): Promise<number> => {
    const unreadIds = pushMessagesRef.current
      .filter((message) => !message.read)
      .map((m) => m.id);
    if (!unreadIds.length) {
      return 0;
    }
    await api.markInboxRead({ all: true });
    setPushMessages((prev) =>
      prev.map((message) =>
        message.read ? message : { ...message, read: true },
      ),
    );
    setSummary((prev) => ({
      ...prev,
      pushMessages: {
        ...prev.pushMessages,
        unread: 0,
      },
    }));
    return unreadIds.length;
  }, []);

  const deleteMessages = useCallback(async (messageIds: string[]) => {
    const ids = Array.from(
      new Set(messageIds.map((id) => id.trim()).filter(Boolean)),
    );
    if (!ids.length) return 0;
    const idSet = new Set(ids);
    await Promise.allSettled(ids.map((id) => api.deleteInboxEvent(id)));
    let deleted = 0;
    let unreadDeleted = 0;
    setPushMessages((prev) => {
      const remaining: PushMessage[] = [];
      for (const message of prev) {
        if (idSet.has(message.id)) {
          deleted += 1;
          if (!message.read) unreadDeleted += 1;
          continue;
        }
        remaining.push(message);
      }
      return remaining;
    });
    setSummary((prev) => ({
      ...prev,
      pushMessages: {
        total: Math.max(prev.pushMessages.total - deleted, 0),
        unread: Math.max(prev.pushMessages.unread - unreadDeleted, 0),
      },
    }));
    return deleted;
  }, []);

  const deleteMessage = useCallback(
    (messageId: string) => {
      void deleteMessages([messageId]);
    },
    [deleteMessages],
  );

  const createHarvest = useCallback(
    async (values: CreateHarvestValues): Promise<HarvestInstance> => {
      const created = await api.createHarvest({
        name: values.name.trim(),
        template_id: values.templateId,
        emoji: values.emoji,
        enabled: true,
        prompt: buildHarvestPrompt(values),
        schedule: {
          type: "cron",
          cron: values.schedule.cron,
          timezone: values.schedule.timezone,
        },
        target: {
          channel: "console",
          user_id: "harvest",
          session_id: "console:harvest",
        },
        runtime: {
          max_concurrency: 1,
          timeout_seconds: 240,
          misfire_grace_seconds: 60,
        },
      });
      const mapped = mapHarvestView(created);
      await loadHarvests();
      return mapped;
    },
    [loadHarvests],
  );

  const triggerHarvest = useCallback(
    async (harvestId: string) => {
      await api.runHarvest(harvestId);
      await loadHarvests();
      window.setTimeout(() => {
        void loadPushMessages();
      }, 1500);
    },
    [loadHarvests, loadPushMessages],
  );

  return {
    summary,
    pushMessages,
    harvests,
    markMessageAsRead,
    markAllMessagesAsRead,
    deleteMessage,
    deleteMessages,
    createHarvest,
    triggerHarvest,
    refreshPushMessages: loadPushMessages,
    refreshHarvests: loadHarvests,
  };
};
