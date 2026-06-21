# -*- coding: utf-8 -*-
"""Tests for SkillMemoryService."""

from pathlib import Path

from qwenpaw.agents.skill_system.memory_service import SkillMemoryService
from qwenpaw.agents.skill_system.store import read_skill_manifest


SKILL_MD = """---
name: demo_skill
description: Use this skill when testing procedural memory.
---

# Demo Skill

Follow the test procedure.
"""

OTHER_SKILL_MD = """---
name: other_skill
description: Use this skill when testing procedural memory variants.
---

# Other Skill

Follow the other procedure.
"""


def test_skill_memory_service_tracks_pin_archive_and_restore(tmp_path: Path):
    service = SkillMemoryService(tmp_path)
    created = service.create_skill(name="demo_skill", content=SKILL_MD)
    assert created["success"] is True

    service.record_usage("demo_skill", source="test")
    pinned = service.set_pinned("demo_skill", True)
    assert pinned["pinned"] is True
    assert service.get_skill_record("demo_skill")["use_count"] == 1

    archived = service.archive_skill("demo_skill", reason="unit_test")
    assert archived["success"] is True
    assert "demo_skill" not in read_skill_manifest(tmp_path).get("skills", {})
    assert service.list_archived_skills()[0]["name"] == "demo_skill"

    restored = service.restore_skill(archived["archive_id"])
    assert restored["success"] is True
    manifest = read_skill_manifest(tmp_path)
    assert "demo_skill" in manifest.get("skills", {})
    assert manifest["skills"]["demo_skill"]["enabled"] is False


def test_skill_memory_service_patches_and_writes_extra_file(tmp_path: Path):
    service = SkillMemoryService(tmp_path)
    assert service.create_skill(name="demo_skill", content=SKILL_MD)["success"]

    patched = service.patch_skill(
        skill_name="demo_skill",
        old_text="Follow the test procedure.",
        new_text="Follow the updated test procedure.",
    )
    assert patched["success"] is True

    written = service.write_skill_file(
        skill_name="demo_skill",
        file_path="references/checklist.md",
        content="# Checklist\n",
    )
    assert written["success"] is True
    assert (
        tmp_path / "skills" / "demo_skill" / "references" / "checklist.md"
    ).exists()


def test_skill_memory_service_auto_merge_updates_primary_and_archives_other(
    tmp_path: Path,
):
    service = SkillMemoryService(tmp_path)
    assert service.create_skill(name="demo_skill", content=SKILL_MD)["success"]
    assert service.create_skill(name="other_skill", content=OTHER_SKILL_MD)[
        "success"
    ]

    merged = SKILL_MD.replace(
        "Follow the test procedure.",
        "Follow the merged procedure.",
    )
    result = service.merge_skills(
        source_skills=["demo_skill", "other_skill"],
        suggested_name="demo_skill",
        merged_content=merged,
        auto_merge=True,
    )

    assert result["success"] is True
    assert result["name"] == "demo_skill"
    assert "other_skill" not in read_skill_manifest(tmp_path).get("skills", {})
    assert service.get_skill_record("demo_skill")["derived_from"] == [
        "demo_skill",
        "other_skill",
    ]
    assert "Follow the merged procedure." in (
        tmp_path / "skills" / "demo_skill" / "SKILL.md"
    ).read_text(encoding="utf-8")
    assert service.list_archived_skills()[0]["name"] == "other_skill"
