# -*- coding: utf-8 -*-
from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Any

from agentscope_runtime.engine.schemas.exception import ConfigurationException
from fastapi import APIRouter, Depends, HTTPException, Request

from ..agent_context import get_agent_for_request
from ..crons.api import get_cron_manager
from ..crons.manager import CronManager
from ..crons.models import (
    CronJobRequest,
    CronJobSpec,
    DispatchSpec,
    DispatchTarget,
)
from .models import HarvestRunResponse, HarvestSpec, HarvestStats, HarvestView
from .store import delete_harvest, get_harvest, list_harvests, upsert_harvest

router = APIRouter(prefix="/harvests", tags=["harvests"])


def _store_path(workspace: Any) -> Path:
    return Path(workspace.workspace_dir) / "harvests.json"


def _agent_input(prompt: str) -> list[dict[str, Any]]:
    return [
        {
            "role": "user",
            "type": "message",
            "content": [{"type": "text", "text": prompt}],
        },
    ]


def _cron_job_id(harvest_id: str) -> str:
    return f"harvest:{harvest_id}"


def _cron_spec_from_harvest(spec: HarvestSpec) -> CronJobSpec:
    assert spec.id is not None
    cron_job_id = spec.cron_job_id or _cron_job_id(spec.id)
    return CronJobSpec(
        id=cron_job_id,
        name=spec.name,
        enabled=spec.enabled,
        schedule=spec.schedule,
        task_type="agent",
        request=CronJobRequest(input=_agent_input(spec.prompt)),
        dispatch=DispatchSpec(
            channel=spec.target.channel,
            target=DispatchTarget(
                user_id=spec.target.user_id,
                session_id=spec.target.session_id,
            ),
            mode="stream",
            meta={
                "source": "harvest",
                "harvest_id": spec.id,
                "template_id": spec.template_id,
            },
        ),
        save_result_to_inbox=True,
        runtime=spec.runtime,
        meta={
            "source": "harvest",
            "harvest_id": spec.id,
            "template_id": spec.template_id,
        },
    )


async def _to_view(spec: HarvestSpec, mgr: CronManager) -> HarvestView:
    cron_job_id = spec.cron_job_id or (spec.id and _cron_job_id(spec.id))
    state = mgr.get_state(cron_job_id) if cron_job_id else None
    history = await mgr.get_history(cron_job_id) if cron_job_id else []
    completed_history = [
        record
        for record in history
        if record.status in {"success", "error", "cancelled", "skipped"}
    ]
    success_count = sum(1 for record in completed_history if record.status == "success")
    total = len(completed_history)
    success_rate = round((success_count / total) * 100) if total else 0
    last_record = completed_history[0] if completed_history else None
    status = "paused"
    if spec.enabled:
        status = "error" if state and state.last_status == "error" else "active"

    return HarvestView(
        **spec.model_dump(),
        status=status,
        next_run_at=(
            state.next_run_at.isoformat()
            if state is not None and state.next_run_at is not None
            else None
        ),
        last_generated=(
            {
                "timestamp": last_record.run_at.isoformat(),
                "success": last_record.status == "success",
            }
            if last_record is not None
            else None
        ),
        stats=HarvestStats(
            total_generated=total,
            success_rate=success_rate,
            consecutive_days=0,
        ),
    )


