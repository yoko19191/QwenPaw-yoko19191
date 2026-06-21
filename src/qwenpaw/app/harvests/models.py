# -*- coding: utf-8 -*-
from __future__ import annotations

import time
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

from ..crons.models import JobRuntimeSpec, ScheduleSpec


class HarvestTarget(BaseModel):
    channel: str = "console"
    user_id: str = "harvest"
    session_id: str = "console:harvest"


class HarvestSpec(BaseModel):
    id: Optional[str] = None
    name: str = Field(min_length=1)
    template_id: str = "custom"
    emoji: str = "H"
    enabled: bool = True
    prompt: str = Field(min_length=1)
    schedule: ScheduleSpec
    target: HarvestTarget = Field(default_factory=HarvestTarget)
    runtime: JobRuntimeSpec = Field(default_factory=JobRuntimeSpec)
    cron_job_id: Optional[str] = None
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)

    @model_validator(mode="after")
    def _normalize_strings(self) -> "HarvestSpec":
        self.name = self.name.strip()
        self.template_id = (self.template_id or "custom").strip() or "custom"
        self.emoji = (self.emoji or "H").strip() or "H"
        self.prompt = self.prompt.strip()
        return self


class HarvestFile(BaseModel):
    version: int = 1
    harvests: list[HarvestSpec] = Field(default_factory=list)


class HarvestStats(BaseModel):
    total_generated: int = 0
    success_rate: int = 0
    consecutive_days: int = 0


class HarvestLastGenerated(BaseModel):
    timestamp: str
    success: bool


class HarvestView(HarvestSpec):
    status: Literal["active", "paused", "error"] = "active"
    next_run_at: Optional[str] = None
    last_generated: Optional[HarvestLastGenerated] = None
    stats: HarvestStats = Field(default_factory=HarvestStats)


class HarvestRunResponse(BaseModel):
    started: bool
    harvest: HarvestView
