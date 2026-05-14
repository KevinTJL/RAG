from __future__ import annotations

import argparse

from app.config import settings
from app.ollama_client import OllamaClient
from app.vector_store import get_collection


SYSTEM_PROMPT = """你是一个高度细致且有帮助的RAG教育助手。
根据提供的上下文进行回答，但需要对信息进行综合整理，提供全面、详细且深入的解释。
请对复杂推理进行拆解，并利用上下文中的所有可用信息提供充分的洞见。
如果有公式，请展示公式，并解释每个变量的含义。
如果上下文信息不足，请明确说明：本地知识库中没有足够的信息。
在可能的情况下，请简要提及来源文件名称以作为引用依据。
"""


def build_context(documents: list[str], metadatas: list[dict]) -> str:
    blocks = []
    for i, (doc, meta) in enumerate(zip(documents, metadatas), start=1):
        source = meta.get("source", "unknown")
        page = meta.get("page", -1)
        loc = f"page {page}" if isinstance(page, int) and page > 0 else "text"
        blocks.append(f"[Context {i} | {source} | {loc}]\n{doc}")
    return "\n\n".join(blocks)


def candidate_count(top_k: int) -> int:
    return max(top_k, top_k * 4)


def chunk_position(meta: dict) -> int | None:
    try:
        if meta.get("global_chunk_index") is not None:
            return int(meta.get("global_chunk_index"))
        chunk_index = meta.get("chunk_index")
        if chunk_index is None:
            return None
        page = int(meta.get("page", -1) or -1)
        chunk = int(chunk_index)
        if page > 0:
            return page * 100000 + chunk
        return chunk
    except Exception:
        return None


def is_near_duplicate(meta: dict, selected: list[dict], window: int = 3) -> bool:
    source = meta.get("source")
    position = chunk_position(meta)
    if not source or position is None:
        return False

    for selected_meta in selected:
        if selected_meta.get("source") != source:
            continue
        selected_position = chunk_position(selected_meta)
        if selected_position is not None and abs(position - selected_position) <= window:
            return True
    return False


def diverse_results(
    documents: list[str],
    metadatas: list[dict],
    distances: list[float],
    top_k: int,
    neighbor_window: int = 3,
    per_source_limit: int = 2,
) -> tuple[list[str], list[dict], list[float]]:
    candidates = list(zip(documents, metadatas, distances))
    selected: list[tuple[str, dict, float]] = []
    source_counts: dict[str, int] = {}

    for doc, meta, distance in candidates:
        source = str(meta.get("source", ""))
        if is_near_duplicate(meta, [item[1] for item in selected], neighbor_window):
            continue
        if source and source_counts.get(source, 0) >= per_source_limit:
            continue
        selected.append((doc, meta, distance))
        source_counts[source] = source_counts.get(source, 0) + 1
        if len(selected) == top_k:
            break

    if len(selected) < top_k:
        selected_ids = {id(meta) for _, meta, _ in selected}
        for doc, meta, distance in candidates:
            if id(meta) in selected_ids:
                continue
            selected.append((doc, meta, distance))
            if len(selected) == top_k:
                break

    docs = [item[0] for item in selected]
    metas = [item[1] for item in selected]
    dists = [item[2] for item in selected]
    return docs, metas, dists


def main() -> None:
    parser = argparse.ArgumentParser(description="Query the local RAG demo.")
    parser.add_argument("question", type=str, help="Question to ask the knowledge base")
    args = parser.parse_args()

    ollama = OllamaClient()
    ollama.healthcheck()
    collection = get_collection(reset=False)

    query_embedding = ollama.embed([args.question])[0]
    result = collection.query(
        query_embeddings=[query_embedding],
        n_results=candidate_count(settings.top_k),
        include=["documents", "metadatas", "distances"],
    )

    documents = (result.get("documents") or [[]])[0]
    metadatas = (result.get("metadatas") or [[]])[0]
    distances = (result.get("distances") or [[]])[0]
    documents, metadatas, distances = diverse_results(
        documents,
        metadatas,
        distances,
        top_k=settings.top_k,
        neighbor_window=3,
        per_source_limit=2,
    )

    if not documents:
        print("No relevant content found in the local knowledge base.")
        return

    context = build_context(documents, metadatas)
    user_prompt = f"Question:\n{args.question}\n\nContext:\n{context}"
    answer = ollama.chat(
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]
    )

    print("\n=== Answer ===\n")
    print(answer)
    print("\n=== Retrieved Chunks ===\n")
    for idx, (doc, meta, dist) in enumerate(zip(documents, metadatas, distances), start=1):
        source = meta.get("source", "unknown")
        page = meta.get("page", -1)
        where = f"page {page}" if isinstance(page, int) and page > 0 else "text"
        preview = doc[:220].replace("\n", " ")
        print(f"[{idx}] {source} | {where} | distance={dist:.4f}")
        print(f"    {preview}")


if __name__ == "__main__":
    main()
