# -*- coding: utf-8 -*-
"""Workspace skill memory lifecycle helpers."""

from __future__ import annotations

import re
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ...exceptions import SkillsError
from ..utils.file_handling import read_text_file_with_encoding_fallback
from .registry import reconcile_workspace_manifest
from .store import (
    copy_skill_dir,
    default_workspace_manifest,
    get_workspace_skill_manifest_path,
    get_workspace_skills_dir,
    mutate_json,
    normalize_skill_dir_name,
    read_json,
    read_skill_from_dir,
    read_skill_manifest,
    safe_skill_dir,
    scan_skill_dir_or_raise,
    staged_skill_dir,
    write_json_atomic,
)
from .workspace_service import SkillService


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


class SkillMemoryService:
    """Skill lifecycle manager for procedural memory."""

    def __init__(self, workspace_dir: str | Path):
        self.workspace_dir = Path(workspace_dir).expanduser()
        self.skill_root = get_workspace_skills_dir(self.workspace_dir)
        self.meta_dir = self.skill_root / ".qwenpaw"
        self.archive_dir = self.skill_root / ".archive"
        self.proposals_dir = self.meta_dir / "proposals"
        self.state_path = self.meta_dir / "skill_memory.json"
        self.meta_dir.mkdir(parents=True, exist_ok=True)
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        self.proposals_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def default_state() -> dict[str, Any]:
        return {
            "schema_version": "qwenpaw-skill-memory.v1",
            "version": 0,
            "skills": {},
            "proposals": {},
        }

    def read_state(self) -> dict[str, Any]:
        return read_json(self.state_path, self.default_state())

    def write_state(self, state: dict[str, Any]) -> None:
        write_json_atomic(self.state_path, state)

    def _mutate_state(self, mutator) -> Any:
        return mutate_json(self.state_path, self.default_state(), mutator)

    def _record_for(self, payload: dict[str, Any], skill_name: str) -> dict[str, Any]:
        skills = payload.setdefault("skills", {})
        record = skills.setdefault(
            skill_name,
            {
                "created_at": _now_iso(),
                "updated_at": _now_iso(),
                "last_used_at": None,
                "use_count": 0,
                "last_reviewed_at": None,
                "failure_count": 0,
                "stale_since": None,
                "stale_passes": 0,
                "pinned": False,
                "archived_at": None,
                "archive_id": None,
                "archive_reason": None,
                "archive_path": None,
                "derived_from": [],
            },
        )
        record.setdefault("created_at", _now_iso())
        record.setdefault("use_count", 0)
        record.setdefault("failure_count", 0)
        record.setdefault("pinned", False)
        record.setdefault("derived_from", [])
        return record

    def list_skill_records(self) -> dict[str, Any]:
        return dict(self.read_state().get("skills", {}) or {})

    def get_skill_record(self, skill_name: str) -> dict[str, Any]:
        state = self.read_state()
        name = normalize_skill_dir_name(skill_name)
        return dict(state.get("skills", {}).get(name, {}) or {})

    def record_usage(self, skill_name: str, *, source: str = "runtime") -> None:
        name = normalize_skill_dir_name(skill_name)

        def _update(payload: dict[str, Any]) -> None:
            record = self._record_for(payload, name)
            record["last_used_at"] = _now_iso()
            record["updated_at"] = _now_iso()
            record["use_count"] = int(record.get("use_count", 0) or 0) + 1
            record["last_source"] = source
            record["stale_since"] = None
            record["stale_passes"] = 0

        self._mutate_state(_update)

    def record_review(self, skill_name: str, *, source: str = "review") -> None:
        name = normalize_skill_dir_name(skill_name)

        def _update(payload: dict[str, Any]) -> None:
            record = self._record_for(payload, name)
            record["last_reviewed_at"] = _now_iso()
            record["updated_at"] = _now_iso()
            record["last_source"] = source

        self._mutate_state(_update)

    def set_pinned(self, skill_name: str, pinned: bool) -> dict[str, Any]:
        name = normalize_skill_dir_name(skill_name)

        def _update(payload: dict[str, Any]) -> dict[str, Any]:
            record = self._record_for(payload, name)
            record["pinned"] = bool(pinned)
            record["updated_at"] = _now_iso()
            return record

        return self._mutate_state(_update)

    def create_skill(
        self,
        *,
        name: str,
        content: str,
        extra_files: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        created = SkillService(self.workspace_dir).create_skill(
            name=name,
            content=content,
            extra_files=extra_files,
            enable=True,
            source="agent",
        )
        if not created:
            return {"success": False, "reason": "conflict"}
        self.record_review(created, source="create")
        return {"success": True, "name": created}

    def patch_skill(
        self,
        *,
        skill_name: str,
        old_text: str,
        new_text: str,
    ) -> dict[str, Any]:
        name = normalize_skill_dir_name(skill_name)
        skill_dir = safe_skill_dir(self.skill_root, name)
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            return {"success": False, "reason": "not_found"}
        current = read_text_file_with_encoding_fallback(skill_md)
        if old_text not in current:
            return {"success": False, "reason": "old_text_not_found"}
        content = current.replace(old_text, new_text, 1)
        result = SkillService(self.workspace_dir).save_skill(
            skill_name=name,
            content=content,
        )
        if result.get("success"):
            self.record_review(name, source="patch")
        return result

    def write_skill_file(
        self,
        *,
        skill_name: str,
        file_path: str,
        content: str,
    ) -> dict[str, Any]:
        name = normalize_skill_dir_name(skill_name)
        relative = self._validate_extra_file_path(file_path)
        skill_dir = safe_skill_dir(self.skill_root, name)
        if not skill_dir.exists():
            return {"success": False, "reason": "not_found"}
        with staged_skill_dir(name) as staged_dir:
            copy_skill_dir(skill_dir, staged_dir)
            target = (staged_dir / relative).resolve()
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            scan_skill_dir_or_raise(staged_dir, name)
            copy_skill_dir(staged_dir, skill_dir)
        reconcile_workspace_manifest(self.workspace_dir)
        self.record_review(name, source="write_file")
        return {"success": True, "name": name, "file_path": relative}

    @staticmethod
    def _validate_extra_file_path(file_path: str) -> str:
        normalized = file_path.strip().replace("\\", "/")
        allowed = ("references/", "scripts/", "assets/")
        if (
            not normalized
            or normalized.startswith("/")
            or ".." in normalized.split("/")
            or not normalized.startswith(allowed)
            or any(part.startswith(".") for part in normalized.split("/"))
        ):
            raise SkillsError(
                message=(
                    "skill file path must be under references/, scripts/, "
                    "or assets/"
                ),
            )
        return normalized

    def archive_skill(
        self,
        skill_name: str,
        *,
        reason: str = "manual",
    ) -> dict[str, Any]:
        name = normalize_skill_dir_name(skill_name)
        manifest = read_skill_manifest(self.workspace_dir)
        entry = manifest.get("skills", {}).get(name)
        skill_dir = safe_skill_dir(self.skill_root, name)
        if entry is None or not skill_dir.exists():
            return {"success": False, "reason": "not_found"}

        SkillService(self.workspace_dir).disable_skill(name)
        archive_id = self._unique_archive_id(name)
        target_dir = safe_skill_dir(self.archive_dir, archive_id)
        shutil.move(str(skill_dir), str(target_dir))

        def _remove(payload: dict[str, Any]) -> None:
            payload.get("skills", {}).pop(name, None)

        mutate_json(
            get_workspace_skill_manifest_path(self.workspace_dir),
            default_workspace_manifest(),
            _remove,
        )

        def _update(payload: dict[str, Any]) -> None:
            record = self._record_for(payload, name)
            record["updated_at"] = _now_iso()
            record["archived_at"] = _now_iso()
            record["archive_id"] = archive_id
            record["archive_reason"] = reason
            record["archive_path"] = str(target_dir)
            record["manifest_entry"] = entry

        self._mutate_state(_update)
        return {"success": True, "name": name, "archive_id": archive_id}

    def restore_skill(self, archive_id: str) -> dict[str, Any]:
        state = self.read_state()
        skill_name = ""
        record: dict[str, Any] | None = None
        for name, candidate in (state.get("skills", {}) or {}).items():
            if candidate.get("archive_id") == archive_id:
                skill_name = name
                record = candidate
                break
        if record is None:
            skill_name = normalize_skill_dir_name(archive_id)
            record = state.get("skills", {}).get(skill_name)
        if record is None:
            return {"success": False, "reason": "not_found"}

        archive_path = Path(str(record.get("archive_path") or ""))
        if not archive_path.exists():
            archive_path = safe_skill_dir(self.archive_dir, archive_id)
        if not archive_path.exists():
            return {"success": False, "reason": "archive_missing"}

        target_dir = safe_skill_dir(self.skill_root, skill_name)
        if target_dir.exists():
            return {"success": False, "reason": "target_exists"}
        scan_skill_dir_or_raise(archive_path, skill_name)
        shutil.move(str(archive_path), str(target_dir))
        manifest_entry = dict(record.get("manifest_entry") or {})
        manifest_entry["enabled"] = False

        def _restore(payload: dict[str, Any]) -> None:
            payload.setdefault("skills", {})
            payload["skills"][skill_name] = manifest_entry

        mutate_json(
            get_workspace_skill_manifest_path(self.workspace_dir),
            default_workspace_manifest(),
            _restore,
        )
        reconcile_workspace_manifest(self.workspace_dir)

        def _update(payload: dict[str, Any]) -> None:
            restored = self._record_for(payload, skill_name)
            restored["updated_at"] = _now_iso()
            restored["archived_at"] = None
            restored["archive_id"] = None
            restored["archive_reason"] = None
            restored["archive_path"] = None

        self._mutate_state(_update)
        return {"success": True, "name": skill_name}

    def list_archived_skills(self) -> list[dict[str, Any]]:
        state = self.read_state()
        archived: list[dict[str, Any]] = []
        for name, record in sorted((state.get("skills", {}) or {}).items()):
            if not record.get("archived_at"):
                continue
            archive_id = str(record.get("archive_id") or name)
            archive_path = Path(str(record.get("archive_path") or ""))
            content = ""
            if (archive_path / "SKILL.md").exists():
                content = read_text_file_with_encoding_fallback(
                    archive_path / "SKILL.md",
                )
            archived.append(
                {
                    "archive_id": archive_id,
                    "name": name,
                    "content": content,
                    "archived_at": record.get("archived_at"),
                    "archive_reason": record.get("archive_reason"),
                    "use_count": record.get("use_count", 0),
                    "last_used_at": record.get("last_used_at"),
                    "pinned": bool(record.get("pinned", False)),
                },
            )
        return archived

    def create_merge_proposal(
        self,
        *,
        source_skills: list[str],
        suggested_name: str,
        merged_content: str,
        reason: str,
    ) -> dict[str, Any]:
        names = [normalize_skill_dir_name(name) for name in source_skills]
        proposal_id = f"{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-merge"
        path = self.proposals_dir / f"{proposal_id}.md"
        body = (
            f"# Skill Merge Proposal: {suggested_name}\n\n"
            f"- source_skills: {', '.join(names)}\n"
            f"- suggested_name: {suggested_name}\n"
            f"- reason: {reason}\n\n"
            "## Draft SKILL.md\n\n"
            "```markdown\n"
            f"{merged_content.strip()}\n"
            "```\n"
        )
        path.write_text(body, encoding="utf-8")

        def _update(payload: dict[str, Any]) -> None:
            payload.setdefault("proposals", {})
            payload["proposals"][proposal_id] = {
                "id": proposal_id,
                "type": "merge",
                "source_skills": names,
                "suggested_name": suggested_name,
                "merged_content": merged_content,
                "reason": reason,
                "created_at": _now_iso(),
                "path": str(path),
            }

        self._mutate_state(_update)
        return {"success": True, "proposal_id": proposal_id, "path": str(path)}

    def list_proposals(self) -> list[dict[str, Any]]:
        state = self.read_state()
        proposals = []
        for proposal in sorted(
            (state.get("proposals", {}) or {}).values(),
            key=lambda item: str(item.get("created_at", "")),
            reverse=True,
        ):
            path = Path(str(proposal.get("path") or ""))
            content = ""
            if path.exists():
                content = read_text_file_with_encoding_fallback(path)
            proposals.append({**proposal, "content": content})
        return proposals

    def delete_proposal(self, proposal_id: str) -> bool:
        state = self.read_state()
        proposal = (state.get("proposals", {}) or {}).get(proposal_id)
        if proposal is None:
            return False
        path = Path(str(proposal.get("path") or ""))
        if path.exists():
            path.unlink()

        def _delete(payload: dict[str, Any]) -> None:
            payload.get("proposals", {}).pop(proposal_id, None)

        self._mutate_state(_delete)
        return True

    def apply_proposal(
        self,
        proposal_id: str,
        *,
        auto_merge: bool = False,
    ) -> dict[str, Any]:
        proposal = (self.read_state().get("proposals", {}) or {}).get(proposal_id)
        if proposal is None:
            return {"success": False, "reason": "not_found"}
        if proposal.get("type") != "merge":
            return {"success": False, "reason": "unsupported_type"}
        return self.merge_skills(
            source_skills=list(proposal.get("source_skills") or []),
            suggested_name=str(proposal.get("suggested_name") or ""),
            merged_content=str(proposal.get("merged_content") or ""),
            auto_merge=auto_merge,
            proposal_id=proposal_id,
        )

    def merge_skills(
        self,
        *,
        source_skills: list[str],
        suggested_name: str,
        merged_content: str,
        auto_merge: bool = False,
        proposal_id: str | None = None,
    ) -> dict[str, Any]:
        names = [normalize_skill_dir_name(name) for name in source_skills]
        if not auto_merge:
            return self.create_merge_proposal(
                source_skills=names,
                suggested_name=suggested_name,
                merged_content=merged_content,
                reason="auto_merge_disabled",
            )
        manifest = read_skill_manifest(self.workspace_dir)
        entries = manifest.get("skills", {}) or {}
        records = self.list_skill_records()
        normalized_suggested = (
            normalize_skill_dir_name(suggested_name)
            if suggested_name
            else ""
        )
        candidates = [name for name in names if name in entries]
        if normalized_suggested in candidates:
            primary_name = normalized_suggested
        elif candidates:
            primary_name = max(
                candidates,
                key=lambda item: int(
                    (records.get(item, {}) or {}).get("use_count", 0) or 0,
                ),
            )
        elif normalized_suggested in entries:
            primary_name = normalized_suggested
        else:
            primary_name = ""

        if primary_name:
            saved = SkillService(self.workspace_dir).save_skill(
                skill_name=primary_name,
                content=merged_content,
            )
            if not saved.get("success"):
                return saved
            self.record_review(primary_name, source="merge")
            new_name = str(saved.get("name") or primary_name)
        else:
            created = self.create_skill(
                name=normalized_suggested or "merged_skill",
                content=merged_content,
            )
            if not created.get("success"):
                return created
            new_name = str(created["name"])

        def _update(payload: dict[str, Any]) -> None:
            record = self._record_for(payload, new_name)
            record["derived_from"] = names
            record["updated_at"] = _now_iso()

        self._mutate_state(_update)
        for name in names:
            if name != new_name:
                self.archive_skill(name, reason=f"merged_into:{new_name}")
        if proposal_id:
            self.delete_proposal(proposal_id)
        return {"success": True, "name": new_name, "derived_from": names}

    def curate(self, config: Any) -> dict[str, Any]:
        archived: list[dict[str, Any]] = []
        proposals: list[dict[str, Any]] = []
        if getattr(config, "auto_archive_enabled", True):
            archived = self._archive_stale_skills(config)
        if getattr(config, "merge_proposals_enabled", True):
            proposals = self._generate_merge_proposals(config)
        return {"archived": archived, "proposals": proposals}

    def _archive_stale_skills(self, config: Any) -> list[dict[str, Any]]:
        manifest = read_skill_manifest(self.workspace_dir)
        now = datetime.now(timezone.utc)
        threshold = now - timedelta(days=int(config.archive_after_days))
        archived: list[dict[str, Any]] = []

        def _mark_stale(payload: dict[str, Any]) -> None:
            for name, entry in manifest.get("skills", {}).items():
                record = self._record_for(payload, name)
                if record.get("pinned"):
                    continue
                if entry.get("enabled", False):
                    continue
                last_used = _parse_iso(record.get("last_used_at"))
                use_count = int(record.get("use_count", 0) or 0)
                never_or_old = last_used is None or last_used < threshold
                low_use = use_count <= int(config.archive_min_uses)
                if not (never_or_old and low_use):
                    record["stale_since"] = None
                    record["stale_passes"] = 0
                    continue
                record["stale_since"] = record.get("stale_since") or _now_iso()
                record["stale_passes"] = int(record.get("stale_passes", 0) or 0) + 1

        self._mutate_state(_mark_stale)

        state = self.read_state()
        passes_required = int(config.stale_passes_before_archive)
        for name, record in (state.get("skills", {}) or {}).items():
            if record.get("archived_at") or record.get("pinned"):
                continue
            if int(record.get("stale_passes", 0) or 0) >= passes_required:
                result = self.archive_skill(name, reason="stale")
                if result.get("success"):
                    archived.append(result)
        return archived

    def _generate_merge_proposals(self, config: Any) -> list[dict[str, Any]]:
        del config
        manifest = read_skill_manifest(self.workspace_dir)
        skill_infos: list[dict[str, str]] = []
        for name, entry in manifest.get("skills", {}).items():
            if not entry.get("enabled", False):
                continue
            skill = read_skill_from_dir(self.skill_root / name, entry.get("source", "customized"))
            if skill is None:
                continue
            skill_infos.append(
                {
                    "name": name,
                    "description": skill.description or "",
                    "content": skill.content or "",
                },
            )
        existing = {
            tuple(sorted(proposal.get("source_skills") or []))
            for proposal in self.list_proposals()
        }
        created: list[dict[str, Any]] = []
        for i, left in enumerate(skill_infos):
            for right in skill_infos[i + 1 :]:
                pair = tuple(sorted([left["name"], right["name"]]))
                if pair in existing:
                    continue
                if self._looks_overlapping(left, right):
                    merged_name = left["name"]
                    merged_content = self._draft_merged_skill(left, right)
                    created.append(
                        self.create_merge_proposal(
                            source_skills=list(pair),
                            suggested_name=merged_name,
                            merged_content=merged_content,
                            reason="similar trigger or description",
                        ),
                    )
                    existing.add(pair)
        return created

    @staticmethod
    def _token_set(text: str) -> set[str]:
        return {
            token.lower()
            for token in re.findall(r"[A-Za-z0-9_\-\u4e00-\u9fff]+", text)
            if len(token.strip()) > 1
        }

    @classmethod
    def _looks_overlapping(cls, left: dict[str, str], right: dict[str, str]) -> bool:
        left_tokens = cls._token_set(left["name"] + " " + left["description"])
        right_tokens = cls._token_set(right["name"] + " " + right["description"])
        if not left_tokens or not right_tokens:
            return False
        overlap = len(left_tokens & right_tokens) / max(
            min(len(left_tokens), len(right_tokens)),
            1,
        )
        return overlap >= 0.6

    @staticmethod
    def _draft_merged_skill(left: dict[str, str], right: dict[str, str]) -> str:
        description = left["description"] or right["description"]
        return (
            "---\n"
            f"name: {left['name']}\n"
            f"description: {description}\n"
            "---\n\n"
            f"# {left['name']}\n\n"
            "## Consolidated Sources\n\n"
            f"- {left['name']}\n"
            f"- {right['name']}\n\n"
            "## Existing Instructions\n\n"
            f"### {left['name']}\n\n{left['content'].strip()}\n\n"
            f"### {right['name']}\n\n{right['content'].strip()}\n"
        )

    def _unique_archive_id(self, skill_name: str) -> str:
        base = normalize_skill_dir_name(skill_name)
        candidate = base
        if not (self.archive_dir / candidate).exists():
            return candidate
        suffix = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        return f"{base}-{suffix}"
