# -*- coding: utf-8 -*-
"""Single source of truth for built-in channel metadata."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional, Type

from pydantic import BaseModel

from ...config.config import (
    ConsoleConfig,
    DingTalkConfig,
    DiscordConfig,
    FeishuConfig,
    IMessageChannelConfig,
    MatrixConfig,
    MattermostConfig,
    MQTTConfig,
    OneBotConfig,
    QQConfig,
    SIPChannelConfig,
    TelegramConfig,
    VoiceChannelConfig,
    WeChatConfig,
    WecomConfig,
    XiaoYiConfig,
    YuanbaoConfig,
)
from .registry import BUILTIN_CHANNEL_KEYS


class ChannelMetadataResponse(BaseModel):
    key: str
    label: str
    order: int
    color: str = "default"
    is_builtin: bool = False
    supports_qrcode: bool = False
    supports_health: bool = True
    docs_url: Optional[str] = None


@dataclass(frozen=True)
class ChannelMetadata:
    key: str
    label: str
    order: int
    color: str
    config_model: Type[BaseModel] | None = None
    docs_url: str | None = None
    supports_health: bool = True

    def public(self, *, supports_qrcode: bool = False) -> ChannelMetadataResponse:
        return ChannelMetadataResponse(
            key=self.key,
            label=self.label,
            order=self.order,
            color=self.color,
            is_builtin=self.key in BUILTIN_CHANNEL_KEYS,
            supports_qrcode=supports_qrcode,
            supports_health=self.supports_health,
            docs_url=self.docs_url,
        )


_BUILTIN_METADATA: dict[str, ChannelMetadata] = {
    "console": ChannelMetadata("console", "Console", 10, "green", ConsoleConfig),
    "dingtalk": ChannelMetadata(
        "dingtalk",
        "DingTalk",
        20,
        "green",
        DingTalkConfig,
    ),
    "feishu": ChannelMetadata("feishu", "Feishu", 30, "volcano", FeishuConfig),
    "imessage": ChannelMetadata(
        "imessage",
        "iMessage",
        40,
        "geekblue",
        IMessageChannelConfig,
    ),
    "discord": ChannelMetadata("discord", "Discord", 50, "blue", DiscordConfig),
    "telegram": ChannelMetadata(
        "telegram",
        "Telegram",
        60,
        "geekblue",
        TelegramConfig,
    ),
    "qq": ChannelMetadata("qq", "QQ", 70, "gold", QQConfig),
    "wechat": ChannelMetadata("wechat", "WeChat", 80, "lime", WeChatConfig),
    "wecom": ChannelMetadata("wecom", "WeCom", 90, "olive", WecomConfig),
    "onebot": ChannelMetadata("onebot", "OneBot", 100, "purple", OneBotConfig),
    "yuanbao": ChannelMetadata("yuanbao", "Yuanbao", 110, "lime", YuanbaoConfig),
    "mattermost": ChannelMetadata(
        "mattermost",
        "Mattermost",
        120,
        "purple",
        MattermostConfig,
    ),
    "mqtt": ChannelMetadata("mqtt", "MQTT", 130, "orange", MQTTConfig),
    "matrix": ChannelMetadata("matrix", "Matrix", 140, "red", MatrixConfig),
    "voice": ChannelMetadata("voice", "Twilio", 150, "geekblue", VoiceChannelConfig),
    "sip": ChannelMetadata("sip", "SIP", 160, "cyan", SIPChannelConfig),
    "xiaoyi": ChannelMetadata("xiaoyi", "XiaoYi", 170, "cyan", XiaoYiConfig),
}


def get_channel_metadata(key: str) -> ChannelMetadata | None:
    return _BUILTIN_METADATA.get(key)


def get_channel_config_model(key: str) -> Type[BaseModel] | None:
    meta = get_channel_metadata(key)
    return meta.config_model if meta else None


def list_channel_metadata(
    available_keys: Iterable[str],
    *,
    qrcode_keys: Iterable[str] = (),
) -> list[ChannelMetadataResponse]:
    qrcode_key_set = set(qrcode_keys)
    items: list[ChannelMetadataResponse] = []
    for index, key in enumerate(available_keys):
        meta = _BUILTIN_METADATA.get(key)
        if meta is None:
            meta = ChannelMetadata(
                key=key,
                label=_format_custom_channel_key(key),
                order=10000 + index,
                color="default",
                config_model=None,
            )
        items.append(meta.public(supports_qrcode=key in qrcode_key_set))
    return sorted(items, key=lambda item: (item.order, item.key))


def _format_custom_channel_key(key: str) -> str:
    return " ".join(part.capitalize() for part in key.replace("-", "_").split("_"))
