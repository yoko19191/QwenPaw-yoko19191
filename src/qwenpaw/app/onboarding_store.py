# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import json
import shutil
import time
from pathlib import Path

from pydantic import BaseModel, Field

_LOCK = asyncio.Lock()


class OnboardingState(BaseModel):
    completed: bool = False
    dismissed_steps: list[str] = Field(default_factory=list)
    updated_at: float = Field(default_factory=time.time)


def _read_state(path: Path) -> OnboardingState:
    if not path.exists():
        return OnboardingState()
    return OnboardingState.model_validate(
        json.loads(path.read_text(encoding="utf-8")),
    )


def _write_state(path: Path, state: OnboardingState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(
        json.dumps(
            state.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    shutil.move(str(tmp_path), str(path))


async def load_onboarding_state(path: Path) -> OnboardingState:
    async with _LOCK:
        return _read_state(path)


async def mark_onboarding_complete(path: Path) -> OnboardingState:
    async with _LOCK:
        state = _read_state(path).model_copy(
            update={"completed": True, "updated_at": time.time()},
        )
        _write_state(path, state)
        return state


async def dismiss_onboarding_step(path: Path, step_id: str) -> OnboardingState:
    async with _LOCK:
        state = _read_state(path)
        dismissed = list(dict.fromkeys([*state.dismissed_steps, step_id]))
        state = state.model_copy(
            update={
                "dismissed_steps": dismissed,
                "updated_at": time.time(),
            },
        )
        _write_state(path, state)
        return state
