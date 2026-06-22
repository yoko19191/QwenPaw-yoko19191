# -*- coding: utf-8 -*-

from qwenpaw.providers.models_dev import (
    MODELS_DEV_PROBE_SOURCE,
    apply_models_dev_metadata,
)
from qwenpaw.providers.provider import ModelInfo, ProviderInfo


def test_apply_models_dev_metadata_matches_provider_base_url():
    provider = ProviderInfo(
        id="custom-alibaba",
        name="Custom Alibaba",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    models = [ModelInfo(id="qwen3-omni-flash", name="Qwen Omni")]
    catalog = {
        "alibaba-cn": {
            "api": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "models": {
                "qwen3-omni-flash": {
                    "id": "qwen3-omni-flash",
                    "limit": {"context": 65536, "output": 16384},
                    "modalities": {
                        "input": ["text", "image", "audio", "video"],
                        "output": ["text", "audio"],
                    },
                },
            },
        },
    }

    enriched = apply_models_dev_metadata(provider, models, catalog)

    assert enriched[0].max_input_length == 65536
    assert enriched[0].max_tokens == 16384
    assert enriched[0].supports_multimodal is True
    assert enriched[0].supports_image is True
    assert enriched[0].supports_video is True
    assert enriched[0].probe_source == MODELS_DEV_PROBE_SOURCE


def test_apply_models_dev_metadata_matches_provider_alias_and_model_suffix():
    provider = ProviderInfo(
        id="gemini",
        name="Google Gemini",
        base_url="https://generativelanguage.googleapis.com",
    )
    models = [ModelInfo(id="gemini-2.5-pro", name="Gemini 2.5 Pro")]
    catalog = {
        "google": {
            "models": {
                "google/gemini-2.5-pro": {
                    "id": "google/gemini-2.5-pro",
                    "limit": {"context": 1048576, "output": 65536},
                    "modalities": {
                        "input": ["text", "image", "audio", "video", "pdf"],
                        "output": ["text"],
                    },
                },
            },
        },
    }

    enriched = apply_models_dev_metadata(provider, models, catalog)

    assert enriched[0].max_input_length == 1048576
    assert enriched[0].max_tokens == 65536
    assert enriched[0].supports_multimodal is True
    assert enriched[0].supports_image is True
    assert enriched[0].supports_video is True
    assert enriched[0].probe_source == MODELS_DEV_PROBE_SOURCE


def test_apply_models_dev_metadata_sets_text_only_capability():
    provider = ProviderInfo(id="deepseek", name="DeepSeek")
    models = [ModelInfo(id="deepseek-chat", name="DeepSeek Chat")]
    catalog = {
        "deepseek": {
            "models": {
                "deepseek-chat": {
                    "id": "deepseek-chat",
                    "limit": {"context": 1000000, "output": 384000},
                    "modalities": {
                        "input": ["text"],
                        "output": ["text"],
                    },
                },
            },
        },
    }

    enriched = apply_models_dev_metadata(provider, models, catalog)

    assert enriched[0].max_input_length == 1000000
    assert enriched[0].max_tokens == 384000
    assert enriched[0].supports_multimodal is False
    assert enriched[0].supports_image is False
    assert enriched[0].supports_video is False
    assert enriched[0].probe_source == MODELS_DEV_PROBE_SOURCE


def test_apply_models_dev_metadata_leaves_unmatched_models_unchanged():
    provider = ProviderInfo(id="custom", name="Custom")
    model = ModelInfo(id="unknown-model", name="Unknown")

    enriched = apply_models_dev_metadata(provider, [model], {})

    assert enriched[0].id == "unknown-model"
    assert enriched[0].max_input_length == model.max_input_length
    assert enriched[0].max_tokens == model.max_tokens
    assert enriched[0].probe_source is None