async def _save_and_sync_cron(
    *,
    path: Path,
    spec: HarvestSpec,
    mgr: CronManager,
) -> HarvestSpec:
    cron_spec = _cron_spec_from_harvest(spec)
    try:
        await mgr.create_or_replace_job(cron_spec)
    except (ConfigurationException, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    persisted = spec.model_copy(update={"cron_job_id": cron_spec.id})
    await upsert_harvest(path, persisted)
    return persisted


@router.get("", response_model=list[HarvestView])
async def list_harvest_tasks(
    request: Request,
    mgr: CronManager = Depends(get_cron_manager),
) -> list[HarvestView]:
    workspace = await get_agent_for_request(request)
    items = await list_harvests(_store_path(workspace))
    return [await _to_view(item, mgr) for item in items]


@router.post("", response_model=HarvestView)
async def create_harvest_task(
    spec: HarvestSpec,
    request: Request,
    mgr: CronManager = Depends(get_cron_manager),
) -> HarvestView:
    workspace = await get_agent_for_request(request)
    now = time.time()
    harvest_id = str(uuid.uuid4())
    created = spec.model_copy(
        update={
            "id": harvest_id,
            "cron_job_id": _cron_job_id(harvest_id),
            "created_at": now,
            "updated_at": now,
        },
    )
    persisted = await _save_and_sync_cron(
        path=_store_path(workspace),
        spec=created,
        mgr=mgr,
    )
    return await _to_view(persisted, mgr)


@router.put("/{harvest_id}", response_model=HarvestView)
async def replace_harvest_task(
    harvest_id: str,
    spec: HarvestSpec,
    request: Request,
    mgr: CronManager = Depends(get_cron_manager),
) -> HarvestView:
    workspace = await get_agent_for_request(request)
    path = _store_path(workspace)
    existing = await get_harvest(path, harvest_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="harvest not found")
    updated = spec.model_copy(
        update={
            "id": harvest_id,
            "cron_job_id": existing.cron_job_id or _cron_job_id(harvest_id),
            "created_at": existing.created_at,
            "updated_at": time.time(),
        },
    )
    persisted = await _save_and_sync_cron(path=path, spec=updated, mgr=mgr)
    return await _to_view(persisted, mgr)


@router.delete("/{harvest_id}")
async def delete_harvest_task(
    harvest_id: str,
    request: Request,
    mgr: CronManager = Depends(get_cron_manager),
) -> dict[str, bool]:
    workspace = await get_agent_for_request(request)
    path = _store_path(workspace)
    existing = await get_harvest(path, harvest_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="harvest not found")
    if existing.cron_job_id:
        await mgr.delete_job(existing.cron_job_id)
    await delete_harvest(path, harvest_id)
    return {"deleted": True}


@router.post("/{harvest_id}/run", response_model=HarvestRunResponse)
async def run_harvest_task(
    harvest_id: str,
    request: Request,
    mgr: CronManager = Depends(get_cron_manager),
) -> HarvestRunResponse:
    workspace = await get_agent_for_request(request)
    spec = await get_harvest(_store_path(workspace), harvest_id)
    if spec is None or not spec.cron_job_id:
        raise HTTPException(status_code=404, detail="harvest not found")
    try:
        await mgr.run_job(spec.cron_job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="cron job not found") from exc
    return HarvestRunResponse(started=True, harvest=await _to_view(spec, mgr))


async def _set_enabled(
    *,
    harvest_id: str,
    enabled: bool,
    request: Request,
    mgr: CronManager,
) -> HarvestView:
    workspace = await get_agent_for_request(request)
    path = _store_path(workspace)
    existing = await get_harvest(path, harvest_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="harvest not found")
    updated = existing.model_copy(
        update={
            "enabled": enabled,
            "updated_at": time.time(),
        },
    )
    persisted = await _save_and_sync_cron(path=path, spec=updated, mgr=mgr)
    return await _to_view(persisted, mgr)


@router.post("/{harvest_id}/pause", response_model=HarvestView)
async def pause_harvest_task(
    harvest_id: str,
    request: Request,
    mgr: CronManager = Depends(get_cron_manager),
) -> HarvestView:
    return await _set_enabled(
        harvest_id=harvest_id,
        enabled=False,
        request=request,
        mgr=mgr,
    )


@router.post("/{harvest_id}/resume", response_model=HarvestView)
async def resume_harvest_task(
    harvest_id: str,
    request: Request,
    mgr: CronManager = Depends(get_cron_manager),
) -> HarvestView:
    return await _set_enabled(
        harvest_id=harvest_id,
        enabled=True,
        request=request,
        mgr=mgr,
    )
