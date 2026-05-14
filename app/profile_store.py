from __future__ import annotations

import json
import re
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

from app.config import settings


PROFILE_VERSION = 1


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def safe_user_id(user_id: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", user_id.strip())
    return cleaned or "default"


def default_profile(user_id: str) -> dict[str, Any]:
    return {
        "version": PROFILE_VERSION,
        "user_id": user_id,
        "updated_at": now_iso(),
        "concept_mastery": {},
        "knowledge_gaps": [],
        "misconceptions": [],
        "recommended_review": [],
        "recent_insights": [],
        "recent_questions": [],
        "abstract_evaluation": "",
        "weak_history": [],
    }


class ProfileStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or settings.project_root / "db" / "profiles"
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, user_id: str) -> Path:
        return self.root / f"{safe_user_id(user_id)}.json"

    def load(self, user_id: str) -> dict[str, Any]:
        path = self.path_for(user_id)
        if not path.exists():
            return default_profile(user_id)

        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return default_profile(user_id)

        profile = default_profile(user_id)
        profile.update(data if isinstance(data, dict) else {})
        profile["user_id"] = user_id
        return profile

    def save(self, user_id: str, profile: dict[str, Any]) -> dict[str, Any]:
        next_profile = deepcopy(profile)
        next_profile["version"] = PROFILE_VERSION
        next_profile["user_id"] = user_id
        next_profile["updated_at"] = now_iso()

        path = self.path_for(user_id)
        with path.open("w", encoding="utf-8") as f:
            json.dump(next_profile, f, ensure_ascii=False, indent=2)

        return next_profile

    def clear(self, user_id: str) -> dict[str, Any]:
        path = self.path_for(user_id)
        if path.exists():
            path.unlink()
        return default_profile(user_id)
