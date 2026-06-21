# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path

from .models import HarvestFile, HarvestSpec

_LOCK = asyncio.Lock()


def _read_file(path: Path) -> HarvestFile:
    if not path.exists():
        return HarvestFile()
    data = json.loads(path.read_text(encoding="utf-8"))
    return HarvestFile.model_validate(data)


def _write_file(path: Path, payload: HarvestFile) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(
        json.dumps(
            payload.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    shutil.move(str(tmp_path), str(path))


async def list_harvests(path: Path) -> list[HarvestSpec]:
    async with _LOCK:
        return _read_file(path).harvests


async def get_harvest(path: Path, harvest_id: str) -> HarvestSpec | None:
    async with _LOCK:
        for harvest in _read_file(path).harvests:
            if harvest.id == harvest_id:
                return harvest
    return None


async def upsert_harvest(path: Path, spec: HarvestSpec) -> None:
    async with _LOCK:
        payload = _read_file(path)
        for index, existing in enumerate(payload.harvests):
            if existing.id == spec.id:
                payload.harvests[index] = spec
                break
        else:
            payload.harvests.append(spec)
        _write_file(path, payload)


async def delete_harvest(path: Path, harvest_id: str) -> bool:
    async with _LOCK:
        payload = _read_file(path)
        before = len(payload.harvests)
        payload.harvests = [
            harvest for harvest in payload.harvests if harvest.id != harvest_id
        ]
        if len(payload.harvests) == before:
            return False
        _write_file(path, payload)
        return True
