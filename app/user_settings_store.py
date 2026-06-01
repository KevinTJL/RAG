from __future__ import annotations

import base64
import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings
from app.profile_store import safe_user_id


SETTINGS_VERSION = 1
DEFAULT_BASE_URL = "https://api.openai.com/v1"


def default_user_settings() -> dict[str, Any]:
    return {
        "version": SETTINGS_VERSION,
        "top_k": max(1, min(8, int(settings.top_k or 4))),
        "deepseek_thinking_enabled": settings.deepseek_thinking_enabled,
        "deepseek_thinking": {
            "deepseek-v4-flash": settings.deepseek_thinking_enabled,
            "deepseek-v4-pro": settings.deepseek_thinking_enabled,
        },
        "search_scope": "all",
        "selected_files": [],
        "custom_openai": {
            "base_url": DEFAULT_BASE_URL,
            "model_name": "",
            "temperature": None,
            "top_p": None,
            "max_tokens": None,
            "timeout": None,
            "enabled_for_chat": False,
            "enabled_for_review": False,
            "has_api_key": False,
        },
    }


def _fernet() -> Fernet:
    digest = hashlib.sha256(settings.auth_secret.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(value: str) -> str:
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_secret(value: str) -> str:
    try:
        return _fernet().decrypt(value.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError):
        return ""


def public_settings(data: dict[str, Any]) -> dict[str, Any]:
    public = deepcopy(data)
    custom = public.setdefault("custom_openai", {})
    custom.pop("api_key_encrypted", None)
    custom.pop("api_key", None)
    custom["has_api_key"] = bool(data.get("custom_openai", {}).get("api_key_encrypted"))
    return public


class UserSettingsStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or settings.project_root / "db" / "user_settings"
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, user_id: str) -> Path:
        return self.root / f"{safe_user_id(user_id)}.json"

    def load_private(self, user_id: str) -> dict[str, Any]:
        data = default_user_settings()
        path = self.path_for(user_id)
        if path.exists():
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                loaded = {}
            if isinstance(loaded, dict):
                data.update({key: value for key, value in loaded.items() if key != "custom_openai"})
                custom = data.setdefault("custom_openai", {})
                custom.update(loaded.get("custom_openai", {}) if isinstance(loaded.get("custom_openai"), dict) else {})
        return self.normalize_private(data)

    def load_public(self, user_id: str) -> dict[str, Any]:
        return public_settings(self.load_private(user_id))

    def save(self, user_id: str, incoming: dict[str, Any]) -> dict[str, Any]:
        current = self.load_private(user_id)
        # Deep-merge deepseek_thinking and custom_openai instead of replacing
        merged = {**current, **incoming}
        if isinstance(incoming.get("deepseek_thinking"), dict):
            current_thinking = dict(current.get("deepseek_thinking", {}))
            current_thinking.update(incoming["deepseek_thinking"])
            merged["deepseek_thinking"] = current_thinking
        if isinstance(incoming.get("custom_openai"), dict):
            current_custom = dict(current.get("custom_openai", {}))
            current_custom.update(incoming["custom_openai"])
            merged["custom_openai"] = current_custom
        next_data = self.normalize_private(merged)

        incoming_custom = incoming.get("custom_openai", {}) if isinstance(incoming.get("custom_openai"), dict) else {}
        custom = next_data.setdefault("custom_openai", {})
        current_custom = current.get("custom_openai", {})

        incoming_api_key = incoming_custom.get("api_key")
        incoming_api_key = incoming_api_key.strip() if isinstance(incoming_api_key, str) else ""

        if incoming_custom.get("clear_api_key"):
            custom.pop("api_key_encrypted", None)
        elif incoming_api_key:
            custom["api_key_encrypted"] = encrypt_secret(incoming_api_key)
        elif current_custom.get("api_key_encrypted"):
            custom["api_key_encrypted"] = current_custom.get("api_key_encrypted")

        custom.pop("api_key", None)
        custom.pop("clear_api_key", None)
        path = self.path_for(user_id)
        path.write_text(json.dumps(next_data, ensure_ascii=False, indent=2), encoding="utf-8")
        path.chmod(0o600)
        return public_settings(next_data)

    def get_custom_api_key(self, user_id: str) -> str:
        encrypted = self.load_private(user_id).get("custom_openai", {}).get("api_key_encrypted", "")
        return decrypt_secret(str(encrypted or "")) if encrypted else ""

    def normalize_private(self, data: dict[str, Any]) -> dict[str, Any]:
        normalized = default_user_settings()
        normalized.update({key: value for key, value in data.items() if key != "custom_openai"})
        normalized["version"] = SETTINGS_VERSION
        try:
            normalized["top_k"] = max(1, min(8, int(normalized.get("top_k") or settings.top_k or 4)))
        except Exception:
            normalized["top_k"] = max(1, min(8, int(settings.top_k or 4)))
        if normalized.get("search_scope") not in {"all", "personal", "system"}:
            normalized["search_scope"] = "all"
        selected_files = normalized.get("selected_files")
        normalized["selected_files"] = selected_files if isinstance(selected_files, list) else []

        # Normalize per-model deepseek thinking toggles
        thinking_defaults = default_user_settings()["deepseek_thinking"]
        incoming_thinking = data.get("deepseek_thinking", {}) if isinstance(data.get("deepseek_thinking"), dict) else {}
        normalized["deepseek_thinking"] = {
            model: bool(incoming_thinking.get(model, thinking_defaults.get(model, settings.deepseek_thinking_enabled)))
            for model in thinking_defaults
        }
        # Preserve any extra model keys from incoming
        for model, enabled in incoming_thinking.items():
            if model not in normalized["deepseek_thinking"]:
                normalized["deepseek_thinking"][model] = bool(enabled)

        custom = normalized.setdefault("custom_openai", {})
        incoming_custom = data.get("custom_openai", {}) if isinstance(data.get("custom_openai"), dict) else {}
        custom.update(incoming_custom)
        custom["base_url"] = str(custom.get("base_url") or DEFAULT_BASE_URL).strip().rstrip("/")
        custom["model_name"] = str(custom.get("model_name") or "").strip()
        for key in ("temperature", "top_p"):
            custom[key] = _optional_float(custom.get(key))
        for key in ("max_tokens", "timeout"):
            custom[key] = _optional_int(custom.get(key))
        custom["enabled_for_chat"] = bool(custom.get("enabled_for_chat"))
        custom["enabled_for_review"] = bool(custom.get("enabled_for_review"))
        return normalized


def _optional_float(value: Any) -> float | None:
    if value in ("", None):
        return None
    try:
        return float(value)
    except Exception:
        return None


def _optional_int(value: Any) -> int | None:
    if value in ("", None):
        return None
    try:
        parsed = int(value)
    except Exception:
        return None
    return parsed if parsed > 0 else None
