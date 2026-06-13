import chromadb
from pathlib import Path

_client = None
_collection = None

def _col():
    global _client, _collection
    if _collection is None:
        Path("chroma_data").mkdir(exist_ok=True)
        _client = chromadb.PersistentClient(path="chroma_data")
        _collection = _client.get_or_create_collection("documents")
    return _collection

def add_document(chunks: list[str], embeddings: list[list[float]], filename: str) -> None:
    col = _col()
    delete_document(filename)
    col.add(
        documents=chunks,
        embeddings=embeddings,
        ids=[f"{filename}__chunk_{i}" for i in range(len(chunks))],
        metadatas=[{"source": filename, "chunk_index": i} for i in range(len(chunks))]
    )

def delete_document(filename: str) -> None:
    col = _col()
    try:
        existing = col.get(where={"source": {"$eq": filename}})
        if existing["ids"]:
            col.delete(ids=existing["ids"])
    except Exception:
        pass

def query(embedding: list[float], n_results: int = 4) -> list[dict]:
    col = _col()
    count = col.count()
    if count == 0:
        return []
    results = col.query(
        query_embeddings=[embedding],
        n_results=min(n_results, count),
        include=["documents", "metadatas"]
    )
    return [
        {"text": doc, "source": meta["source"]}
        for doc, meta in zip(results["documents"][0], results["metadatas"][0])
    ]

def list_documents() -> list[str]:
    col = _col()
    if col.count() == 0:
        return []
    result = col.get(include=["metadatas"])
    return sorted(set(m["source"] for m in result["metadatas"]))
