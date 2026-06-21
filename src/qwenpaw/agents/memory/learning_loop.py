# -*- coding: utf-8 -*-
"""Post-turn learning loops for Markdown memory and procedural skills."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from agentscope.agent import ReActAgent
from agentscope.memory import InMemoryMemory
from agentscope.message import Msg
from agentscope.tool import Toolkit

from ..model_factory import create_model_and_formatter
from ..skill_system.memory_service import SkillMemoryService
from ..tools.skill_memory_tools import skill_manage, skill_read, skill_usage
from ...app.runner.utils import strip_injected_skill_block
from ...config.config import load_agent_config
from .markdown_store import MarkdownMemoryStore

logger = logging.getLogger(__name__)


def _message_text(msg: Msg) -> str:
    role = getattr(msg, "role", "") or ""
    text = msg.get_text_content() if hasattr(msg, "get_text_content") else ""
    return strip_injected_skill_block(text or "", role)


def _format_exchange(messages: list[Msg], response: Msg | None) -> str:
    lines = []
    for msg in messages[-6:]:
        role = getattr(msg, "role", "unknown") or "unknown"
        text = _message_text(msg).strip()
        if text:
            lines.append(f"{role}: {text[:4000]}")
    if response is not None:
        text = _message_text(response).strip()
        if text:
            lines.append(f"assistant: {text[:4000]}")
    return "\n\n".join(lines)


async def schedule_learning_review(
    *,
    agent_id: str,
    workspace_dir: str | Path,
    memory_manager: Any,
    messages: list[Msg],
    response: Msg | None,
    source: str = "chat",
) -> None:
    """Fire-and-forget post-turn learning review when configured."""
    if source in {"cron", "learning_review"}:
        return
    task = asyncio.create_task(
        _run_learning_review(
            agent_id=agent_id,
            workspace_dir=Path(workspace_dir),
            memory_manager=memory_manager,
            messages=list(messages or []),
            response=response,
        ),
        name=f"learning-review-{agent_id}",
    )
    task.add_done_callback(_log_task_failure)


def _log_task_failure(task: asyncio.Task) -> None:
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.warning("learning review failed: %s", exc, exc_info=True)


async def _run_learning_review(
    *,
    agent_id: str,
    workspace_dir: Path,
    memory_manager: Any,
    messages: list[Msg],
    response: Msg | None,
) -> None:
    agent_config = load_agent_config(agent_id)
    running = agent_config.running
    markdown_cfg = running.markdown_memory_config
    skill_cfg = running.procedural_skill_memory_config
    if not markdown_cfg.review_enabled and not skill_cfg.review_enabled:
        return

    store = getattr(memory_manager, "markdown_store", None)
    if store is None and markdown_cfg.enabled:
        store = MarkdownMemoryStore(
            working_dir=workspace_dir,
            memory_dir_name=running.daily_memory_dir,
            migrate_legacy_root_files=markdown_cfg.migrate_legacy_root_files,
        )

    should_review_memory = False
    should_review_skills = False
    if store is not None and markdown_cfg.enabled and markdown_cfg.review_enabled:
        count = store.bump_counter("memory_turn_count")
        should_review_memory = count % markdown_cfg.review_interval_turns == 0
    if store is not None and skill_cfg.enabled and skill_cfg.review_enabled:
        count = store.bump_counter("skill_turn_count")
        should_review_skills = count % skill_cfg.review_interval_turns == 0
    if should_review_memory and not hasattr(memory_manager, "memory_manage"):
        should_review_memory = False

    if not should_review_memory and not should_review_skills:
        return

    prompt = _build_review_prompt(
        should_review_memory=should_review_memory,
        should_review_skills=should_review_skills,
        exchange=_format_exchange(messages, response),
    )
    if not prompt.strip():
        return

    from ...app.agent_context import set_current_agent_id
    from ...config.context import set_current_workspace_dir

    set_current_workspace_dir(workspace_dir)
    set_current_agent_id(agent_id)
    chat_model, formatter = create_model_and_formatter(agent_id)
    toolkit = Toolkit()
    if should_review_memory and hasattr(memory_manager, "memory_manage"):
        toolkit.register_tool_function(memory_manager.memory_manage)
    if should_review_skills:
        toolkit.register_tool_function(skill_manage)
        toolkit.register_tool_function(skill_read)
        toolkit.register_tool_function(skill_usage)

    review_agent = ReActAgent(
        name="QwenPawLearningReview",
        model=chat_model,
        sys_prompt=(
            "You are a background learning reviewer. Extract only stable, "
            "future-useful memory or procedural skill improvements. Use the "
            "provided tools for writes. If there is nothing durable, reply "
            "with 'no changes'. Never use unavailable tools."
        ),
        toolkit=toolkit,
        memory=InMemoryMemory(),
        formatter=formatter,
        max_iters=6,
    )
    await review_agent(
        Msg(
            name="learning_review",
            role="user",
            content=prompt,
        ),
    )
    if store is not None:
        state = store.read_state()
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        if should_review_memory:
            state["last_memory_review_at"] = now
        if should_review_skills:
            state["last_skill_review_at"] = now
        store.write_state(state)


def _build_review_prompt(
    *,
    should_review_memory: bool,
    should_review_skills: bool,
    exchange: str,
) -> str:
    targets = []
    if should_review_memory:
        targets.append(
            "- Memory: use memory_manage to update memory/MEMORY.md, "
            "memory/USER.md, or memory/topics/*.md only for durable facts, "
            "stable preferences, decisions, or reusable project context.",
        )
    if should_review_skills:
        targets.append(
            "- Skills: use skill_manage only for workspace skills when a "
            "reusable procedure should be created or corrected.",
        )
    return (
        "Review the completed exchange below.\n\n"
        + "\n".join(targets)
        + "\n\nDo not record transient chatter, secrets, or raw injected "
        "SKILL.md content. Prefer no changes over noisy memory.\n\n"
        "## Exchange\n\n"
        f"{exchange}"
    )


def run_skill_curator(
    *,
    agent_id: str,
    workspace_dir: str | Path,
) -> dict[str, Any]:
    """Run deterministic procedural skill curator."""
    agent_config = load_agent_config(agent_id)
    cfg = agent_config.running.procedural_skill_memory_config
    if not cfg.enabled or not cfg.curator_enabled:
        return {"skipped": True}
    return SkillMemoryService(workspace_dir).curate(cfg)


def run_markdown_memory_curator(
    *,
    agent_id: str,
    workspace_dir: str | Path,
) -> dict[str, Any]:
    """Run deterministic Markdown memory curator."""
    agent_config = load_agent_config(agent_id)
    running = agent_config.running
    cfg = running.markdown_memory_config
    if not cfg.enabled or not cfg.curator_enabled:
        return {"skipped": True}
    store = MarkdownMemoryStore(
        working_dir=workspace_dir,
        memory_dir_name=running.daily_memory_dir,
        migrate_legacy_root_files=cfg.migrate_legacy_root_files,
    )
    result = store.curate()
    state = store.read_state()
    state["last_markdown_curator_at"] = datetime.now().astimezone().isoformat()
    store.write_state(state)
    return {**result, "llm_consolidation": cfg.llm_consolidation_enabled}
