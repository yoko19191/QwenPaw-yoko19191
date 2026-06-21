# -*- coding: utf-8 -*-
"""Tests for MarkdownMemoryStore."""

from pathlib import Path

import pytest

from qwenpaw.agents.memory.markdown_store import MarkdownMemoryStore


def test_markdown_store_initializes_and_migrates_legacy_files(tmp_path: Path):
    (tmp_path / "MEMORY.md").write_text("legacy long memory", encoding="utf-8")
    (tmp_path / "PROFILE.md").write_text("legacy user memory", encoding="utf-8")

    store = MarkdownMemoryStore(tmp_path, migrate_legacy_root_files=True)

    assert "legacy long memory" in store.read("MEMORY.md")
    assert "legacy user memory" in store.read("USER.md")
    assert (tmp_path / "MEMORY.md").exists()
    assert (tmp_path / "PROFILE.md").exists()


def test_markdown_store_applies_memory_operations(tmp_path: Path):
    store = MarkdownMemoryStore(tmp_path)

    added = store.apply(
        action="add",
        target="topics/project.md",
        content="Remember the deployment checklist.",
        source="test",
    )
    assert added["success"] is True
    assert "Remember the deployment checklist." in store.read(
        "topics/project.md",
    )

    replaced = store.apply(
        action="replace",
        target="topics/project.md",
        old_text="deployment checklist",
        content="release checklist",
    )
    assert replaced["success"] is True
    assert "release checklist" in store.read("topics/project.md")

    removed = store.apply(
        action="remove",
        target="topics/project.md",
        old_text="release checklist",
    )
    assert removed["success"] is True
    assert "release checklist" not in store.read("topics/project.md")


def test_markdown_store_snapshot_includes_daily_memory(tmp_path: Path):
    store = MarkdownMemoryStore(tmp_path)
    (tmp_path / "memory" / "2026-06-21.md").write_text(
        "# Daily\n\nToday decision",
        encoding="utf-8",
    )

    snapshot = store.build_prompt_snapshot(24000)

    assert "memory/2026-06-21.md" in snapshot
    assert "Today decision" in snapshot


def test_markdown_store_curator_deduplicates_entries(tmp_path: Path):
    store = MarkdownMemoryStore(tmp_path)
    assert store.apply(
        action="add",
        target="MEMORY.md",
        content="Stable fact",
        source="unit",
    )["success"]
    assert store.apply(
        action="add",
        target="MEMORY.md",
        content="Stable fact",
        source="unit",
    )["success"]

    result = store.curate()

    assert result["removed_entries"] == 1
    content = (tmp_path / "memory" / "MEMORY.md").read_text(encoding="utf-8")
    assert content.count("Stable fact") == 1


@pytest.mark.parametrize(
    "target",
    ["../MEMORY.md", "/tmp/MEMORY.md", ".hidden.md", ".state/learning.json"],
)
def test_markdown_store_rejects_unsafe_targets(
    tmp_path: Path,
    target: str,
):
    store = MarkdownMemoryStore(tmp_path)

    with pytest.raises(ValueError):
        store.apply(action="add", target=target, content="bad")
