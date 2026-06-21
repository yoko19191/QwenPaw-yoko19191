import { useState, useEffect, useCallback, useMemo } from "react";
import api from "../../../api";
import type { ChannelMetadata } from "../../../api/types";
import { useAgentStore } from "../../../stores/agentStore";

export function useChannels() {
  const { selectedAgent } = useAgentStore();
  const [channels, setChannels] = useState<
    Record<string, Record<string, unknown>>
  >({});
  const [channelTypes, setChannelTypes] = useState<string[]>([]);
  const [metadataByKey, setMetadataByKey] = useState<
    Record<string, ChannelMetadata>
  >({});
  const [loading, setLoading] = useState(true);

  const fetchChannels = useCallback(async () => {
    setLoading(true);
    try {
      const [data, types, metadata] = await Promise.all([
        api.listChannels(),
        api.listChannelTypes(),
        api.listChannelMetadata().catch(() => []),
      ]);
      if (data)
        setChannels(data as unknown as Record<string, Record<string, unknown>>);
      if (types) setChannelTypes(types);
      setMetadataByKey(
        Object.fromEntries((metadata || []).map((item) => [item.key, item])),
      );
    } catch (error) {
      console.error("❌ Failed to load channels:", error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchChannels();
  }, [fetchChannels, selectedAgent]);

  // Built-in channels come first (in a fixed order), then custom channels
  const builtinOrder = useMemo(
    () => [
      "console",
      "dingtalk",
      "feishu",
      "imessage",
      "discord",
      "telegram",
      "qq",
      "wechat",
      "wecom",
      "yuanbao",
      "mattermost",
      "mqtt",
      "matrix",
      "voice",
      "sip",
      "xiaoyi",
      "onebot",
    ],
    [],
  );

  const orderedKeys = useMemo(() => {
    const metadataKeys = Object.values(metadataByKey)
      .sort((a, b) => a.order - b.order || a.key.localeCompare(b.key))
      .map((item) => item.key)
      .filter((key) => channelTypes.includes(key));
    if (metadataKeys.length > 0) {
      return [
        ...metadataKeys,
        ...channelTypes.filter((key) => !metadataKeys.includes(key)),
      ];
    }
    return [
      ...builtinOrder.filter((k) => channelTypes.includes(k)),
      ...channelTypes.filter((k) => !builtinOrder.includes(k)),
    ];
  }, [builtinOrder, channelTypes, metadataByKey]);

  const isBuiltin = useCallback(
    (key: string) =>
      metadataByKey[key]?.is_builtin ?? Boolean(channels[key]?.isBuiltin),
    [channels, metadataByKey],
  );

  return {
    channels,
    channelTypes,
    orderedKeys,
    isBuiltin,
    metadataByKey,
    loading,
    fetchChannels,
  };
}
