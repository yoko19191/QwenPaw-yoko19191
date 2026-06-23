# -*- coding: utf-8 -*-
"""A Manager class to handle all providers, including built-in and custom ones.
It provides a unified interface to manage providers, such as listing available
providers, adding/removing custom providers, and fetching provider details."""

import asyncio
import os
from typing import Dict, List
import logging
import json

from pydantic import BaseModel

from agentscope.model import ChatModelBase
from agentscope_runtime.engine.schemas.exception import (
    ModelNotFoundException,
)

from ..constant import SECRET_DIR
from ..config.config import ModelSlotConfig
from ..exceptions import ProviderError
from .anthropic_provider import AnthropicProvider
from .gemini_provider import GeminiProvider
from .ollama_provider import OllamaProvider
from .openai_provider import (
    OpenAIProvider,
    OpenCodeProvider,
    KiloProvider,
)
from .lmstudio_provider import LMStudioProvider
from .models_dev import discover_models_with_models_dev_fallback
from .provider import (
    ModelInfo,
    Provider,
    ProviderInfo,
)
from .openrouter_provider import OpenRouterProvider
from ..security.secret_store import (
    PROVIDER_SECRET_FIELDS,
    decrypt_dict_fields,
    encrypt_dict_fields,
    is_encrypted,
)

logger = logging.getLogger(__name__)

# -------------------------------------------------------
# Built-in provider definitions. Model lists are discovered dynamically.
# -------------------------------------------------------

PROVIDER_MODELSCOPE = OpenAIProvider(
    id="modelscope",
    name="ModelScope",
    base_url="https://api-inference.modelscope.cn/v1",
    api_key_prefix="ms",
    models=[],
    freeze_url=True,
)

PROVIDER_DASHSCOPE = OpenAIProvider(
    id="dashscope",
    name="DashScope",
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    api_key_prefix="sk",
    models=[],
    provider_group="aliyun",
    provider_group_name="Aliyun",
    provider_variant="dashscope",
    meta={
        "base_url_options": [
            {
                "label": "China (Beijing)",
                "value": "https://dashscope.aliyuncs.com/" "compatible-mode/v1",
            },
            {
                "label": "International (Singapore)",
                "value": "https://dashscope-intl.aliyuncs.com/" "compatible-mode/v1",
            },
            {
                "label": "US (Virginia)",
                "value": "https://dashscope-us.aliyuncs.com/" "compatible-mode/v1",
            },
        ],
    },
)

PROVIDER_ALIYUN_CODINGPLAN = OpenAIProvider(
    id="aliyun-codingplan",
    name="Aliyun Coding Plan (China)",
    base_url="https://coding.dashscope.aliyuncs.com/v1",
    api_key_prefix="sk-sp",
    models=[],
    support_connection_check=False,
    freeze_url=True,
    provider_group="aliyun",
    provider_group_name="Aliyun",
    provider_variant="coding_plan_cn",
)

PROVIDER_ALIYUN_CODINGPLAN_INTL = OpenAIProvider(
    id="aliyun-codingplan-intl",
    name="Aliyun Coding Plan (International)",
    base_url="https://coding-intl.dashscope.aliyuncs.com/v1",
    api_key_prefix="sk-sp",
    models=[],
    support_connection_check=False,
    freeze_url=True,
    provider_group="aliyun",
    provider_group_name="Aliyun",
    provider_variant="coding_plan_intl",
)

PROVIDER_ALIYUN_TOKENPLAN = OpenAIProvider(
    id="aliyun-tokenplan",
    name="Aliyun Token Plan",
    base_url=("https://token-plan.cn-beijing.maas.aliyuncs.com/" "compatible-mode/v1"),
    api_key_prefix="sk-sp",
    models=[],
    support_connection_check=False,
    freeze_url=True,
    provider_group="aliyun",
    provider_group_name="Aliyun",
    provider_variant="token_plan",
)

PROVIDER_ALIYUN_TOKENPLAN_INTL = OpenAIProvider(
    id="aliyun-tokenplan-intl",
    name="Aliyun Token Plan (International)",
    base_url=(
        "https://token-plan.ap-southeast-1.maas.aliyuncs.com/" "compatible-mode/v1"
    ),
    api_key_prefix="sk-sp",
    models=[],
    support_connection_check=False,
    freeze_url=True,
    provider_group="aliyun",
    provider_group_name="Aliyun",
    provider_variant="token_plan_intl",
)

PROVIDER_ZHIPU_CN = OpenAIProvider(
    id="zhipu-cn",
    name="Zhipu (BigModel)",
    base_url="https://open.bigmodel.cn/api/paas/v4",
    api_key_prefix="",
    models=[],
    freeze_url=True,
    provider_group="zhipu",
    provider_group_name="Zhipu",
    provider_variant="open_platform_cn",
    meta={"is_free_tier": True},
)

PROVIDER_ZHIPU_CN_CODINGPLAN = OpenAIProvider(
    id="zhipu-cn-codingplan",
    name="Zhipu Coding Plan (BigModel)",
    base_url="https://open.bigmodel.cn/api/coding/paas/v4",
    api_key_prefix="",
    models=[],
    freeze_url=True,
    support_connection_check=False,
    provider_group="zhipu",
    provider_group_name="Zhipu",
    provider_variant="coding_plan_cn",
)

PROVIDER_ZHIPU_INTL = OpenAIProvider(
    id="zhipu-intl",
    name="Zhipu (Z.AI)",
    base_url="https://api.z.ai/api/paas/v4",
    api_key_prefix="",
    models=[],
    freeze_url=True,
    provider_group="zhipu",
    provider_group_name="Zhipu",
    provider_variant="open_platform_intl",
)

PROVIDER_ZHIPU_INTL_CODINGPLAN = OpenAIProvider(
    id="zhipu-intl-codingplan",
    name="Zhipu Coding Plan (Z.AI)",
    base_url="https://api.z.ai/api/coding/paas/v4",
    api_key_prefix="",
    models=[],
    freeze_url=True,
    support_connection_check=False,
    provider_group="zhipu",
    provider_group_name="Zhipu",
    provider_variant="coding_plan_intl",
)

PROVIDER_QWENPAW = OpenAIProvider(
    id="qwenpaw-local",
    name="QwenPaw Local",
    is_local=True,
    require_api_key=False,
)

PROVIDER_OPENAI = OpenAIProvider(
    id="openai",
    name="OpenAI",
    base_url="https://api.openai.com/v1",
    api_key_prefix="sk-",
    models=[],
    freeze_url=True,
    meta={
        "supports_oauth": True,
        "oauth_auth_mode": "codex_oauth",
        "oauth_flows": ["codex_device_code"],
    },
)

PROVIDER_OPENCODE = OpenCodeProvider(
    id="opencode",
    name="OpenCode",
    base_url="https://opencode.ai/zen/v1",
    api_key_prefix="",
    models=[],
    require_api_key=False,
    meta={
        "base_url_options": [
            {"label": "OpenCode", "value": "https://opencode.ai/zen/v1"},
            {"label": "OpenCode Go", "value": "https://opencode.ai/zen/go/v1"},
        ],
        "is_free_tier": True,
    },
    freeze_url=False,
)

