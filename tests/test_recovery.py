import uuid
import json
import os
import subprocess
import sys
from pathlib import Path

import chromadb
import pytest
import rag.store as store
from rag.versioned_store import publish, selected

VECTOR = [0.1] * 384


@pytest.fixture
def collection(monkeypatch):
    collection = chromadb.EphemeralClient().create_collection("recovery_" + uuid.uuid4().hex)
    monkeypatch.setattr(store, "_collection", collection)
    return collection


def texts():
    return [record["text"] for record in store.query(VECTOR)]


def test_failed_manifest_commit_preserves_old_document(collection, monkeypatch):
    store.add_document(["old"], [VECTOR], "a.txt")
    def fail(*args):
        raise OSError("manifest unavailable")
    monkeypatch.setattr(store, "publish", fail)
    with pytest.raises(OSError):
        store.add_document(["new"], [VECTOR], "a.txt")
    assert texts() == ["old"]


def test_partial_add_and_failed_cleanup_are_invisible(collection, monkeypatch):
    store.add_document(["old"], [VECTOR], "a.txt")
    original_add = collection.add
    def partial(**kwargs):
        original_add(**kwargs)
        raise OSError("partial write")
    def no_cleanup(**kwargs):
        raise OSError("cleanup failed")
    monkeypatch.setattr(collection, "add", partial)
    monkeypatch.setattr(collection, "delete", no_cleanup)
    with pytest.raises(OSError):
        store.add_document(["uncommitted"], [VECTOR], "a.txt")
    assert texts() == ["old"]


def test_post_commit_cleanup_failure_does_not_expose_old_chunks(collection, monkeypatch):
    store.add_document(["old"], [VECTOR], "a.txt")
    def fail(**kwargs):
        raise OSError("cleanup failed")
    monkeypatch.setattr(collection, "delete", fail)
    store.add_document(["new"], [VECTOR], "a.txt")
    assert collection.count() == 2
    assert texts() == ["new"]


def test_legacy_data_and_crash_staging_survive_reload(collection):
    collection.add(ids=["legacy"], documents=["legacy content"], embeddings=[VECTOR], metadatas=[{"source": "a.txt"}])
    collection.add(ids=["orphan"], documents=["uncommitted"], embeddings=[VECTOR], metadatas=[{"source": "a.txt", "revision": "staged"}])
    assert texts() == ["legacy content"]
    publish(collection, "a.txt", ["orphan"])
    assert selected(collection)["a.txt"] == {"orphan"}
    assert texts() == ["uncommitted"]


def test_delete_write_failure_is_reported_and_preserves_document(collection, monkeypatch):
    store.add_document(["keep"], [VECTOR], "a.txt")
    def fail(**kwargs):
        raise OSError("write failed")
    monkeypatch.setattr(collection, "delete", fail)
    with pytest.raises(OSError):
        store.delete_document("a.txt")
    assert texts() == ["keep"]


def test_process_restart_ignores_uncommitted_revision():
    root = Path(__file__).resolve().parents[1]
    def run(code):
        return subprocess.run([sys.executable, "-c", code], cwd=root, env=os.environ.copy(),
                              text=True, encoding="utf8", capture_output=True, check=True).stdout.strip()
    run("from rag import store; import os; v=[0.1]*384; store.add_document(['old'],[v],'a.txt'); "
        "store._col().add(ids=['staged'],documents=['new'],embeddings=[v],metadatas=[{'source':'a.txt','revision':'crash'}]); os._exit(0)")
    result = run("from rag import store; import json; print(json.dumps(store.query([0.1]*384)))")
    assert [item['text'] for item in json.loads(result)] == ['old']
    run("from rag.store import _col; from rag.versioned_store import publish; publish(_col(),'a.txt',['staged'])")
    result = run("from rag import store; import json; print(json.dumps(store.query([0.1]*384)))")
    assert [item['text'] for item in json.loads(result)] == ['new']
