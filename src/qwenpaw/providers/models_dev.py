# -*- coding: utf-8 -*-
"""models.dev metadata enrichment for provider model discovery."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Iterable, Mapping
from urllib.parse import urlparse

import httpx

from qwenpaw.providers.provider import ModelInfo, ProviderInfo
from qwenpaw.utils.http import trust_env_for_url

logger = logging.getLogger(__name__)

MODELS_DEV_API_URL = "https://models.dev/api.json"
MODELS_DEV_PROBE_SOURCE = "models.dev"
_CACHE_TTL_SECONDS = 6 * 60 * 60
_USER_AGENT = "QwenPaw/1.0"

_catalog_cache: Mapping[str, Any] | None = None
_catalog_cache_at = 0.0
_catalog_lock = asyncio.Lock()

_PROVIDER_ALIASES: dict[str, tuple[str, ...]] = {
    "azure-openai": ("azure",),
    "dashscope": ("alibaba-cn", "alibaba"),
    "aliyun-codingplan": ("alibaba-coding-plan-cn",),
    "aliyun-codingplan-intl": ("alibaba-coding-plan",),
    "aliyun-tokenplan": ("alibaba-token-plan-cn",),
    "aliyun-tokenplan-intl": ("alibaba-token-plan",),
    "anthropic": ("anthropic",),
    "deepseek": ("deepseek",),
    "gemini": ("google",),
    "github-models": ("github-models",),
    "kimi-cn": ("moonshotai-cn",),
    "kimi-intl": ("moonshotai",),
    "kimi-codingplan": ("kimi-for-coding",),
    "lmstudio": ("lmstudio",),
    "minimax": ("minimax",),
    "minimax-cn": ("minimax-cn",),
    "mimo-tokenplan": ("xiaomi-token-plan-cn",),
    "modelscope": ("modelscope",),
    "opencode": ("opencode", "opencode-go"),
    "openai": ("openai",),
    "openrouter": ("openrouter",),
    "kilo": ("kilo",),
    "siliconflow-cn": ("siliconflow-cn",),
    "siliconflow-intl": ("siliconflow",),
    "zhipu-cn": ("zhipuai",),
    "zhipu-cn-codingplan": ("zhipuai-coding-plan",),
    "zhipu-intl": ("zai",),
    "zhipu-intl-codingplan": ("zai-coding-plan",),
}


def _normal_key(value: str | None) -> str:
    return (value or "").strip().casefold()


def _positive_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value > 0:
        return value
    if isinstance(value, float) and value > 0 and value.is_integer():
        return int(value)
    return None


def _normalize_url(value: str | None) -> str:
    if not value:
        return ""

    parsed = urlparse(value.strip())
    if not parsed.scheme or not parsed.netloc:
        return value.strip().rstrip("/").casefold()

    path = parsed.path.rstrip("/")
    return f"{parsed.scheme.casefold()}://{parsed.netloc.casefold()}{path}"


def _url_variants(value: str | None) -> set[str]:
    normalized = _normalize_url(value)
    if not normalized:
        return set()

    variants = {normalized}
    if normalized.endswith("/v1"):
        variants.add(normalized[:-3])
    else:
        variants.add(f"{normalized}/v1")
    return variants


def _iter_provider_keys(
    provider: ProviderInfo,
    catalog: Mapping[str, Any],
) -> Iterable[str]:
    seen: set[str] = set()

    def add(key: str | None):
        if key and key in catalog and key not in seen:
            seen.add(key)
            yield key

    provider_id = provider.id
    yield from add(provider_id)

    for alias in _PROVIDER_ALIASES.get(provider_id, ()):
        yield from add(alias)

    group = getattr(provider, "provider_group", "")
    for alias in _PROVIDER_ALIASES.get(group, ()):
        yield from add(alias)

    provider_urls = _url_variants(getattr(provider, "base_url", ""))
    if not provider_urls:
        return

    for key, entry in catalog.items():
        if key in seen or not isinstance(entry, Mapping):
            continue
        entry_urls = _url_variants(str(entry.get("api") or ""))
        if provider_urls.intersection(entry_urls):
            seen.add(key)
            yield key


def _model_aliases(key: str, metadata: Mapping[str, Any]) -> set[str]:
    aliases = {_normal_key(key)}

    metadata_id = metadata.get("id")
    if isinstance(metadata_id, str):
        aliases.add(_normal_key(metadata_id))

    for value in list(aliases):
        if "/" in value:
            aliases.add(value.rsplit("/", 1)[-1])

    return {alias for alias in aliases if alias}


def _build_model_lookup(
    provider_models: Mapping[str, Any],
) -> dict[str, Mapping[str, Any]]:
    lookup: dict[str, Mapping[str, Any]] = {}

    for key, metadata in provider_models.items():
        if not isinstance(metadata, Mapping):
            continue
        for alias in _model_aliases(str(key), metadata):
            lookup.setdefault(alias, metadata)

    return lookup


def _find_metadata(
    model: ModelInfo,
    lookups: Iterable[dict[str, Mapping[str, Any]]],
) -> Mapping[str, Any] | None:
    aliases = {
        _normal_key(model.id),
        _normal_key(model.name),
    }
    for alias in list(aliases):
        if "/" in alias:
            aliases.add(alias.rsplit("/", 1)[-1])

    aliases.discard("")

    for lookup in lookups:
        for alias in aliases:
            metadata = lookup.get(alias)
            if metadata is not None:
                return metadata
    return None


def _apply_metadata(model: ModelInfo, metadata: Mapping[str, Any]) -> ModelInfo:
    enriched = model.model_copy(deep=True)
    applied_metadata = False

    limit = metadata.get("limit")
    if isinstance(limit, Mapping):
        context = _positive_int(limit.get("context")) or _positive_int(
            limit.get("input"),
        )
        output = _positive_int(limit.get("output"))
        if context is not None and context >= 1000:
            enriched.max_input_length = context
            applied_metadata = True
        if output is not None:
            enriched.max_tokens = output
            applied_metadata = True

    modalities = metadata.get("modalities")
    if isinstance(modalities, Mapping):
        raw_input = modalities.get("input")
        if isinstance(raw_input, list):
            input_modalities = {
                str(modality).casefold()
                for modality in raw_input
                if isinstance(modality, str)
            }
            if input_modalities:
                enriched.supports_image = "image" in input_modalities
                enriched.supports_video = "video" in input_modalities
                enriched.supports_multimodal = any(
                    modality != "text" for modality in input_modalities
                )
                applied_metadata = True

    if applied_metadata:
        enriched.probe_source = MODELS_DEV_PROBE_SOURCE

    return enriched


def _is_free_from_cost(cost: Any) -> bool:
    if not isinstance(cost, Mapping):
        return False
    numeric_values: list[float] = []
    for value in cost.values():
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            numeric_values.append(float(value))
    return bool(numeric_values) and all(value == 0 for value in numeric_values)


def _metadata_to_model_info(
    key: str,
    metadata: Mapping[str, Any],
) -> ModelInfo | None:
    raw_id = metadata.get("id")
    model_id = str(raw_id if isinstance(raw_id, str) else key).strip()
    if not model_id:
        return None

    raw_name = metadata.get("name")
    name = str(raw_name if isinstance(raw_name, str) else model_id).strip()
    model = ModelInfo(
        id=model_id,
        name=name or model_id,
        is_free=_is_free_from_cost(metadata.get("cost")),
    )
    return _apply_metadata(model, metadata)


def discover_models_dev_models(
    provider: ProviderInfo,
    catalog: Mapping[str, Any],
) -> list[ModelInfo]:
    """Build model candidates for a provider directly from models.dev."""
    provider_keys = list(_iter_provider_keys(provider, catalog))
    if not provider_keys:
        return []

    models: list[ModelInfo] = []
    seen: set[str] = set()
    for provider_key in provider_keys:
        entry = catalog.get(provider_key)
        if not isinstance(entry, Mapping):
            continue
        provider_models = entry.get("models")
        if not isinstance(provider_models, Mapping):
            continue
        for key, metadata in provider_models.items():
            if not isinstance(metadata, Mapping):
                continue
            model = _metadata_to_model_info(str(key), metadata)
            if model is None:
                continue
            dedupe_key = model.id.strip()
            if not dedupe_key or dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            models.append(model)

    return sorted(models, key=lambda item: item.id.casefold())


async def fetch_models_dev_catalog(timeout: float = 3.0) -> Mapping[str, Any]:
    """Fetch and cache the models.dev provider catalog."""
    global _catalog_cache, _catalog_cache_at  # pylint: disable=global-statement

    now = time.monotonic()
    if _catalog_cache is not None and now - _catalog_cache_at < _CACHE_TTL_SECONDS:
        return _catalog_cache

    async with _catalog_lock:
        now = time.monotonic()
        if _catalog_cache is not None and now - _catalog_cache_at < _CACHE_TTL_SECONDS:
            return _catalog_cache

        async with httpx.AsyncClient(
            follow_redirects=True,
            headers={"User-Agent": _USER_AGENT},
            timeout=timeout,
            trust_env=trust_env_for_url(MODELS_DEV_API_URL),
        ) as client:
            response = await client.get(MODELS_DEV_API_URL)
            response.raise_for_status()
            payload = response.json()

        if not isinstance(payload, Mapping):
            raise ValueError("models.dev catalog payload is not an object")

        _catalog_cache = payload
        _catalog_cache_at = time.monotonic()
        return _catalog_cache


def apply_models_dev_metadata(
    provider: ProviderInfo,
    models: list[ModelInfo],
    catalog: Mapping[str, Any],
) -> list[ModelInfo]:
    """Apply models.dev metadata to provider-discovered model rows."""
    provider_keys = list(_iter_provider_keys(provider, catalog))
    if not provider_keys:
        return models

    lookups: list[dict[str, Mapping[str, Any]]] = []
    for provider_key in provider_keys:
        entry = catalog.get(provider_key)
        if not isinstance(entry, Mapping):
            continue
        provider_models = entry.get("models")
        if isinstance(provider_models, Mapping):
            lookups.append(_build_model_lookup(provider_models))

    if not lookups:
        return models

    enriched_models: list[ModelInfo] = []
    for model in models:
        metadata = _find_metadata(model, lookups)
        if metadata is None:
            enriched_models.append(model)
        else:
            enriched_models.append(_apply_metadata(model, metadata))

    return enriched_models


def merge_models_dev_discovery(
    provider: ProviderInfo,
    provider_api_models: list[ModelInfo],
    catalog: Mapping[str, Any],
) -> list[ModelInfo]:
    """Merge provider API models with models.dev candidates.

    Provider API rows win for duplicate IDs because they reflect the current
    endpoint/account. models.dev adds metadata and fills providers whose model
    list API is unavailable.
    """
    api_models = apply_models_dev_metadata(
        provider,
        provider_api_models,
        catalog,
    )
    models_dev_models = discover_models_dev_models(provider, catalog)
    if not api_models:
        return models_dev_models

    merged = list(api_models)
    seen = {model.id.strip() for model in merged if model.id.strip()}
    for model in models_dev_models:
        model_id = model.id.strip()
        if not model_id or model_id in seen:
            continue
        seen.add(model_id)
        merged.append(model)
    return merged


async def enrich_models_with_models_dev_metadata(
    provider: ProviderInfo,
    models: list[ModelInfo],
) -> list[ModelInfo]:
    """Best-effort models.dev enrichment for discovered models."""
    if not models:
        return models

    try:
        catalog = await fetch_models_dev_catalog()
        return apply_models_dev_metadata(provider, models, catalog)
    except Exception as exc:  # pragma: no cover - network best effort
        logger.debug(
            "Failed to enrich provider '%s' models from models.dev: %s",
            provider.id,
            exc,
        )
        return models


async def discover_models_with_models_dev_fallback(
    provider: ProviderInfo,
    provider_api_models: list[ModelInfo],
) -> list[ModelInfo]:
    """Best-effort provider API + models.dev model discovery."""
    try:
        catalog = await fetch_models_dev_catalog()
        return merge_models_dev_discovery(
            provider,
            provider_api_models,
            catalog,
        )
    except Exception as exc:  # pragma: no cover - network best effort
        logger.debug(
            "Failed to discover provider '%s' models from models.dev: %s",
            provider.id,
            exc,
        )
        return provider_api_models
