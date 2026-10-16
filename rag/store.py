"""Chroma retrieval with durable, copy-on-write document replacement.

Run one application worker per data directory (as in the systemd service).
"""
import logging
import os
from pathlib import Path
from threading import RLock
from uuid import uuid4

import chromadb
from rag.versioned_store import publish, visible

logger = logging.getLogger(__name__)
_client = None
_collection = None
_lock = RLock()


def _col():
    global _client, _collection
    with _lock:
        if _collection is None:
            directory = Path(os.getenv("RAG_DATA_DIR", "chroma_data"))
            directory.mkdir(parents=True, exist_ok=True)
            _client = chromadb.PersistentClient(path=str(directory))
            _collection = _client.get_or_create_collection("documents")
        return _collection


def add_document(chunks: list[str], embeddings: list[list[float]], filename: str) -> None:
    if not chunks or len(chunks) != len(embeddings):
        raise ValueError("A document must have matching nonempty chunks and embeddings")
    with _lock:
        col = _col()
        previous = col.get(where={"source": {"$eq": filename}})["ids"]
        revision = uuid4().hex
        ids = [f"{revision}_{i}" for i in range(len(chunks))]
        try:
            col.add(documents=chunks, embeddings=embeddings, ids=ids,
                    metadatas=[{"source": filename, "chunk_index": i, "revision": revision}
                               for i in range(len(chunks))])
            publish(col, filename, ids)
        except Exception:
            try:
                col.delete(ids=ids)
            except Exception:
                logger.warning("Could not clean staged document revision", exc_info=True)
            raise
        if previous:
            try:
                col.delete(ids=previous)
            except Exception:
                logger.warning("Old document revision cleanup deferred", exc_info=True)


def delete_document(filename: str) -> None:
    with _lock:
        col = _col()
        ids = col.get(where={"source": {"$eq": filename}})["ids"]
        if ids:
            col.delete(ids=ids)
        publish(col, filename, [])


def query(embedding: list[float], n_results: int = 6, *, question: str | None = None) -> list[dict]:
    with _lock:
        col = _col()
        ids = [identifier for identifier, _ in visible(col)]
        if not ids or n_results <= 0:
            return []
        pool = max(24, n_results * 4) if question else n_results
        results = col.query(query_embeddings=[embedding], ids=ids,
                            n_results=min(pool, len(ids)), include=["documents", "metadatas"])
        ranked = results["ids"][0]
        if question:
            from rag.hybrid import rank_candidates
            ranked = rank_candidates(col, ids, ranked, question, n_results)
        rows = col.get(ids=ranked, include=["documents", "metadatas"])
        by_id = {identifier: {"text": doc, "source": meta["source"]}
                 for identifier, doc, meta in zip(rows["ids"], rows["documents"], rows["metadatas"])}
        return [by_id[identifier] for identifier in ranked[:n_results]]


def list_documents() -> list[str]:
    with _lock:
        return sorted({meta["source"] for _, meta in visible(_col())})