PROVIDER_KILO = KiloProvider(
    id="kilo",
    name="Kilo Code",
    base_url="https://api.kilo.ai/api/gateway",
    api_key_prefix="",
    models=[],
    require_api_key=False,
    meta={"is_free_tier": True},
    freeze_url=True,
)

PROVIDER_AZURE_OPENAI = OpenAIProvider(
    id="azure-openai",
    name="Azure OpenAI",
    api_key_prefix="",
    models=[],
)

PROVIDER_MINIMAX = AnthropicProvider(
    id="minimax",
    name="MiniMax (International)",
    base_url="https://api.minimax.io/anthropic",
    models=[],
    chat_model="AnthropicChatModel",
    freeze_url=True,
    support_connection_check=False,
    provider_group="minimax",
    provider_group_name="MiniMax",
    provider_variant="open_platform_intl",
)

PROVIDER_MINIMAX_CN = AnthropicProvider(
    id="minimax-cn",
    name="MiniMax (China)",
    base_url="https://api.minimaxi.com/anthropic",
    models=[],
    chat_model="AnthropicChatModel",
    freeze_url=True,
    support_connection_check=False,
    provider_group="minimax",
    provider_group_name="MiniMax",
    provider_variant="open_platform_cn",
)

PROVIDER_KIMI_CN = OpenAIProvider(
    id="kimi-cn",
    name="Kimi (China)",
    base_url="https://api.moonshot.cn/v1",
    api_key_prefix="",
    models=[],
    freeze_url=True,
    provider_group="kimi",
    provider_group_name="Kimi",
    provider_variant="open_platform_cn",
)

PROVIDER_KIMI_INTL = OpenAIProvider(
    id="kimi-intl",
    name="Kimi (International)",
    base_url="https://api.moonshot.ai/v1",
    api_key_prefix="",
    models=[],
    freeze_url=True,
    provider_group="kimi",
    provider_group_name="Kimi",
    provider_variant="open_platform_intl",
)

PROVIDER_KIMI_CODINGPLAN = OpenAIProvider(
    id="kimi-codingplan",
    name="Kimi Coding Plan",
    base_url="https://api.kimi.com/coding/v1",
    api_key_prefix="sk-kimi-",
    models=[],
    freeze_url=True,
    support_connection_check=False,
    provider_group="kimi",
    provider_group_name="Kimi",
    provider_variant="coding_plan",
)

PROVIDER_DEEPSEEK = OpenAIProvider(
    id="deepseek",
    name="DeepSeek",
    base_url="https://api.deepseek.com",
    api_key_prefix="sk-",
    models=[],
    freeze_url=True,
)

PROVIDER_ANTHROPIC = AnthropicProvider(
    id="anthropic",
    name="Anthropic",
    base_url="https://api.anthropic.com",
    api_key_prefix="sk-ant-",
    models=[],
    chat_model="AnthropicChatModel",
    freeze_url=False,
)

PROVIDER_GEMINI = GeminiProvider(
    id="gemini",
    name="Google Gemini",
    base_url="https://generativelanguage.googleapis.com",
    api_key_prefix="",
    models=[],
    chat_model="GeminiChatModel",
    freeze_url=True,
    meta={
        "is_free_tier": True,
    },
)

PROVIDER_OLLAMA = OllamaProvider(
    id="ollama",
    name="Ollama",
    is_local=True,
    require_api_key=False,
    support_model_discovery=True,
    generate_kwargs={"max_tokens": None},
)

PROVIDER_OPENROUTER = OpenRouterProvider(
    id="openrouter",
    name="OpenRouter",
    base_url="https://openrouter.ai/api/v1",
    api_key_prefix="sk-or-v1-",
    models=[],
    freeze_url=True,
    meta={
        "supports_oauth": True,
        "is_free_tier": True,
    },
)

PROVIDER_GITHUB_MODELS = OpenAIProvider(
    id="github-models",
    name="GitHub Models",
    base_url="https://models.inference.ai.azure.com",
    api_key_prefix="ghp_",
    models=[],
    freeze_url=True,
    meta={
        "is_free_tier": True,
    },
)


PROVIDER_LMSTUDIO = LMStudioProvider(
    id="lmstudio",
    name="LM Studio",
    is_local=True,
    base_url="http://localhost:1234/v1",
    require_api_key=False,
    api_key_prefix="",
    support_model_discovery=True,
    generate_kwargs={"max_tokens": None},
)

PROVIDER_SILICONFLOW_CN = OpenAIProvider(
    id="siliconflow-cn",
    name="SiliconFlow (China)",
    base_url="https://api.siliconflow.cn/v1",
    api_key_prefix="sk-",
    models=[],
    freeze_url=True,
    require_api_key=True,
    provider_group="siliconflow",
    provider_group_name="SiliconFlow",
    provider_variant="china",
    meta={
        "is_free_tier": True,
    },
)

PROVIDER_SILICONFLOW_INTL = OpenAIProvider(
    id="siliconflow-intl",
    name="SiliconFlow (International)",
    base_url="https://api.siliconflow.com/v1",
    api_key_prefix="sk-",
    models=[],
    freeze_url=True,
    require_api_key=True,
    provider_group="siliconflow",
    provider_group_name="SiliconFlow",
    provider_variant="international",
    meta={
        "is_free_tier": True,
    },
)

PROVIDER_VOLCENGINE_CN = OpenAIProvider(
    id="volcengine-cn",
    name="Volcano Engine",
    base_url="https://ark.cn-beijing.volces.com/api/v3",
    api_key_prefix="",
    models=[],
    freeze_url=True,
    support_model_discovery=True,
    provider_group="volcengine",
    provider_group_name="Volcano Engine",
    provider_variant="open_platform",
)

PROVIDER_VOLCENGINE_CN_CODINGPLAN = OpenAIProvider(
    id="volcengine-cn-codingplan",
    name="Volcano Engine Coding Plan",
    base_url="https://ark.cn-beijing.volces.com/api/coding/v3",
    api_key_prefix="",
    models=[],
    support_connection_check=False,
    freeze_url=True,
    support_model_discovery=True,
    provider_group="volcengine",
    provider_group_name="Volcano Engine",
    provider_variant="coding_plan",
)

PROVIDER_MIMO_TOKENPLAN = OpenAIProvider(
    id="mimo-tokenplan",
    name="Xiaomi MiMo Token Plan",
    base_url="https://token-plan-cn.xiaomimimo.com/v1",
    api_key_prefix="",
    models=[],
    freeze_url=True,
)


