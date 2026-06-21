# -*- coding: utf-8 -*-
"""Tools for managing skills as procedural memory."""

from __future__ import annotations

import json
from typing import Any

from agentscope.message import TextBlock
from agentscope.tool import ToolResponse

from ...config.config import load_agent_config
from ..skill_system.memory_service import SkillMemoryService


def _response(payload: dict[str, Any]) -> ToolResponse:
    return ToolResponse(
        content=[
            TextBlock(
                type="text",
                text=json.dumps(payload, ensure_ascii=False, indent=2),
            ),
        ],
    )


def _service() -> SkillMemoryService | None:
    from ...config.context import get_current_workspace_dir

    workspace_dir = get_current_workspace_dir()
    if workspace_dir is None:
        return None
    return SkillMemoryService(workspace_dir)


async def skill_manage(  # pylint: disable=too-many-arguments,too-many-return-statements
    action: str,
    skill_name: str = "",
    content: str = "",
    old_text: str = "",
    new_text: str = "",
    file_path: str = "",
    source_skills: list[str] | None = None,
    suggested_name: str = "",
    auto_merge: bool | None = None,
) -> ToolResponse:
    """Create, patch, archive, restore, or merge workspace skills.

    This tool is scoped to the current workspace. It never edits the shared
    skill pool or built-in skills. All writes pass through the skill scanner.
    """
    service = _service()
    if service is None:
        return _response({"success": False, "reason": "workspace_not_set"})

    normalized_action = action.strip().lower()
    try:
        if normalized_action == "create":
            return _response(
                service.create_skill(
                    name=skill_name,
                    content=content,
                ),
            )
        if normalized_action == "patch":
            return _response(
                service.patch_skill(
                    skill_name=skill_name,
                    old_text=old_text,
                    new_text=new_text or content,
                ),
            )
        if normalized_action == "write_file":
            return _response(
                service.write_skill_file(
                    skill_name=skill_name,
                    file_path=file_path,
                    content=content,
                ),
            )
        if normalized_action == "enable":
            from ..skill_system.workspace_service import SkillService

            result = SkillService(service.workspace_dir).enable_skill(
                skill_name,
            )
            if result.get("success"):
                service.record_review(skill_name, source="enable")
            return _response(result)
        if normalized_action == "disable":
            from ..skill_system.workspace_service import SkillService

            result = SkillService(service.workspace_dir).disable_skill(
                skill_name,
            )
            if result.get("success"):
                service.record_review(skill_name, source="disable")
            return _response(result)
        if normalized_action == "archive":
            return _response(service.archive_skill(skill_name, reason="tool"))
        if normalized_action == "restore":
            return _response(service.restore_skill(skill_name))
        if normalized_action == "pin":
            return _response(service.set_pinned(skill_name, True))
        if normalized_action == "unpin":
            return _response(service.set_pinned(skill_name, False))
        if normalized_action == "merge":
            from ...app.agent_context import get_current_agent_id

            agent_id = get_current_agent_id() or "default"
            cfg = load_agent_config(agent_id).running
            allow_auto = (
                cfg.procedural_skill_memory_config.auto_merge_enabled
                if auto_merge is None
                else bool(auto_merge)
            )
            return _response(
                service.merge_skills(
                    source_skills=source_skills or [],
                    suggested_name=suggested_name or skill_name,
                    merged_content=content,
                    auto_merge=allow_auto,
                ),
            )
    except Exception as exc:  # pylint: disable=broad-except
        return _response({"success": False, "reason": str(exc)})

    return _response({"success": False, "reason": "unknown_action"})


async def skill_read(skill_name: str, file_path: str = "SKILL.md") -> ToolResponse:
    """Read a workspace skill file for review."""
    service = _service()
    if service is None:
        return _response({"success": False, "reason": "workspace_not_set"})
    if file_path == "SKILL.md":
        try:
            from ..utils.file_handling import read_text_file_with_encoding_fallback
            from ..skill_system.store import (
                get_workspace_skills_dir,
                safe_skill_dir,
            )

            skill_dir = safe_skill_dir(
                get_workspace_skills_dir(service.workspace_dir),
                skill_name,
            )
            content = read_text_file_with_encoding_fallback(
                skill_dir / "SKILL.md",
            )
            return _response({"success": True, "content": content})
        except Exception as exc:  # pylint: disable=broad-except
            return _response({"success": False, "reason": str(exc)})
    from ..skill_system.workspace_service import SkillService

    loaded = SkillService(service.workspace_dir).load_skill_file(
        skill_name,
        file_path,
    )
    if loaded is None:
        return _response({"success": False, "reason": "not_found"})
    return _response({"success": True, "content": loaded})


async def skill_usage(skill_name: str = "") -> ToolResponse:
    """Read procedural memory usage statistics."""
    service = _service()
    if service is None:
        return _response({"success": False, "reason": "workspace_not_set"})
    if skill_name:
        return _response(
            {"success": True, "record": service.get_skill_record(skill_name)},
        )
    return _response({"success": True, "skills": service.list_skill_records()})
