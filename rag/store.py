# EN: ChromaDB vector store wrapper. Handles document indexing, deletion, and similarity search.
# ZH: ChromaDB 向量数据库封装。处理文档索引、删除和语义相似度检索。

import logging
import chromadb
from pathlib import Path

logger = logging.getLogger(__name__)

_client = None
_collection = None


def _col():
    # EN: Lazily initialize the ChromaDB persistent client and collection.
    # ZH: 懒加载 ChromaDB 持久化客户端和集合。
    global _client, _collection
    if _collection is None:
        Path("chroma_data").mkdir(exist_ok=True)
        _client = chromadb.PersistentClient(path="chroma_data")
        _collection = _client.get_or_create_collection("documents")
    return _collection


def add_document(chunks: list[str], embeddings: list[list[float]], filename: str) -> None:
    """
    EN: Index a document's chunks into ChromaDB. Automatically removes any previous
        version of the same filename before inserting to avoid duplicates.
    ZH: 将文档分块索引到 ChromaDB。插入前自动删除同名文档的旧版本，避免重复。
    """
    col = _col()
    # EN: Delete existing entries for this filename first (upsert-like behavior).
    # ZH: 先删除该文件名的旧条目，实现类似 upsert 的行为。
    delete_document(filename)
    col.add(
        documents=chunks,
        embeddings=embeddings,
        ids=[f"{filename}__chunk_{i}" for i in range(len(chunks))],
        metadatas=[{"source": filename, "chunk_index": i} for i in range(len(chunks))]
    )


def delete_document(filename: str) -> None:
    """
    EN: Remove all chunks belonging to `filename` from the vector store.
    ZH: 从向量数据库中删除属于 `filename` 的所有分块。
    """
    col = _col()
    try:
        existing = col.get(where={"source": {"$eq": filename}})
        if existing["ids"]:
            col.delete(ids=existing["ids"])
    except Exception as e:
        # EN: Log but don't raise — deletion failure shouldn't block an upload or re-index.
        # ZH: 记录日志但不抛出异常 —— 删除失败不应阻塞上传或重新索引流程。
        logger.warning("Failed to delete document '%s': %s", filename, e)


def query(embedding: list[float], n_results: int = 6) -> list[dict]:
    """
    EN: Retrieve the top-N most semantically similar chunks for a given query embedding.
    ZH: 检索与给定查询向量语义最相似的前 N 个分块。
    """
    col = _col()
    count = col.count()
    if count == 0:
        return []
    results = col.query(
        query_embeddings=[embedding],
        # EN: Clamp n_results to the actual document count to avoid ChromaDB errors.
        # ZH: 将 n_results 限制在实际文档数量内，避免 ChromaDB 报错。
        n_results=min(n_results, count),
        include=["documents", "metadatas"]
    )
    return [
        {"text": doc, "source": meta["source"]}
        for doc, meta in zip(results["documents"][0], results["metadatas"][0])
    ]


def list_documents() -> list[str]:
    """
    EN: Return a sorted, deduplicated list of all indexed document filenames.
    ZH: 返回所有已索引文档文件名的排序去重列表。
    """
    col = _col()
    if col.count() == 0:
        return []
    result = col.get(include=["metadatas"])
    return sorted(set(m["source"] for m in result["metadatas"]))
