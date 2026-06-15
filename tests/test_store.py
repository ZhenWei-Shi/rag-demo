import sys
import uuid
from pathlib import Path
import pytest
import chromadb

sys.path.insert(0, str(Path(__file__).parent.parent))
import rag.store as store_module

# Dimension of all-MiniLM-L6-v2 embeddings
DIM = 384
EMBED = [0.1] * DIM


@pytest.fixture(autouse=True)
def in_memory_store(monkeypatch):
    """Replace the persistent ChromaDB collection with an ephemeral in-memory one.
    Uses a unique collection name per test because EphemeralClient shares state
    within the same process in newer ChromaDB versions.
    """
    client = chromadb.EphemeralClient()
    col = client.create_collection(f"test_{uuid.uuid4().hex}")
    monkeypatch.setattr(store_module, "_client", client)
    monkeypatch.setattr(store_module, "_collection", col)
    yield col


# ── list_documents ─────────────────────────────────────────────────────────

def test_list_empty_store():
    assert store_module.list_documents() == []


def test_list_after_add():
    store_module.add_document(["chunk"], [EMBED], "a.txt")
    assert store_module.list_documents() == ["a.txt"]


def test_list_is_sorted_and_deduplicated():
    store_module.add_document(["x"], [EMBED], "z.txt")
    store_module.add_document(["y"], [EMBED], "a.txt")
    assert store_module.list_documents() == ["a.txt", "z.txt"]


def test_list_multiple_chunks_same_file():
    store_module.add_document(["c1", "c2", "c3"], [EMBED, EMBED, EMBED], "doc.txt")
    assert store_module.list_documents() == ["doc.txt"]


# ── add_document / upsert ──────────────────────────────────────────────────

def test_add_replaces_existing_chunks():
    store_module.add_document(["old content"], [EMBED], "a.txt")
    store_module.add_document(["new content"], [EMBED], "a.txt")
    assert store_module.list_documents() == ["a.txt"]
    results = store_module.query(EMBED, n_results=10)
    texts = [r["text"] for r in results]
    assert "new content" in texts
    assert "old content" not in texts


# ── delete_document ────────────────────────────────────────────────────────

def test_delete_removes_document():
    store_module.add_document(["hello"], [EMBED], "b.txt")
    store_module.delete_document("b.txt")
    assert store_module.list_documents() == []


def test_delete_nonexistent_does_not_raise():
    store_module.delete_document("ghost.txt")  # must not raise


def test_delete_only_removes_target():
    store_module.add_document(["aaa"], [EMBED], "keep.txt")
    store_module.add_document(["bbb"], [EMBED], "remove.txt")
    store_module.delete_document("remove.txt")
    assert store_module.list_documents() == ["keep.txt"]


# ── query ──────────────────────────────────────────────────────────────────

def test_query_empty_store():
    assert store_module.query(EMBED) == []


def test_query_returns_source_and_text():
    store_module.add_document(["relevant text"], [EMBED], "doc.txt")
    results = store_module.query(EMBED)
    assert len(results) == 1
    assert results[0]["source"] == "doc.txt"
    assert results[0]["text"] == "relevant text"


def test_query_clamps_n_results_to_available():
    store_module.add_document(["a", "b"], [EMBED, EMBED], "c.txt")
    # Request far more than what's stored — must not raise
    results = store_module.query(EMBED, n_results=100)
    assert len(results) == 2
