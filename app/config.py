from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Load .env if present in the project root
PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    app_env: str = os.getenv("APP_ENV", "development")
    auth_secret: str = os.getenv("AUTH_SECRET", "dev-insecure-" + secrets.token_urlsafe(24))
    auth_token_ttl_hours: int = int(os.getenv("AUTH_TOKEN_TTL_HOURS", "168"))
    project_root: Path = Path(os.getenv("PROJECT_ROOT", str(PROJECT_ROOT)))
    data_dir: Path = Path(os.getenv("DATA_DIR", str(PROJECT_ROOT / "data" / "raw")))
    user_data_root: Path = Path(os.getenv("USER_DATA_ROOT", str(PROJECT_ROOT / "data" / "users")))
    chroma_path: Path = Path(os.getenv("CHROMA_PATH", str(PROJECT_ROOT / "db" / "chroma")))
    cors_origins: tuple[str, ...] = tuple(
        item.strip()
        for item in os.getenv("CORS_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173").split(",")
        if item.strip()
    )
    ollama_host: str = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    chat_model: str = os.getenv("CHAT_MODEL", "qwen2.5:3b")
    embed_model: str = os.getenv("EMBED_MODEL", "bge-m3")
    deepseek_api_key: str = os.getenv("DEEPSEEK_API_KEY", "")
    deepseek_base_url: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    deepseek_reasoning_effort: str = os.getenv("DEEPSEEK_REASONING_EFFORT", "high")
    deepseek_thinking_enabled: bool = os.getenv("DEEPSEEK_THINKING_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
    available_chat_models: tuple[str, ...] = tuple(
        item.strip()
        for item in os.getenv("AVAILABLE_CHAT_MODELS", "qwen2.5:3b,deepseek-v4-pro,deepseek-v4-flash").split(",")
        if item.strip()
    )
    collection_name: str = os.getenv("COLLECTION_NAME", "rag_demo")
    chunk_size: int = int(os.getenv("CHUNK_SIZE", "1600"))
    chunk_overlap: int = int(os.getenv("CHUNK_OVERLAP", "300"))
    top_k: int = int(os.getenv("TOP_K", "4"))
    temperature: float = float(os.getenv("TEMPERATURE", "0.2"))
    top_p: float = float(os.getenv("TOP_P", "0.9"))
    num_ctx: int = int(os.getenv("NUM_CTX", "4096"))


settings = Settings()
