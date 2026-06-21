# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..agent_context import get_agent_for_request
from ..harvests.store import list_harvests
from ..onboarding_store import (
    dismiss_onboarding_step,
    load_onboarding_state,
    mark_onboarding_complete,
)

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


class OnboardingStep(BaseModel):
    id: str
    title: str
    description: str = ""
    action_label: str = ""
    action_path: str = ""
    complete: bool = False
    optional: bool = False
    dismissed: bool = False


class OnboardingStatus(BaseModel):
    completed: bool = False
    progress: float = Field(ge=0, le=1)
    steps: list[OnboardingStep] = Field(default_factory=list)


def _state_path(workspace: Any) -> Path:
    return Path(workspace.workspace_dir) / "onboarding.json"


async def _has_harvests(workspace: Any) -> bool:
    return bool(await list_harvests(Path(workspace.workspace_dir) / "harvests.json"))


def _has_active_model(request: Request, workspace: Any) -> bool:
    active_model = getattr(workspace.config, "active_model", None)
    if (
        active_model is not None
        and getattr(active_model, "provider_id", "")
        and getattr(active_model, "model", "")
    ):
        return True
    provider_manager = getattr(request.app.state, "provider_manager", None)
    if provider_manager is None:
        return False
    try:
        global_model = provider_manager.get_active_model()
    except Exception:  # pylint: disable=broad-except
        return False
    return bool(
        global_model
        and getattr(global_model, "provider_id", "")
        and getattr(global_model, "model", "")
    )


def _has_external_channel(workspace: Any) -> bool:
    channels = workspace.config.channels
    if channels is None:
        return False
    data = channels.model_dump()
    extra = getattr(channels, "__pydantic_extra__", None) or {}
    data.update(extra)
    for key, value in data.items():
        if key == "console":
            continue
        if isinstance(value, dict) and value.get("enabled") is True:
            return True
        if getattr(value, "enabled", False) is True:
            return True
    return False


async def _build_status(request: Request) -> OnboardingStatus:
    workspace = await get_agent_for_request(request)
    state = await load_onboarding_state(_state_path(workspace))
    dismissed = set(state.dismissed_steps)
    steps = [
        OnboardingStep(
            id="model",
            title="Configure a model",
            description="Select the LLM this agent should use.",
            action_label="Open Models",
            action_path="/models",
            complete=_has_active_model(request, workspace),
            dismissed="model" in dismissed,
        ),
        OnboardingStep(
            id="channel",
            title="Connect a channel",
            description="Enable at least one non-console channel.",
            action_label="Open Channels",
            action_path="/channels",
            complete=_has_external_channel(workspace),
            optional=True,
            dismissed="channel" in dismissed,
        ),
        OnboardingStep(
            id="harvest",
            title="Create an Inbox harvest",
            description="Schedule a real AI harvest into Inbox.",
            action_label="Open Inbox",
            action_path="/inbox",
            complete=await _has_harvests(workspace),
            optional=True,
            dismissed="harvest" in dismissed,
        ),
    ]
    progress = sum(1 for step in steps if step.complete) / len(steps) if steps else 1.0
    return OnboardingStatus(
        completed=state.completed,
        progress=progress,
        steps=steps,
    )


@router.get("/status", response_model=OnboardingStatus)
async def get_onboarding_status(request: Request) -> OnboardingStatus:
    return await _build_status(request)


@router.post("/complete", response_model=OnboardingStatus)
async def complete_onboarding(request: Request) -> OnboardingStatus:
    workspace = await get_agent_for_request(request)
    await mark_onboarding_complete(_state_path(workspace))
    return await _build_status(request)


@router.post("/steps/{step_id}/dismiss", response_model=OnboardingStatus)
async def dismiss_step(step_id: str, request: Request) -> OnboardingStatus:
    if step_id not in {"model", "channel", "harvest"}:
        raise HTTPException(status_code=404, detail="step not found")
    workspace = await get_agent_for_request(request)
    await dismiss_onboarding_step(_state_path(workspace), step_id)
    return await _build_status(request)
