# -*- coding: utf-8 -*-
"""File-backed Markdown long-term memory store."""

from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from ..utils.file_handling import read_text_file_with_encoding_fallback

MemoryAction = Literal["add", "replace", "remove"]


class MarkdownMemoryStore:
    """Manage workspace ``memory/`` Markdown files safely."""

    LONG_TERM_FILE = "MEMORY.md"
    USER_FILE = "USER.md"
    STATE_DIR = ".state"
    STATE_FILE = "learning.json"

    def __init__(
        self,
        working_dir: str | Path,
        *,
        memory_dir_name: str = "memory",
        migrate_legacy_root_files: bool = True,
    ) -> None:
        self.working_dir = Path(working_dir).expanduser().resolve()
        self.memory_dir = (self.working_dir / memory_dir_name).resolve()
        self.state_dir = self.memory_dir / self.STATE_DIR
        self.state_path = self.state_dir / self.STATE_FILE
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_core_files()
        if migrate_legacy_root_files:
            self.migrate_legacy_root_files()

    def _ensure_core_files(self) -> None:
        defaults = {
            self.LONG_TERM_FILE: "# Long-Term Memory\n",
            self.USER_FILE: "# User Memory\n",
        }
        for filename, content in defaults.items():
            path = self.memory_dir / filename
            if not path.exists():
                self._atomic_write(path, content)
        if not self.state_path.exists():
            self._atomic_write(
                self.state_path,
                json.dumps(
                    {
                        "memory_turn_count": 0,
                        "skill_turn_count": 0,
                        "last_memory_review_at": None,
                        "last_skill_review_at": None,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
            )

    def migrate_legacy_root_files(self) -> dict[str, bool]:
        """Copy legacy root memory files into canonical ``memory/`` files."""
        state = self.read_state()
        migrations = state.setdefault("migrations", {})
        result = {"memory": False, "user": False}
        mapping = {
            "memory": (self.working_dir / "MEMORY.md", self.LONG_TERM_FILE),
            "user": (self.working_dir / "PROFILE.md", self.USER_FILE),
        }
        for key, (src, target_name) in mapping.items():
            if migrations.get(key) or not src.exists():
                continue
            content = read_text_file_with_encoding_fallback(src).strip()
            if not content:
                migrations[key] = True
                continue
            target = self.memory_dir / target_name
            current = self.read(target_name).strip()
            marker = f"\n\n## Migrated from {src.name}\n\n"
            if content not in current:
                next_content = (current or f"# {target.stem.title()}\n")
                next_content = next_content.rstrip() + marker + content + "\n"
                self._atomic_write(target, next_content)
            migrations[key] = True
            result[key] = True
        if result["memory"] or result["user"]:
            self.write_state(state)
        return result

    def resolve_memory_path(self, target: str | None) -> Path:
        """Resolve a caller-provided Markdown target under ``memory/``."""
        raw = (target or self.LONG_TERM_FILE).strip().replace("\\", "/")
        if not raw:
            raw = self.LONG_TERM_FILE
        if raw.startswith("memory/"):
            raw = raw[len("memory/") :]
        if raw.startswith("/") or raw.startswith(".") or ".." in raw.split("/"):
            raise ValueError("memory target must be a safe relative path")
        if raw.startswith(f"{self.STATE_DIR}/"):
            raise ValueError("memory state files are internal")
        if not raw.endswith(".md"):
            raw += ".md"
        path = (self.memory_dir / raw).resolve()
        base = self.memory_dir.resolve()
        try:
            path.relative_to(base)
        except ValueError as exc:
            raise ValueError("memory target escapes memory directory") from exc
        if any(part.startswith(".") for part in path.relative_to(base).parts):
            raise ValueError("hidden memory files are not writable")
        return path

    def read(self, target: str | None = None) -> str:
        path = self.resolve_memory_path(target)
        if not path.exists():
            return ""
        return read_text_file_with_encoding_fallback(path)

    def apply(
        self,
        *,
        action: MemoryAction,
        target: str | None = None,
        content: str = "",
        old_text: str = "",
        source: str = "agent",
    ) -> dict[str, Any]:
        path = self.resolve_memory_path(target)
        path.parent.mkdir(parents=True, exist_ok=True)
        current = (
            read_text_file_with_encoding_fallback(path) if path.exists() else ""
        )
        if action == "add":
            entry = self._format_entry(content=content, source=source)
            next_content = current.rstrip() + "\n\n" + entry + "\n"
        elif action == "replace":
            if not old_text:
                return {"success": False, "reason": "old_text_required"}
            if old_text not in current:
                return {"success": False, "reason": "old_text_not_found"}
            next_content = current.replace(old_text, content, 1)
        elif action == "remove":
            if not old_text:
                return {"success": False, "reason": "old_text_required"}
            if old_text not in current:
                return {"success": False, "reason": "old_text_not_found"}
            next_content = current.replace(old_text, "", 1)
        else:
            return {"success": False, "reason": "invalid_action"}
        self._atomic_write(path, next_content)
        return {
            "success": True,
            "action": action,
            "target": str(path.relative_to(self.memory_dir)),
        }

    def apply_batch(self, operations: list[dict[str, Any]]) -> dict[str, Any]:
        results = []
        for operation in operations:
            results.append(
                self.apply(
                    action=str(operation.get("action", "")),  # type: ignore[arg-type]
                    target=operation.get("target"),
                    content=str(operation.get("content", "") or ""),
                    old_text=str(operation.get("old_text", "") or ""),
                    source=str(operation.get("source", "agent") or "agent"),
                ),
            )
        return {
            "success": all(result.get("success") for result in results),
            "results": results,
        }

    def _snapshot_files(self) -> list[Path]:
        files = [
            self.memory_dir / self.LONG_TERM_FILE,
            self.memory_dir / self.USER_FILE,
        ]
        files.extend(sorted(self.memory_dir.glob("????-??-??.md"), reverse=True))
        files.extend(sorted((self.memory_dir / "topics").glob("*.md")))
        return files

    def build_prompt_snapshot(self, max_chars: int) -> str:
        """Return bounded long-term memory snapshot for system prompt."""
        parts: list[str] = []
        remaining = max_chars
        for path in self._snapshot_files():
            if not path.exists() or not path.is_file():
                continue
            content = read_text_file_with_encoding_fallback(path).strip()
            if content:
                block = f"### memory/{path.relative_to(self.memory_dir)}\n{content}"
                if len(block) > remaining:
                    block = block[:remaining].rstrip()
                parts.append(block)
                remaining -= len(block)
                if remaining <= 0:
                    break
        snapshot = "\n\n".join(parts).strip()
        if len(snapshot) > max_chars:
            snapshot = snapshot[:max_chars].rstrip()
        return snapshot

    def curate(self) -> dict[str, Any]:
        """Run deterministic Markdown memory maintenance."""
        changed_files: list[str] = []
        removed_entries = 0
        for path in self._snapshot_files():
            if not path.exists() or not path.is_file():
                continue
            original = read_text_file_with_encoding_fallback(path)
            curated, removed = self._dedupe_delimited_entries(original)
            if removed <= 0:
                continue
            self._atomic_write(path, curated)
            changed_files.append(str(path.relative_to(self.working_dir)))
            removed_entries += removed
        return {
            "success": True,
            "changed_files": changed_files,
            "removed_entries": removed_entries,
        }

    @staticmethod
    def _dedupe_delimited_entries(text: str) -> tuple[str, int]:
        pattern = re.compile(r"\n§\n(?P<body>.*?)\n§\n", re.DOTALL)
        matches = list(pattern.finditer(text))
        if not matches:
            return text, 0
        prefix = text[: matches[0].start()].rstrip()
        suffix = text[matches[-1].end() :].strip()
        seen: set[str] = set()
        bodies: list[str] = []
        removed = 0
        for match in matches:
            body = match.group("body").strip()
            key = MarkdownMemoryStore._entry_dedupe_key(body)
            if key in seen:
                removed += 1
                continue
            seen.add(key)
            bodies.append(body)
        rebuilt = prefix
        for body in bodies:
            rebuilt += f"\n\n§\n{body}\n§\n"
        if suffix:
            rebuilt += f"\n\n{suffix}\n"
        return rebuilt.rstrip() + "\n", removed

    @staticmethod
    def _entry_dedupe_key(body: str) -> str:
        lines = [
            line.strip()
            for line in body.splitlines()
            if not line.strip().startswith("- time:")
        ]
        return "\n".join(lines).strip()

    def read_state(self) -> dict[str, Any]:
        try:
            return json.loads(read_text_file_with_encoding_fallback(self.state_path))
        except Exception:
            return {}

    def write_state(self, state: dict[str, Any]) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self._atomic_write(
            self.state_path,
            json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        )

    def bump_counter(self, key: str) -> int:
        state = self.read_state()
        value = int(state.get(key, 0) or 0) + 1
        state[key] = value
        self.write_state(state)
        return value

    @staticmethod
    def _format_entry(*, content: str, source: str) -> str:
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        body = content.strip()
        return f"§\n- time: {now}\n- source: {source}\n\n{body}\n§"

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=str(path.parent),
            text=True,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(content)
            os.replace(tmp_name, path)
        finally:
            try:
                os.unlink(tmp_name)
            except FileNotFoundError:
                pass
