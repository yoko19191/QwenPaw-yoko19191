# -*- coding: utf-8 -*-
# pylint: disable=redefined-outer-name,unused-argument,protected-access
"""Tests for the Kimi built-in providers."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

import qwenpaw.providers.provider_manager as provider_manager_module
from qwenpaw.providers.openai_provider import OpenAIProvider
from qwenpaw.providers.provider import ModelInfo
from qwenpaw.providers.provider_manager import (
    PROVIDER_KIMI_CN,
    PROVIDER_KIMI_INTL,
    PROVIDER_KIMI_CODINGPLAN,
    ProviderManager,
)


def test_kimi_providers_are_openai_compatible() -> None:
    """Kimi providers should be OpenAIProvider instances."""
    assert isinstance(PROVIDER_KIMI_CN, OpenAIProvider)
    assert isinstance(PROVIDER_KIMI_INTL, OpenAIProvider)


def test_kimi_provider_configs() -> None:
    """Verify Kimi provider configuration defaults."""
    assert PROVIDER_KIMI_CN.id == "kimi-cn"
    assert PROVIDER_KIMI_CN.name == "Kimi (China)"
    assert PROVIDER_KIMI_CN.base_url == "https://api.moonshot.cn/v1"
    assert PROVIDER_KIMI_CN.freeze_url is True

    assert PROVIDER_KIMI_INTL.id == "kimi-intl"
    assert PROVIDER_KIMI_INTL.name == "Kimi (International)"
    assert PROVIDER_KIMI_INTL.base_url == "https://api.moonshot.ai/v1"
    assert PROVIDER_KIMI_INTL.freeze_url is True


def test_kimi_models_are_discovered_dynamically() -> None:
    """Kimi providers should not ship hard-coded model IDs."""
    assert PROVIDER_KIMI_CN.models == []
    assert PROVIDER_KIMI_INTL.models == []


@pytest.fixture
def isolated_secret_dir(monkeypatch, tmp_path):
    secret_dir = tmp_path / ".qwenpaw.secret"
    monkeypatch.setattr(provider_manager_module, "SECRET_DIR", secret_dir)
    return secret_dir


def test_kimi_registered_in_provider_manager(isolated_secret_dir) -> None:
    """Kimi providers should be registered as built-in providers."""
    manager = ProviderManager()

    provider_cn = manager.get_provider("kimi-cn")
    assert provider_cn is not None
    assert isinstance(provider_cn, OpenAIProvider)
    assert provider_cn.base_url == "https://api.moonshot.cn/v1"

    provider_intl = manager.get_provider("kimi-intl")
    assert provider_intl is not None
    assert isinstance(provider_intl, OpenAIProvider)
    assert provider_intl.base_url == "https://api.moonshot.ai/v1"


async def test_kimi_check_connection_success(monkeypatch) -> None:
    """Kimi check_connection should delegate to OpenAI client."""
    provider = OpenAIProvider(
        id="kimi-cn",
        name="Kimi (China)",
        base_url="https://api.moonshot.cn/v1",
        api_key="test-key",
    )

    class FakeModels:
        async def list(self, timeout=None):
            return SimpleNamespace(data=[])

    fake_client = SimpleNamespace(models=FakeModels())
    monkeypatch.setattr(provider, "_client", lambda timeout=5: fake_client)

    ok, msg = await provider.check_connection(timeout=2)

    assert ok is True
    assert msg == ""


def test_kimi_registered_without_hardcoded_models(isolated_secret_dir) -> None:
    """Kimi providers should rely on API/models.dev discovery."""
    manager = ProviderManager()
    provider_cn = manager.get_provider("kimi-cn")
    provider_intl = manager.get_provider("kimi-intl")

    assert provider_cn is not None
    assert provider_intl is not None
    assert provider_cn.models == []
    assert provider_intl.models == []
    assert provider_cn.support_model_discovery is True
    assert provider_intl.support_model_discovery is True


async def test_kimi_activate_models(
    isolated_secret_dir,
    monkeypatch,
) -> None:
    """Should be able to activate both Kimi providers."""
    manager = ProviderManager()
    provider_cn = manager.get_provider("kimi-cn")
    provider_intl = manager.get_provider("kimi-intl")
    assert provider_cn is not None
    assert provider_intl is not None

    provider_cn.extra_models = [
        ModelInfo(id="kimi-discovered", name="kimi-discovered"),
    ]
    provider_intl.extra_models = [
        ModelInfo(id="kimi-thinking-discovered", name="kimi-thinking-discovered"),
    ]

    await manager.activate_model("kimi-cn", "kimi-discovered")
    assert manager.active_model is not None
    assert manager.active_model.provider_id == "kimi-cn"
    assert manager.active_model.model == "kimi-discovered"

    await manager.activate_model("kimi-intl", "kimi-thinking-discovered")
    assert manager.active_model is not None
    assert manager.active_model.provider_id == "kimi-intl"
    assert manager.active_model.model == "kimi-thinking-discovered"


def test_kimi_codingplan_provider_config() -> None:
    """Verify Kimi Coding Plan provider configuration."""
    assert isinstance(PROVIDER_KIMI_CODINGPLAN, OpenAIProvider)
    assert PROVIDER_KIMI_CODINGPLAN.id == "kimi-codingplan"
    assert PROVIDER_KIMI_CODINGPLAN.name == "Kimi Coding Plan"
    assert (
        PROVIDER_KIMI_CODINGPLAN.base_url == "https://api.kimi.com/coding/v1"
    )
    assert PROVIDER_KIMI_CODINGPLAN.api_key_prefix == "sk-kimi-"
    assert PROVIDER_KIMI_CODINGPLAN.freeze_url is True
    assert PROVIDER_KIMI_CODINGPLAN.support_connection_check is False


def test_kimi_codingplan_models_are_discovered_dynamically() -> None:
    """Kimi Coding Plan should not ship hard-coded model IDs."""
    assert PROVIDER_KIMI_CODINGPLAN.models == []


def test_kimi_codingplan_registered(isolated_secret_dir) -> None:
    """Kimi Coding Plan should be in ProviderManager builtins."""
    manager = ProviderManager()
    provider = manager.get_provider("kimi-codingplan")
    assert provider is not None
    assert provider.models == []
    assert provider.support_model_discovery is True


def test_kimi_provider_group_meta() -> None:
    """All Kimi providers share the same provider_group."""
    for p in (
        PROVIDER_KIMI_CN,
        PROVIDER_KIMI_INTL,
        PROVIDER_KIMI_CODINGPLAN,
    ):
        assert p.provider_group == "kimi"
        assert p.provider_group_name == "Kimi"

    assert PROVIDER_KIMI_CN.provider_variant == "open_platform_cn"
    assert PROVIDER_KIMI_INTL.provider_variant == "open_platform_intl"
    assert PROVIDER_KIMI_CODINGPLAN.provider_variant == "coding_plan"