class ProviderManager:  # pylint: disable=too-many-public-methods
    """A manager class to handle all providers,
    including built-in and custom ones."""

    _instance = None

    def __init__(self) -> None:
        # Initialize provider manager, load providers from registry and store
        # any necessary state (e.g., cached models).
        self.builtin_providers: Dict[str, Provider] = {}
        self.custom_providers: Dict[str, Provider] = {}
        self.plugin_providers: Dict[str, Dict] = {}  # Plugin providers
        self.active_model: ModelSlotConfig | None = None
        self.active_model_fallbacks: List[ModelSlotConfig] = []
        self.root_path = SECRET_DIR / "providers"
        self.builtin_path = self.root_path / "builtin"
        self.custom_path = self.root_path / "custom"
        self.plugin_path = self.root_path / "plugin"  # Plugin provider configs
        self._prepare_disk_storage()
        self._init_builtins()
        try:
            self._migrate_legacy_providers()
        except Exception as e:
            logger.warning("Failed to migrate legacy providers: %s", e)
        self._init_from_storage()
        self._apply_default_annotations()

    def _prepare_disk_storage(self):
        """Prepare directory structure"""
        for path in [
            self.root_path,
            self.builtin_path,
            self.custom_path,
            self.plugin_path,
        ]:
            path.mkdir(parents=True, exist_ok=True)
            try:
                os.chmod(path, 0o700)  # Restrict permissions for security
            except Exception:
                pass

    def _init_builtins(self):
        self._add_builtin(PROVIDER_QWENPAW)
        self._add_builtin(PROVIDER_OLLAMA)
        self._add_builtin(PROVIDER_LMSTUDIO)
        self._add_builtin(PROVIDER_OPENROUTER)
        self._add_builtin(PROVIDER_GITHUB_MODELS)
        self._add_builtin(PROVIDER_MODELSCOPE)
        self._add_builtin(PROVIDER_DASHSCOPE)
        self._add_builtin(PROVIDER_ALIYUN_CODINGPLAN)
        self._add_builtin(PROVIDER_ALIYUN_CODINGPLAN_INTL)
        self._add_builtin(PROVIDER_ALIYUN_TOKENPLAN)
        self._add_builtin(PROVIDER_ALIYUN_TOKENPLAN_INTL)
        self._add_builtin(PROVIDER_OPENCODE)
        self._add_builtin(PROVIDER_KILO)
        self._add_builtin(PROVIDER_OPENAI)
        self._add_builtin(PROVIDER_AZURE_OPENAI)
        self._add_builtin(PROVIDER_ANTHROPIC)
        self._add_builtin(PROVIDER_GEMINI)
        self._add_builtin(PROVIDER_DEEPSEEK)
        self._add_builtin(PROVIDER_KIMI_CN)
        self._add_builtin(PROVIDER_KIMI_INTL)
        self._add_builtin(PROVIDER_KIMI_CODINGPLAN)
        self._add_builtin(PROVIDER_MINIMAX_CN)
        self._add_builtin(PROVIDER_MINIMAX)
        self._add_builtin(PROVIDER_ZHIPU_CN)
        self._add_builtin(PROVIDER_ZHIPU_CN_CODINGPLAN)
        self._add_builtin(PROVIDER_ZHIPU_INTL)
        self._add_builtin(PROVIDER_ZHIPU_INTL_CODINGPLAN)
        self._add_builtin(PROVIDER_SILICONFLOW_CN)
        self._add_builtin(PROVIDER_SILICONFLOW_INTL)
        self._add_builtin(PROVIDER_VOLCENGINE_CN)
        self._add_builtin(PROVIDER_VOLCENGINE_CN_CODINGPLAN)
        self._add_builtin(PROVIDER_MIMO_TOKENPLAN)

    def _add_builtin(self, provider: Provider):
        provider = provider.model_copy(deep=True)
        if not provider.is_local:
            provider.support_model_discovery = True
        self.builtin_providers[provider.id] = provider

    async def list_provider_info(self) -> List[ProviderInfo]:
        tasks = [provider.get_info() for provider in self.builtin_providers.values()]
        tasks += [provider.get_info() for provider in self.custom_providers.values()]
        # Add plugin providers - directly return their ProviderInfo
        for plugin_provider in self.plugin_providers.values():
            provider_info = plugin_provider["info"]
            # Plugin providers store ProviderInfo directly, no need to
            # instantiate
            tasks.append(self._get_plugin_provider_info(provider_info))

        provider_infos = await asyncio.gather(*tasks)
        return list(provider_infos)

    async def _get_plugin_provider_info(
        self,
        provider_info: ProviderInfo,
    ) -> ProviderInfo:
        """Helper to return plugin provider info as async task."""
        return provider_info

    @staticmethod
    def _normalize_provider_id(provider_id: str) -> str:
        """Normalize provider ID for backward compatibility.

        Maps legacy 'copaw-local' to 'qwenpaw-local'.
        """
        if provider_id == "copaw-local":
            return "qwenpaw-local"
        return provider_id

    def get_provider(self, provider_id: str) -> Provider | None:
        # Return a provider instance by its ID. This will be used to create
        # chat model instances for the agent.
        # Normalize provider ID for backward compatibility
        provider_id = self._normalize_provider_id(provider_id)
        # Check plugin providers first
        if provider_id in self.plugin_providers:
            plugin_provider = self.plugin_providers[provider_id]
            provider_info = plugin_provider["info"]
            provider_class = plugin_provider["class"]
            # Instantiate with **dict unpacking for Pydantic BaseModel
            return provider_class(**provider_info.model_dump())
        if provider_id in self.builtin_providers:
            return self.builtin_providers[provider_id]
        if provider_id in self.custom_providers:
            return self.custom_providers[provider_id]
        return None

    async def get_provider_info(self, provider_id: str) -> ProviderInfo | None:
        provider = self.get_provider(provider_id)
        return await provider.get_info() if provider else None

    def get_active_model(self) -> ModelSlotConfig | None:
        # Return the currently active provider/model configuration.
        return self.active_model

    def get_active_model_fallbacks(self) -> List[ModelSlotConfig]:
        """Return configured global fallback models in priority order."""
        return [
            ModelSlotConfig(provider_id=slot.provider_id, model=slot.model)
            for slot in self.active_model_fallbacks
        ]

    def update_provider(self, provider_id: str, config: Dict) -> bool:
        # Update the configuration of a provider (e.g., base URL, API key).
        # This will be called when the user edits a provider's settings in the
        # UI. It should update the in-memory provider instance and persist the
        # changes to providers.json.
        # Normalize provider ID for backward compatibility
        provider_id = self._normalize_provider_id(provider_id)
        provider = self.get_provider(provider_id)
        if not provider:
            return False
        provider.update_config(config)

        # Determine save location
        is_builtin = provider_id in self.builtin_providers
        is_plugin = provider_id in self.plugin_providers

        if is_plugin:
            # Update plugin provider info in memory (convert Provider to
            # ProviderInfo)
            provider_info = ProviderInfo(**provider.model_dump())
            self.plugin_providers[provider_id]["info"] = provider_info
            # Save to plugin path (separate from builtin)
            self._save_plugin_provider(provider)
        else:
            self._save_provider(provider, is_builtin=is_builtin)

        return True

    def start_local_model_resume(self, local_manager) -> None:
        """Schedule background restore of the active local model server."""
        task = asyncio.create_task(
            self._resume_local_model(local_manager),
            name="qwenpaw-local-model-resume",
        )
        task.add_done_callback(self._on_local_model_resume_done)

    @staticmethod
    def _on_local_model_resume_done(task: asyncio.Task[None]) -> None:
        """Log unexpected failures from background local model restore."""
        if task.cancelled():
            return

        exc = task.exception()
        if exc is not None:
            logger.warning(
                "Background local model restore failed: %s",
                exc,
                exc_info=exc,
            )
        logger.info("Background local model restore completed")

    async def fetch_provider_models(
        self,
        provider_id: str,
        save: bool = True,
    ) -> List[ModelInfo]:
        """Fetch the list of available models from a provider.

        Args:
            provider_id: The ID of the provider to fetch models from.
            save: If True, save the discovered models to the provider
                configuration. Defaults to True.

        Returns:
            List of ModelInfo objects representing available models.
        """
        provider_id = self._normalize_provider_id(provider_id)
        provider = self.get_provider(provider_id)
        if not provider:
            return []
        provider_api_models: List[ModelInfo] = []
        try:
            provider_api_models = await provider.fetch_models()
        except Exception as e:
            logger.warning(
                "Failed to fetch models from provider API '%s': %s",
                provider_id,
                e,
            )

        if getattr(provider, "auth_mode", "") == "codex_oauth":
            models = provider_api_models
        else:
            models = await discover_models_with_models_dev_fallback(
                provider,
                provider_api_models,
            )
        if save:
            provider.extra_models = models
            # Save provider config to appropriate location
            is_plugin = provider_id in self.plugin_providers
            if is_plugin:
                provider_info = ProviderInfo(**provider.model_dump())
                self.plugin_providers[provider_id]["info"] = provider_info
                self._save_plugin_provider(provider)
            else:
                self._save_provider(
                    provider,
                    is_builtin=provider_id in self.builtin_providers,
                )
        return models

    def _resolve_custom_provider_id(self, provider_id: str) -> str:
        """Resolve provider ID conflicts for a custom provider."""
        base_id = provider_id
        if base_id in self.builtin_providers:
            base_id = f"{base_id}-custom"

        resolved_id = base_id
        while (
            resolved_id in self.builtin_providers
            or resolved_id in self.custom_providers
        ):
            resolved_id = f"{resolved_id}-new"

        return resolved_id

    async def add_custom_provider(self, provider_data: ProviderInfo):
        # Add a new custom provider with the given data. This will update the
        # providers.json file and make the new provider available in the UI.
        provider_payload = provider_data.model_dump()
        provider_payload["id"] = self._resolve_custom_provider_id(
            provider_data.id,
        )
        provider_payload["is_custom"] = True
        provider = self._provider_from_data(
            provider_payload,
        )  # Validate provider data
        # For custom providers, we assume they don't support connection check
        # without model config, to avoid false negatives in the UI.
        provider.support_connection_check = False
        provider.support_model_discovery = True
        self.custom_providers[provider.id] = provider
        self._save_provider(provider, is_builtin=False)
        return await provider.get_info()

    def remove_custom_provider(self, provider_id: str) -> bool:
        # Remove a custom provider by its ID. This will update the
        # providers.json file and remove the provider from the UI.
        if provider_id in self.custom_providers:
            del self.custom_providers[provider_id]
            provider_path = self.custom_path / f"{provider_id}.json"
            if provider_path.exists():
                os.remove(provider_path)
            self._prune_active_model_fallbacks(provider_id=provider_id)
            return True
        return False

    async def activate_model(
        self,
        provider_id: str,
        model_id: str,
        fallback_models: List[ModelSlotConfig] | None = None,
    ):
        # Set the active provider and model for the agent. This will update
        # providers.json and determine which provider/model is used when the
        # agent creates chat model instances.
        # Normalize provider ID for backward compatibility
        provider_id = self._normalize_provider_id(provider_id)
        provider = self.get_provider(provider_id)
        if not provider:
            raise ProviderError(
                message=f"Provider '{provider_id}' not found.",
            )
        if not provider.has_model(model_id):
            raise ModelNotFoundException(
                model_name=f"{provider_id}/{model_id}",
                details={"provider_id": provider_id, "model_id": model_id},
            )
        next_active_model = ModelSlotConfig(
            provider_id=provider_id,
            model=model_id,
        )
        if fallback_models is not None:
            next_fallbacks = self._dedupe_model_slots(
                fallback_models,
                primary=next_active_model,
                strict=True,
            )
            fallbacks_changed = True
        else:
            next_fallbacks = self._dedupe_model_slots(
                self.active_model_fallbacks,
                primary=next_active_model,
                strict=False,
            )
            fallbacks_changed = next_fallbacks != self.active_model_fallbacks

        self.active_model = next_active_model
        self.active_model_fallbacks = next_fallbacks
        self.save_active_model(self.active_model)
        if fallbacks_changed:
            self.save_active_model_fallbacks(self.active_model_fallbacks)

        self.maybe_probe_multimodal(provider_id, model_id)

    def _validate_model_slot(self, slot: ModelSlotConfig) -> ModelSlotConfig:
        """Normalize and validate a provider/model slot."""
        provider_id = self._normalize_provider_id(slot.provider_id)
        model_id = (slot.model or "").strip()
        provider = self.get_provider(provider_id)
        if not provider:
            raise ProviderError(
                message=f"Provider '{provider_id}' not found.",
            )
        if not provider.has_model(model_id):
            raise ModelNotFoundException(
                model_name=f"{provider_id}/{model_id}",
                details={"provider_id": provider_id, "model_id": model_id},
            )
        return ModelSlotConfig(provider_id=provider_id, model=model_id)

    def _dedupe_model_slots(
        self,
        slots: List[ModelSlotConfig],
        primary: ModelSlotConfig | None = None,
        *,
        strict: bool,
    ) -> List[ModelSlotConfig]:
        """Validate, de-duplicate, and remove the primary slot."""
        seen: set[tuple[str, str]] = set()
        if primary and primary.provider_id and primary.model:
            seen.add(
                (
                    self._normalize_provider_id(primary.provider_id),
                    primary.model.strip(),
                ),
            )

        result: List[ModelSlotConfig] = []
        for raw_slot in slots:
            try:
                slot = self._validate_model_slot(raw_slot)
            except Exception:
                if strict:
                    raise
                logger.warning(
                    "Dropping invalid active model fallback: %s",
                    raw_slot,
                    exc_info=True,
                )
                continue
            key = (slot.provider_id, slot.model)
            if key in seen:
                continue
            seen.add(key)
            result.append(slot)
        return result

    def set_active_model_fallbacks(
        self,
        fallback_models: List[ModelSlotConfig],
        primary: ModelSlotConfig | None = None,
    ) -> None:
        """Persist global active-model fallback slots in priority order."""
        primary = primary if primary is not None else self.active_model
        self.active_model_fallbacks = self._dedupe_model_slots(
            fallback_models,
            primary=primary,
            strict=True,
        )
        self.save_active_model_fallbacks(self.active_model_fallbacks)

    def _prune_active_model_fallbacks(
        self,
        provider_id: str | None = None,
        model_id: str | None = None,
    ) -> None:
        """Remove fallback entries that reference a deleted provider/model."""
        provider_id = self._normalize_provider_id(provider_id) if provider_id else None
        before = len(self.active_model_fallbacks)
        self.active_model_fallbacks = [
            slot
            for slot in self.active_model_fallbacks
            if not (
                (provider_id is None or slot.provider_id == provider_id)
                and (model_id is None or slot.model == model_id)
            )
        ]
        if len(self.active_model_fallbacks) != before:
            self.save_active_model_fallbacks(self.active_model_fallbacks)

    def maybe_probe_multimodal(self, provider_id: str, model_id: str) -> None:
        """Schedule multimodal probing for a model if capability is unknown."""
        provider = self.get_provider(provider_id)
        # Auto-probe multimodal if not yet probed
        for model in provider.models + provider.extra_models:
            if model.id == model_id and model.supports_multimodal is None:
                asyncio.create_task(
                    self._auto_probe_multimodal(provider_id, model_id),
                )
                break

    async def _auto_probe_multimodal(
        self,
        provider_id: str,
        model_id: str,
    ) -> None:
        """Background probe that doesn't block model activation."""
        try:
            result = await self.probe_model_multimodal(provider_id, model_id)
            logger.info(
                "Auto-probe for %s/%s: image=%s, video=%s",
                provider_id,
                model_id,
                result.get("supports_image"),
                result.get("supports_video"),
            )
        except Exception as e:
            logger.warning("Auto-probe multimodal failed: %s", e)

    async def add_model_to_provider(
        self,
        provider_id: str,
        model_info: ModelInfo,
    ) -> ProviderInfo:
        provider_id = self._normalize_provider_id(provider_id)
        provider = self.get_provider(provider_id)
        if not provider:
            raise ProviderError(
                message=f"Provider '{provider_id}' not found.",
            )
        added, error_message = await provider.add_model(model_info)
        if not added:
            raise ProviderError(
                message=error_message,
                details={
                    "provider_id": provider_id,
                    "model_id": model_info.id,
                },
            )

        # Save provider config to appropriate location
        is_plugin = provider_id in self.plugin_providers
        if is_plugin:
            provider_info = ProviderInfo(**provider.model_dump())
            self.plugin_providers[provider_id]["info"] = provider_info
            self._save_plugin_provider(provider)
        else:
            self._save_provider(
                provider,
                is_builtin=provider_id in self.builtin_providers,
            )
        return await provider.get_info()

    async def update_model_config(
        self,
        provider_id: str,
        model_id: str,
        config: Dict,
    ) -> ProviderInfo:
        """Update per-model configuration and persist to disk."""
        provider_id = self._normalize_provider_id(provider_id)
        provider = self.get_provider(provider_id)
        if not provider:
            raise ProviderError(
                message=f"Provider '{provider_id}' not found.",
            )
        if not provider.update_model_config(model_id, config):
            raise ModelNotFoundException(
                model_name=f"{provider_id}/{model_id}",
                details={"provider_id": provider_id, "model_id": model_id},
            )

        # Save provider config to appropriate location
        is_plugin = provider_id in self.plugin_providers
        if is_plugin:
            provider_info = ProviderInfo(**provider.model_dump())
            self.plugin_providers[provider_id]["info"] = provider_info
            self._save_plugin_provider(provider)
        else:
            self._save_provider(
                provider,
                is_builtin=provider_id in self.builtin_providers,
            )
        return await provider.get_info()

    async def delete_model_from_provider(
        self,
        provider_id: str,
        model_id: str,
    ) -> ProviderInfo:
        provider_id = self._normalize_provider_id(provider_id)
        provider = self.get_provider(provider_id)
        if not provider:
            raise ProviderError(
                message=f"Provider '{provider_id}' not found.",
            )
        await provider.delete_model(model_id=model_id)
        if not provider.has_model(model_id):
            self._prune_active_model_fallbacks(
                provider_id=provider_id,
                model_id=model_id,
            )

        # Save provider config to appropriate location
        is_plugin = provider_id in self.plugin_providers
        if is_plugin:
            provider_info = ProviderInfo(**provider.model_dump())
            self.plugin_providers[provider_id]["info"] = provider_info
            self._save_plugin_provider(provider)
        else:
            self._save_provider(
                provider,
                is_builtin=provider_id in self.builtin_providers,
            )
        return await provider.get_info()

    async def probe_model_multimodal(
        self,
        provider_id: str,
        model_id: str,
        image_only: bool = False,
    ) -> dict:
        """Probe a model's multimodal capabilities and persist the result.

        Args:
            provider_id: Provider identifier.
            model_id: Model identifier.
            image_only: When True, skip the video probe for a faster result.
                Only ``supports_image`` will be accurate; ``supports_video``
                will remain at its previous value (not updated).
        """
        provider_id = self._normalize_provider_id(provider_id)
        provider = self.get_provider(provider_id)
        if not provider:
            return {"error": f"Provider '{provider_id}' not found"}

        result = await provider.probe_model_multimodal(
            model_id,
            image_only=image_only,
        )

        # Update the model's capability flags.
        # For image_only probes, leave supports_video untouched so a
        # subsequent full probe can fill it in correctly.
        for model in provider.models + provider.extra_models:
            if model.id == model_id:
                model.supports_image = result.supports_image
                if not image_only:
                    model.supports_video = result.supports_video
                    model.supports_multimodal = result.supports_multimodal
                else:
                    # Partial update: derive supports_multimodal from
                    # image alone; video will be updated by the full probe.
                    if result.supports_image:
                        model.supports_multimodal = True
                model.probe_source = "probed"
                break

        # Compare probe result against expected baseline
        from .capability_baseline import (
            ExpectedCapabilityRegistry,
            compare_probe_result,
        )

        registry = ExpectedCapabilityRegistry()
        expected = registry.get_expected(provider_id, model_id)
        if expected:
            discrepancies = compare_probe_result(
                expected,
                result.supports_image,
                result.supports_video,
            )
            for d in discrepancies:
                logger.warning(
                    "Probe discrepancy: %s/%s %s expected=%s actual=%s (%s)",
                    d.provider_id,
                    d.model_id,
                    d.field,
                    d.expected,
                    d.actual,
                    d.discrepancy_type,
                )

        # Persist to disk
        is_plugin = provider_id in self.plugin_providers
        if is_plugin:
            provider_info = ProviderInfo(**provider.model_dump())
            self.plugin_providers[provider_id]["info"] = provider_info
            self._save_plugin_provider(provider)
        else:
            self._save_provider(
                provider,
                is_builtin=provider_id in self.builtin_providers,
            )
        return {
            "supports_image": result.supports_image,
            "supports_video": result.supports_video,
            "supports_multimodal": result.supports_multimodal,
            "image_message": result.image_message,
            "video_message": result.video_message,
        }

    def _save_provider(
        self,
        provider: Provider,
        is_builtin: bool = False,
        skip_if_exists: bool = False,
    ):
        """Save a provider configuration to disk.

        Sensitive fields (``api_key``) are encrypted before writing.
        """
        provider_dir = self.builtin_path if is_builtin else self.custom_path
        provider_path = provider_dir / f"{provider.id}.json"
        if skip_if_exists and provider_path.exists():
            return
        data = encrypt_dict_fields(
            provider.model_dump(),
            PROVIDER_SECRET_FIELDS,
        )
        with open(provider_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        try:
            os.chmod(provider_path, 0o600)
        except OSError:
            pass

    def _save_plugin_provider(self, provider: Provider):
        """Save a plugin provider configuration to disk.

        Sensitive fields (``api_key``) are encrypted before writing.
        """
        provider_path = self.plugin_path / f"{provider.id}.json"
        data = encrypt_dict_fields(
            provider.model_dump(),
            PROVIDER_SECRET_FIELDS,
        )
        with open(provider_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        try:
            os.chmod(provider_path, 0o600)
        except OSError:
            pass

    def save_provider_config(
        self,
        provider_id: str,
        provider: Provider | None = None,
    ) -> None:
        """Persist the current in-memory provider state to disk.

        Args:
            provider_id: The provider to save.
            provider: Optional pre-resolved provider instance. When
                supplied, this instance is saved directly — important
                for plugin providers where ``get_provider`` returns a
                fresh copy each time.
        """
        if provider is None:
            provider = self.get_provider(provider_id)
        if provider is None:
            return
        is_plugin = provider_id in self.plugin_providers
        if is_plugin:
            provider_info = ProviderInfo(**provider.model_dump())
            self.plugin_providers[provider_id]["info"] = provider_info
            self._save_plugin_provider(provider)
        else:
            self._save_provider(
                provider,
                is_builtin=provider_id in self.builtin_providers,
            )

    def load_provider(
        self,
        provider_id: str,
        is_builtin: bool = False,
    ) -> Provider | None:
        """Load a provider configuration from disk.

        Encrypted fields are transparently decrypted.  If a legacy
        plaintext ``api_key`` is detected it is re-encrypted in place.
        """
        provider_dir = self.builtin_path if is_builtin else self.custom_path
        provider_path = provider_dir / f"{provider_id}.json"
        if not provider_path.exists():
            return None
        try:
            with open(provider_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            needs_rewrite = self._maybe_migrate_plaintext(
                data,
                PROVIDER_SECRET_FIELDS,
            )
            data = decrypt_dict_fields(data, PROVIDER_SECRET_FIELDS)
            provider = self._provider_from_data(data)

            if needs_rewrite:
                try:
                    self._save_provider(
                        provider,
                        is_builtin=is_builtin,
                        skip_if_exists=False,
                    )
                except Exception as enc_err:
                    logger.debug(
                        "Deferred plaintext→encrypted migration"
                        " for provider '%s': %s",
                        provider_id,
                        enc_err,
                    )

            return provider
        except Exception as e:
            logger.warning(
                "Failed to load provider '%s' from %s: %s",
                provider_id,
                provider_path,
                e,
            )
            return None

    @staticmethod
    def _maybe_migrate_plaintext(
        data: dict,
        secret_fields: frozenset[str],
    ) -> bool:
        """Return ``True`` when *data* contains plaintext secret fields
        that should be re-encrypted on disk."""
        for field in secret_fields:
            value = data.get(field)
            if isinstance(value, str) and value and not is_encrypted(value):
                return True
        return False

    def _provider_from_data(self, data: Dict) -> Provider:
        """Deserialize provider data to a concrete provider type."""
        provider_id = str(data.get("id", ""))
        chat_model = str(data.get("chat_model", ""))

        if provider_id == "openrouter":
            return OpenRouterProvider.model_validate(data)
        if provider_id == "anthropic" or chat_model == "AnthropicChatModel":
            return AnthropicProvider.model_validate(data)
        if provider_id == "gemini" or chat_model == "GeminiChatModel":
            return GeminiProvider.model_validate(data)
        if provider_id == "ollama":
            return OllamaProvider.model_validate(data)
        return OpenAIProvider.model_validate(data)

    def save_active_model(self, active_model: ModelSlotConfig):
        """Save the active provider/model configuration to disk."""
        active_path = self.root_path / "active_model.json"
        with open(active_path, "w", encoding="utf-8") as f:
            json.dump(
                active_model.model_dump(),
                f,
                ensure_ascii=False,
                indent=2,
            )
        try:
            os.chmod(active_path, 0o600)
        except OSError:
            pass

    def save_active_model_fallbacks(
        self,
        fallback_models: List[ModelSlotConfig],
    ) -> None:
        """Save global active provider/model fallbacks to disk."""
        fallbacks_path = self.root_path / "active_model_fallbacks.json"
        with open(fallbacks_path, "w", encoding="utf-8") as f:
            json.dump(
                [slot.model_dump() for slot in fallback_models],
                f,
                ensure_ascii=False,
                indent=2,
            )
        try:
            os.chmod(fallbacks_path, 0o600)
        except OSError:
            pass

    def clear_active_model(self, provider_id: str | None = None) -> bool:
        """Clear the active provider/model configuration.

        If provider_id is provided, only clear when it matches the current
        active provider.
        """
        if self.active_model is None:
            return False
        # Normalize provider ID for backward compatibility
        if provider_id is not None:
            provider_id = self._normalize_provider_id(provider_id)
        if provider_id is not None and self.active_model.provider_id != provider_id:
            return False

        self.active_model = None
        active_path = self.root_path / "active_model.json"
        try:
            active_path.unlink()
        except (FileNotFoundError, OSError):
            pass
        return True

    def load_active_model(self) -> ModelSlotConfig | None:
        """Load the active provider/model configuration from disk."""
        active_path = self.root_path / "active_model.json"
        if not active_path.exists():
            return None
        try:
            with open(active_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return ModelSlotConfig.model_validate(data)
        except Exception:
            return None

    def load_active_model_fallbacks(self) -> List[ModelSlotConfig]:
        """Load global active provider/model fallbacks from disk."""
        fallbacks_path = self.root_path / "active_model_fallbacks.json"
        if not fallbacks_path.exists():
            return []
        try:
            with open(fallbacks_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                return []
            return [ModelSlotConfig.model_validate(item) for item in data]
        except Exception:
            return []

    def _migrate_copaw_config(self) -> None:
        """Migrate copaw-local provider config to qwenpaw-local."""
        # 1. Migrate active model configuration (only provider_id)
        if self.active_model and self.active_model.provider_id == "copaw-local":
            self.active_model.provider_id = "qwenpaw-local"
            self.save_active_model(self.active_model)
            logger.info(
                "Migrated active model provider from "
                "'copaw-local' to 'qwenpaw-local'",
            )
        migrated_fallbacks = False
        for slot in self.active_model_fallbacks:
            if slot.provider_id == "copaw-local":
                slot.provider_id = "qwenpaw-local"
                migrated_fallbacks = True
        if migrated_fallbacks:
            self.save_active_model_fallbacks(self.active_model_fallbacks)

        # 2. Migrate stored provider config file
        copaw_config_path = self.builtin_path / "copaw-local.json"
        if not copaw_config_path.exists():
            return

        try:
            # Load old config and apply to new provider instance
            with open(copaw_config_path, "r", encoding="utf-8") as f:
                old_config = json.load(f)

            # Get the new built-in provider instance
            provider = self.builtin_providers.get("qwenpaw-local")
            if not provider:
                return

            # Apply migrated configuration (preserve extra_models as-is)
            if "extra_models" in old_config:
                provider.extra_models = [
                    ModelInfo.model_validate(model)
                    for model in old_config["extra_models"]
                ]
            if "base_url" in old_config:
                provider.base_url = old_config["base_url"]
            if "generate_kwargs" in old_config:
                provider.generate_kwargs = old_config["generate_kwargs"]

            # Save using standard persistence logic (with encryption)
            self._save_provider(provider, is_builtin=True)

            # Remove old config file
            copaw_config_path.unlink()
            logger.info(
                "Migrated provider config from "
                "'copaw-local.json' to 'qwenpaw-local.json'",
            )
        except Exception as exc:
            logger.warning("Failed to migrate copaw-local config: %s", exc)

    # pylint: disable=too-many-branches
    def _migrate_legacy_providers(self):
        """Migrate from legacy providers.json format to the new structure."""
        legacy_path = SECRET_DIR / "providers.json"
        if legacy_path.exists() and legacy_path.is_file():
            with open(legacy_path, "r", encoding="utf-8") as f:
                legacy_data = json.load(f)
            builtin_providers = legacy_data.get("providers", {})
            custom_providers = legacy_data.get("custom_providers", {})
            active_model = legacy_data.get("active_llm", {})
            # Migrate built-in providers
            for provider_id, config in builtin_providers.items():
                provider = self.get_provider(provider_id)
                if not provider:
                    logger.warning(
                        "Legacy provider '%s' not found in"
                        " registry, skipping migration for this provider.",
                        provider_id,
                    )
                    continue
                if "api_key" in config:
                    provider.api_key = config["api_key"]
                if "extra_models" in config:
                    provider.extra_models = [
                        ModelInfo.model_validate(model)
                        for model in config["extra_models"]
                    ]
                if not provider.freeze_url and "base_url" in config:
                    provider.base_url = config["base_url"]
                self._save_provider(provider, is_builtin=True)
            # Migrate custom providers
            for provider_id, data in custom_providers.items():
                custom_provider = OpenAIProvider(
                    id=provider_id,
                    name=data.get("name", provider_id),
                    base_url=data.get("base_url", ""),
                    api_key=data.get("api_key", ""),
                    is_custom=True,
                )
                if "models" in data:
                    # migrate models to extra_models field
                    custom_provider.extra_models = [
                        ModelInfo.model_validate(model) for model in data["models"]
                    ]
                if "chat_model" in data:
                    custom_provider.chat_model = data["chat_model"]
                self._save_provider(custom_provider, is_builtin=False)
            # Migrate active model (only provider_id, not model)
            if active_model:
                try:
                    # Convert legacy copaw-local provider_id
                    if active_model.get("provider_id") == "copaw-local":
                        active_model["provider_id"] = "qwenpaw-local"
                    self.active_model = ModelSlotConfig.model_validate(
                        active_model,
                    )
                    self.save_active_model(self.active_model)
                except Exception:
                    logger.warning(
                        "Failed to migrate active model, using default.",
                    )
            # Remove legacy file after migration
            try:
                os.remove(legacy_path)
            except Exception:
                logger.warning(
                    "Failed to remove legacy providers.json after migration.",
                )

    def _init_from_storage(self):
        """Initialize all providers and active model from disk storage."""
        # Load built-in providers
        # pylint: disable=too-many-nested-blocks
        for builtin in self.builtin_providers.values():
            provider = self.load_provider(builtin.id, is_builtin=True)
            if provider:
                # inherit user-configured base_url only when freeze_url=False
                if not builtin.freeze_url:
                    builtin.base_url = provider.base_url
                builtin.api_key = provider.api_key
                if provider.auth_mode != "api_key":
                    builtin.auth_mode = provider.auth_mode
                if provider.oauth_refresh_token:
                    builtin.oauth_refresh_token = provider.oauth_refresh_token
                if provider.oauth_expires_at is not None:
                    builtin.oauth_expires_at = provider.oauth_expires_at
                if provider.custom_headers:
                    builtin.custom_headers = provider.custom_headers
                builtin_model_ids = {m.id for m in builtin.models}
                builtin.extra_models = [
                    m for m in provider.extra_models if m.id not in builtin_model_ids
                ]
                builtin.generate_kwargs.update(provider.generate_kwargs)
                # Restore per-model config for built-in models.
                # Collect from both stored built-in models and promoted
                # extra_models (models that were user-added but are now
                # part of the built-in list).
                stored_model_config: dict = {}
                for m in provider.models:
                    stored_model_config[m.id] = {
                        "generate_kwargs": m.generate_kwargs,
                        "max_tokens": m.max_tokens,
                        "max_input_length": m.max_input_length,
                    }
                for m in provider.extra_models:
                    if m.id in builtin_model_ids:
                        stored_model_config.setdefault(
                            m.id,
                            {
                                "generate_kwargs": m.generate_kwargs,
                                "max_tokens": m.max_tokens,
                                "max_input_length": m.max_input_length,
                            },
                        )
                if stored_model_config:
                    for model in builtin.models:
                        cfg = stored_model_config.get(model.id)
                        if cfg:
                            if cfg["generate_kwargs"]:
                                model.generate_kwargs = cfg["generate_kwargs"]
                            if cfg["max_tokens"] is not None:
                                model.max_tokens = cfg["max_tokens"]
                            if cfg["max_input_length"] is not None:
                                model.max_input_length = cfg["max_input_length"]
        # Load custom providers
        for provider_file in self.custom_path.glob("*.json"):
            provider = self.load_provider(provider_file.stem, is_builtin=False)
            if provider:
                provider.support_model_discovery = True
                self.custom_providers[provider.id] = provider
        # Load active model config
        active_model = self.load_active_model()
        if active_model:
            self.active_model = active_model

        fallback_models = self.load_active_model_fallbacks()
        if fallback_models:
            self.active_model_fallbacks = self._dedupe_model_slots(
                fallback_models,
                primary=self.active_model,
                strict=False,
            )
            if self.active_model_fallbacks != fallback_models:
                self.save_active_model_fallbacks(self.active_model_fallbacks)

        # Migrate copaw-local to qwenpaw-local for backwards compatibility
        self._migrate_copaw_config()

    def _apply_default_annotations(self):
        """Apply doc-based default annotations for unprobed models.

        Models that already carry static annotations (supports_image /
        supports_video set at definition time) only need the derived
        supports_multimodal flag computed.  Models with no annotations
        at all fall back to the ExpectedCapabilityRegistry.
        """
        from .capability_baseline import ExpectedCapabilityRegistry

        registry = ExpectedCapabilityRegistry()
        for provider in self.builtin_providers.values():
            for model in provider.models:
                # Already fully annotated (e.g. by a prior probe) → skip
                if model.supports_multimodal is not None:
                    continue

                # Static annotations present → compute derived flag only
                if model.supports_image is not None or model.supports_video is not None:
                    model.supports_multimodal = bool(
                        model.supports_image or model.supports_video,
                    )
                    continue

                # No annotations at all → fall back to registry
                expected = registry.get_expected(provider.id, model.id)
                if expected:
                    model.supports_image = expected.expected_image
                    model.supports_video = expected.expected_video
                    model.supports_multimodal = bool(
                        expected.expected_image or expected.expected_video,
                    )
                    model.probe_source = "documentation"

    async def _resume_local_model(self, local_manager) -> None:
        """Resume the active local model server from the previous run."""

        def _clear_local_provider():
            self.update_provider(
                "qwenpaw-local",
                {
                    "base_url": "",
                    "extra_models": [],
                },
            )

        local_models = self.get_provider("qwenpaw-local").extra_models
        model_id = local_models[0].id if local_models else None
        if model_id is None:
            return

        installed, _ = local_manager.check_llamacpp_installation()
        if not installed:
            logger.info(
                "Skipping local model restore because" " llama.cpp is not installed.",
            )
            _clear_local_provider()
            return

        if not local_manager.is_model_downloaded(model_id):
            logger.warning(
                "Skipping local model restore because" " model is not downloaded: %s",
                model_id,
            )
            _clear_local_provider()
            return

        try:
            setup_result = await local_manager.setup_server(model_id)
        except (FileNotFoundError, RuntimeError, ValueError) as exc:
            logger.warning(
                "Failed to restore local model server for %s: %s",
                model_id,
                exc,
            )
            _clear_local_provider()
            return

        self.update_provider(
            "qwenpaw-local",
            {
                "base_url": f"http://127.0.0.1:{setup_result.port}/v1",
                "extra_models": [setup_result.model_info],
            },
        )

    def register_plugin_provider(
        self,
        provider_id: str,
        provider_class,
        label: str,
        base_url: str,
        metadata: Dict,
    ):
        """Register a plugin provider.

        Args:
            provider_id: Provider ID
            provider_class: Provider class
            label: Display label
            base_url: API base URL
            metadata: Additional metadata
        """
        # Get default models from provider class if available
        default_models = []
        if hasattr(provider_class, "get_default_models"):
            try:
                default_models = provider_class.get_default_models()
            except Exception as e:
                logger.warning(
                    f"Failed to get default models for {provider_id}: {e}",
                )

        # Create ProviderInfo
        provider_info = ProviderInfo(
            id=provider_id,
            name=label,
            base_url=base_url,
            api_key="",  # Will be configured by user
            chat_model=metadata.get("chat_model", "OpenAIChatModel"),
            models=default_models,  # Add default models
            is_custom=False,  # Mark as non-custom (like builtin, cannot be
            # deleted)
            require_api_key=metadata.get("require_api_key", True),
            meta=metadata.get("meta", {}),  # Pass meta from plugin
        )

        # Check if there's a saved configuration for this plugin provider
        saved_config_path = self.plugin_path / f"{provider_id}.json"
        if saved_config_path.exists():
            try:
                with open(saved_config_path, "r", encoding="utf-8") as f:
                    saved_config = json.load(f)

                # Decrypt sensitive fields
                saved_config = decrypt_dict_fields(
                    saved_config,
                    PROVIDER_SECRET_FIELDS,
                )

                # Merge saved config (api_key, base_url, extra_models, etc)
                if "api_key" in saved_config:
                    provider_info.api_key = saved_config["api_key"]
                if "base_url" in saved_config:
                    provider_info.base_url = saved_config["base_url"]
                if "generate_kwargs" in saved_config:
                    provider_info.generate_kwargs = saved_config["generate_kwargs"]
                # Load extra_models from saved config
                if "extra_models" in saved_config:
                    provider_info.extra_models = [
                        ModelInfo.model_validate(
                            (
                                model.model_dump()
                                if isinstance(model, BaseModel)
                                else model
                            ),
                        )
                        for model in saved_config["extra_models"]
                    ]
                logger.info(
                    f"✓ Loaded saved config for plugin provider: "
                    f"{provider_id} "
                    f"({len(provider_info.extra_models)} extra model(s))",
                )
            except Exception as e:
                logger.warning(
                    f"Failed to load saved config for {provider_id}: {e}",
                )

        # Register to internal dict
        self.plugin_providers[provider_id] = {
            "info": provider_info,
            "class": provider_class,
        }

        logger.info(
            f"✓ Registered plugin provider: {provider_id} "
            f"with {len(default_models)} default model(s)",
        )

    def unregister_plugin_provider(self, provider_id: str) -> bool:
        """Remove a plugin provider from memory.

        Removes the provider from ``self.plugin_providers`` so it no
        longer appears in the model list.  The persisted configuration
        file (``plugin_path/{provider_id}.json``) is intentionally
        kept on disk so that user-configured keys survive a
        reinstall.

        Args:
            provider_id: Plugin provider identifier to remove.

        Returns:
            ``True`` if the provider was found and removed,
            ``False`` if it was not registered.
        """
        if provider_id not in self.plugin_providers:
            logger.warning(
                f"unregister_plugin_provider: '{provider_id}' not found",
            )
            return False
        del self.plugin_providers[provider_id]
        self._prune_active_model_fallbacks(provider_id=provider_id)
        logger.info(
            f"Unregistered plugin provider '{provider_id}' from memory",
        )
        return True

    @staticmethod
    def get_instance() -> "ProviderManager":
        """Get the singleton instance of ProviderManager."""
        if ProviderManager._instance is None:
            ProviderManager._instance = ProviderManager()
        return ProviderManager._instance

    @staticmethod
    def get_active_chat_model() -> ChatModelBase:
        """Get the currently active provider/model configuration."""
        manager = ProviderManager.get_instance()
        model = manager.get_active_model()
        if model is None or model.provider_id == "" or model.model == "":
            raise ProviderError(
                message="No active model configured.",
            )
        provider = manager.get_provider(model.provider_id)
        if provider is None:
            raise ProviderError(
                message=f"Active provider '{model.provider_id}' not found.",
            )
        return provider.get_chat_model_instance(model.model)
