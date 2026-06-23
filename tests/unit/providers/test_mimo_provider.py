# -*- coding: utf-8 -*-
# pylint: disable=redefined-outer-name,unused-argument,protected-access
"""Tests for the Xiaomi MiMo Token Plan built-in provider."""
from __future__ import annotations

import pytest

import qwenpaw.providers.provider_manager as provider_manager_module
from qwenpaw.providers.openai_provider import OpenAIProvider
from qwenpaw.providers.provider_manager import (
    PROVIDER_MIMO_TOKENPLAN,
    ProviderManager,
)


def test_mimo_provider_is_openai_compatible() -> None:
    """MiMo Token Plan provider should be an OpenAIProvider instance."""
    assert isinstance(PROVIDER_MIMO_TOKENPLAN, OpenAIProvider)


def test_mimo_provider_config() -> None:
    """Verify MiMo Token Plan provider configuration defaults."""
    assert PROVIDER_MIMO_TOKENPLAN.id == "mimo-tokenplan"
    assert PROVIDER_MIMO_TOKENPLAN.name == "Xiaomi MiMo Token Plan"
    assert (
        PROVIDER_MIMO_TOKENPLAN.base_url
        == "https://token-plan-cn.xiaomimimo.com/v1"
    )
    assert PROVIDER_MIMO_TOKENPLAN.freeze_url is True
    assert PROVIDER_MIMO_TOKENPLAN.api_key_prefix == ""


def test_mimo_models_are_discovered_dynamically() -> None:
    """MiMo Token Plan should not ship hard-coded model IDs."""
    assert PROVIDER_MIMO_TOKENPLAN.models == []


@pytest.fixture
def isolated_secret_dir(monkeypatch, tmp_path):
    secret_dir = tmp_path / ".qwenpaw.secret"
    monkeypatch.setattr(provider_manager_module, "SECRET_DIR", secret_dir)
    return secret_dir


def test_mimo_registered_in_provider_manager(
    isolated_secret_dir,
) -> None:
    """MiMo Token Plan provider should be registered as a built-in provider."""
    manager = ProviderManager()

    provider = manager.get_provider("mimo-tokenplan")
    assert provider is not None
    assert isinstance(provider, OpenAIProvider)
    assert provider.base_url == "https://token-plan-cn.xiaomimimo.com/v1"
    assert provider.name == "Xiaomi MiMo Token Plan"


def test_mimo_registered_without_hardcoded_models(isolated_secret_dir) -> None:
    """MiMo Token Plan provider should rely on API/models.dev discovery."""
    manager = ProviderManager()
    provider = manager.get_provider("mimo-tokenplan")

    assert provider is not None
    assert provider.models == []
    assert provider.support_model_discovery is True


def test_mimo_provider_list_includes_mimo(isolated_secret_dir) -> None:
    """ProviderManager should list MiMo Token Plan in available providers."""
    manager = ProviderManager()
    # Verify the provider exists in builtin_providers
    assert "mimo-tokenplan" in manager.builtin_providers
    assert manager.get_provider("mimo-tokenplan") is not None
