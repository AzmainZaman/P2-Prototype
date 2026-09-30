"""Versioned local records for question configurations (Report §4.6, NFR-08).

Each saved version is one UTF-8 JSON file named <question_id>-v<version>.json.
Files are created exclusively and marked read-only; editing a question always
produces a new version, so earlier configurations are never overwritten.
"""
from __future__ import annotations

import hashlib
import json
import os
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from .models import Configuration
from .validation import Issue, has_errors, validate

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_DIR = PROJECT_ROOT / "data" / "configs"
DEFAULT_SEED_DIR = PROJECT_ROOT / "data" / "seed"


class ValidationFailed(Exception):
    def __init__(self, issues: List[Issue]):
        super().__init__("Configuration has validation errors.")
        self.issues = issues


class NoChanges(Exception):
    pass


def compute_hash(cfg: Configuration) -> str:
    payload = json.dumps(cfg.content_dict(), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class Store:
    def __init__(self, config_dir: Path = DEFAULT_CONFIG_DIR):
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(parents=True, exist_ok=True)

    # --- Reading -----------------------------------------------------------
    def all_configs(self) -> List[Configuration]:
        configs = []
        for path in sorted(self.config_dir.glob("*.json")):
            with path.open(encoding="utf-8") as f:
                configs.append(Configuration.from_dict(json.load(f)))
        return sorted(configs, key=lambda c: (c.question_id, c.version or 0))

    def question_ids(self) -> List[str]:
        return sorted({c.question_id for c in self.all_configs()})

    def versions(self, question_id: str) -> List[Configuration]:
        return [c for c in self.all_configs() if c.question_id == question_id]

    def latest(self, question_id: str) -> Optional[Configuration]:
        versions = self.versions(question_id)
        return versions[-1] if versions else None

    def load(self, config_id: str) -> Optional[Configuration]:
        path = self.config_dir / f"{config_id}.json"
        if not path.exists():
            return None
        with path.open(encoding="utf-8") as f:
            return Configuration.from_dict(json.load(f))

    def verify(self, cfg: Configuration) -> bool:
        """True when the stored content still matches the hash recorded at save time."""
        return cfg.content_hash == compute_hash(cfg)

    def next_question_id(self) -> str:
        existing = set(self.question_ids())
        n = 1
        while f"Q{n:02d}" in existing:
            n += 1
        return f"Q{n:02d}"

    # --- Writing -----------------------------------------------------------
    def save_new_version(self, draft: Configuration, parent_config_id: Optional[str] = None) -> Configuration:
        """Validate and save the draft as the next immutable version of its question."""
        draft = draft.as_draft()
        draft.question_id = draft.question_id.strip()
        issues = validate(draft, self.question_ids(), is_new_question=parent_config_id is None)
        if has_errors(issues):
            raise ValidationFailed(issues)

        latest = self.latest(draft.question_id)
        content_hash = compute_hash(draft)
        if latest is not None and latest.content_hash == content_hash:
            raise NoChanges(f"No changes since {latest.config_id}.")

        draft.version = (latest.version if latest else 0) + 1
        draft.config_id = f"{draft.question_id}-v{draft.version}"
        draft.created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        draft.content_hash = content_hash
        draft.parent_config_id = parent_config_id

        path = self.config_dir / f"{draft.config_id}.json"
        with path.open("x", encoding="utf-8") as f:  # "x" refuses to overwrite
            json.dump(draft.to_dict(), f, ensure_ascii=False, indent=2)
        os.chmod(path, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
        return draft

    def ensure_seed(self, seed_dir: Path = DEFAULT_SEED_DIR) -> None:
        """Load the bundled example questions the first time the store is empty."""
        if any(self.config_dir.glob("*.json")) or not seed_dir.exists():
            return
        for path in sorted(seed_dir.glob("*.json")):
            with path.open(encoding="utf-8") as f:
                self.save_new_version(Configuration.from_dict(json.load(f)))
