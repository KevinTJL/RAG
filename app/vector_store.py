from __future__ import annotations

from typing import Any

import chromadb

from app.config import settings
from app.profile_store import safe_user_id


def collection_name_for_user(user_id: str | None = None) -> str:
    if not user_id:
        return settings.collection_name
    return f"{settings.collection_name}_{safe_user_id(user_id)}"


def get_collection(reset: bool = False, user_id: str | None = None):
    settings.chroma_path.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(settings.chroma_path))
    collection_name = collection_name_for_user(user_id)

    if reset:
        try:
            client.delete_collection(collection_name)
        except Exception:
            pass

    collection = client.get_or_create_collection(name=collection_name)
    return collection


def get_user_memory_collection(user_id: str, reset: bool = False):
    """获取或创建一个隔离的用户长程记忆 Collection"""
    client = chromadb.PersistentClient(path=str(settings.chroma_path))
    col_name = f"user_memory_{safe_user_id(user_id)}"
    
    if reset:
        try:
            client.delete_collection(col_name)
        except Exception:
            pass

    collection = client.get_or_create_collection(name=col_name)
    return collection


def delete_user_memory_collection(user_id: str) -> None:
    client = chromadb.PersistentClient(path=str(settings.chroma_path))
    col_name = f"user_memory_{safe_user_id(user_id)}"
    try:
        client.delete_collection(col_name)
    except Exception:
        pass


def batched(items: list[Any], batch_size: int = 64):
    for i in range(0, len(items), batch_size):
        yield items[i : i + batch_size]
