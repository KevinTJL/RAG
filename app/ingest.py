from __future__ import annotations

import hashlib
from pathlib import Path

from app.config import settings
from app.loaders import iter_supported_files, load_pdf_file, load_text_file
from app.ollama_client import OllamaClient
from app.text_utils import clean_text, split_text
from app.vector_store import batched, get_collection
from app.graph_store import GraphStore
from app.graph_extractor import extract_triplets


def make_chunk_id(file_path: Path, page: int | None, chunk_index: int, text: str) -> str:
    base = f"{file_path.as_posix()}::{page}::{chunk_index}::{text[:50]}"
    return hashlib.md5(base.encode("utf-8")).hexdigest()


def build_records(file_path: Path) -> list[dict]:
    records: list[dict] = []
    suffix = file_path.suffix.lower()

    if suffix in {".txt", ".md"}:
        text = clean_text(load_text_file(file_path))
        chunks = split_text(text, settings.chunk_size, settings.chunk_overlap)
        for idx, chunk in enumerate(chunks):
            records.append(
                {
                    "id": make_chunk_id(file_path, None, idx, chunk),
                    "document": chunk,
                    "metadata": {
                        "source": file_path.name,
                        "file_path": str(file_path),
                        "page": -1,
                        "chunk_index": idx,
                        "global_chunk_index": idx,
                        "doc_type": suffix.lstrip("."),
                    },
                }
            )
        return records

    if suffix == ".pdf":
        pages = load_pdf_file(file_path)
        global_idx = 0
        for page_num, page_text in pages:
            page_text = clean_text(page_text)
            if not page_text:
                continue
            chunks = split_text(page_text, settings.chunk_size, settings.chunk_overlap)
            for idx, chunk in enumerate(chunks):
                records.append(
                    {
                        "id": make_chunk_id(file_path, page_num, idx, chunk),
                        "document": chunk,
                        "metadata": {
                            "source": file_path.name,
                            "file_path": str(file_path),
                            "page": page_num,
                            "chunk_index": idx,
                            "global_chunk_index": global_idx,
                            "doc_type": "pdf",
                        },
                    }
                )
                global_idx += 1
        return records

    return records


def delete_file_records(filename: str, user_id: str | None = None) -> int | None:
    collection = get_collection(reset=False, user_id=user_id)
    try:
        existing = collection.get(where={"source": filename}, include=[])
        ids = existing.get("ids", [])
        if ids:
            collection.delete(ids=ids)
        return len(ids)
    except Exception:
        try:
            collection.delete(where={"source": filename})
        except Exception:
            return None
        return None


def index_file(file_path: Path, ollama: OllamaClient | None = None, user_id: str | None = None) -> int:
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    records = build_records(file_path)
    collection = get_collection(reset=False, user_id=user_id)
    delete_file_records(file_path.name, user_id=user_id)

    if not records:
        return 0

    client = ollama or OllamaClient()
    client.healthcheck()

    batch_size = 32
    total = len(records)
    for start in range(0, total, batch_size):
        batch = records[start : start + batch_size]
        docs_batch = [r["document"] for r in batch]
        ids_batch = [r["id"] for r in batch]
        metas_batch = [r["metadata"] for r in batch]
        embeddings = client.embed(docs_batch)
        collection.add(
            ids=ids_batch,
            documents=docs_batch,
            metadatas=metas_batch,
            embeddings=embeddings,
        )

    return total


def main(data_dir: Path | None = None, user_id: str | None = None) -> None:
    source_dir = data_dir or settings.data_dir
    if not source_dir.exists():
        raise FileNotFoundError(f"Data directory not found: {source_dir}")

    files = list(iter_supported_files(source_dir))
    if not files:
        print(f"No supported files found in {source_dir}")
        return

    ollama = OllamaClient()
    ollama.healthcheck()

    print(f"Found {len(files)} file(s). Building index...")
    collection = get_collection(reset=True, user_id=user_id)

    all_records: list[dict] = []
    for file_path in files:
        records = build_records(file_path)
        all_records.extend(records)
        print(f"- {file_path.name}: {len(records)} chunk(s)")

    if not all_records:
        print("No valid text content extracted.")
        return

    # print(f"Extracting knowledge graph triplets from {len(all_records)} chunks (This may take a while)...")
    # graph_store = GraphStore()
    # graph_store.clear()
    # for i, r in enumerate(all_records, 1):
    #     triplets = extract_triplets(r["document"])
    #     for t in triplets:
    #         if isinstance(t, dict) and "h" in t and "r" in t and "t" in t:
    #             graph_store.add_triplet(t["h"], t["r"], t["t"], source=r["metadata"]["source"])
    #     print(f"  Graph extraction: {i}/{len(all_records)} chunks processed (found {len(triplets)} triplets)")
    # graph_store.save()
    # print(f"Graph data saved into db/graph.json with {len(graph_store.graph.nodes)} nodes and {len(graph_store.graph.edges)} edges.")

    documents = [r["document"] for r in all_records]
    ids = [r["id"] for r in all_records]
    metadatas = [r["metadata"] for r in all_records]

    batch_size = 32
    total = len(all_records)
    for start in range(0, total, batch_size):
        end = min(total, start + batch_size)
        docs_batch = documents[start:end]
        ids_batch = ids[start:end]
        metas_batch = metadatas[start:end]
        embeddings = ollama.embed(docs_batch)
        collection.add(
            ids=ids_batch,
            documents=docs_batch,
            metadatas=metas_batch,
            embeddings=embeddings,
        )
        print(f"  Indexed {end}/{total} chunks")

    print("\nDone.")
    print(f"Collection: {settings.collection_name}")
    print(f"Chroma path: {settings.chroma_path}")


if __name__ == "__main__":
    main()
