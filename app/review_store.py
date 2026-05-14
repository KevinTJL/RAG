from __future__ import annotations

import json
import uuid
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

from app.config import settings
from app.profile_store import safe_user_id


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


class ReviewStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or settings.project_root / "db" / "review_sessions"
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, user_id: str) -> Path:
        return self.root / f"{safe_user_id(user_id)}.json"

    def load_all(self, user_id: str) -> list[dict[str, Any]]:
        path = self.path_for(user_id)
        if not path.exists():
            return []
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return []
        return data if isinstance(data, list) else []

    def save_all(self, user_id: str, sessions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        path = self.path_for(user_id)
        with path.open("w", encoding="utf-8") as f:
            json.dump(sessions, f, ensure_ascii=False, indent=2)
        return sessions

    def add(self, user_id: str, session: dict[str, Any]) -> dict[str, Any]:
        sessions = self.load_all(user_id)
        next_session = deepcopy(session)
        next_session.setdefault("id", str(uuid.uuid4()))
        next_session.setdefault("created_at", now_iso())
        sessions.insert(0, next_session)
        self.save_all(user_id, sessions[:50])
        return next_session

    def update(self, user_id: str, session_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        sessions = self.load_all(user_id)
        for session in sessions:
            if session.get("id") == session_id:
                session.update(patch)
                session["updated_at"] = now_iso()
                self.save_all(user_id, sessions)
                return session
        return None

    def get(self, user_id: str, session_id: str) -> dict[str, Any] | None:
        for session in self.load_all(user_id):
            if session.get("id") == session_id:
                return session
        return None

    def delete(self, user_id: str, session_id: str) -> bool:
        sessions = self.load_all(user_id)
        next_sessions = [session for session in sessions if session.get("id") != session_id]
        if len(next_sessions) == len(sessions):
            return False
        self.save_all(user_id, next_sessions)
        return True

    def clear(self, user_id: str) -> None:
        path = self.path_for(user_id)
        if path.exists():
            path.unlink()

    def delete_step(self, user_id: str, session_id: str, step_key: str) -> dict[str, Any] | None:
        sessions = self.load_all(user_id)
        for session in sessions:
            if session.get("id") != session_id:
                continue

            plan = session.get("plan") if isinstance(session.get("plan"), dict) else {}
            steps = plan.get("steps") if isinstance(plan.get("steps"), list) else []
            delete_index: int | None = None
            for index, step in enumerate(steps):
                if str(step.get("id", "")).strip() == step_key:
                    delete_index = index
                    break
            if delete_index is None and step_key.isdigit():
                candidate = int(step_key)
                if 0 <= candidate < len(steps):
                    delete_index = candidate
            if delete_index is None:
                return None

            deleted_step = steps[delete_index]
            deleted_step_id = str(deleted_step.get("id", "")).strip()
            next_steps = [step for index, step in enumerate(steps) if index != delete_index]
            plan["steps"] = next_steps
            answers = session.get("answers") if isinstance(session.get("answers"), dict) else {}
            if deleted_step_id:
                answers.pop(deleted_step_id, None)
            answers.pop(str(delete_index), None)
            session["answers"] = answers

            scored_steps = [step for step in next_steps if step.get("type") in {"question", "quiz"}]
            correct_count = sum(1 for item in answers.values() if item.get("is_correct"))
            session["score"] = round(correct_count / max(1, len(scored_steps)), 2)
            session["updated_at"] = now_iso()
            self.save_all(user_id, sessions)
            return session

        return None
