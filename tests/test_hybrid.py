"""Ranking contracts and active-revision isolation, without downloading a model."""
import uuid
import chromadb
import pytest
from rag import store
from rag.hybrid import tokenize

V = [1.0, 0.0, 0.0]

@pytest.fixture
def collection(monkeypatch):
    col = chromadb.EphemeralClient().create_collection('hybrid_' + uuid.uuid4().hex)
    monkeypatch.setattr(store, '_collection', col)
    return col

def test_multilingual_identifiers():
    terms = tokenize('XR-71B 青杉实验室')
    assert 'xr' in terms and '71b' in terms and '青杉' in terms and '室' in terms

def test_empty_query_and_no_term_match_keep_dense_order(collection):
    store.add_document(['first', 'second'], [V, [0.9,0.1,0.0]], 'a.txt')
    dense = store.query(V)
    assert store.query(V, question='!!!') == dense
    assert store.query(V, question='absentword') == dense
    assert store.query(V, n_results=0, question='first') == []

def test_lexical_candidates_can_enter_outside_dense_pool(collection):
    for i in range(27):
        store.add_document([f'generic note {i}'], [V], f'{i}.txt')
    store.add_document(['special identifier CERULEAN 713'], [[0.0,1.0,0.0]], 'target.txt')
    assert 'target.txt' not in [r['source'] for r in store.query(V)]
    assert 'target.txt' in [r['source'] for r in store.query(V, question='CERULEAN 713')]

def test_only_active_revision_is_lexically_searchable(collection, monkeypatch):
    store.add_document(['old SECRETWORD'], [V], 'a.txt')
    original_delete = collection.delete
    monkeypatch.setattr(collection, 'delete', lambda **kw: None)
    store.add_document(['new content'], [V], 'a.txt')
    collection.add(ids=['staged'], documents=['SECRETWORD uncommitted'], embeddings=[V],
                   metadatas=[{'source':'b.txt','revision':'not-published'}])
    results = store.query(V, question='SECRETWORD')
    assert [r['text'] for r in results] == ['new content']
    monkeypatch.setattr(collection, 'delete', original_delete)
    store.delete_document('a.txt')
    assert store.query(V, question='SECRETWORD') == []

def test_chinese_only_collection(collection):
    store.add_document(['青杉预约提前三天', '赤松周五关闭'], [V,[0.5,0.5,0.0]], 'cn.md')
    result = store.query(V, n_results=1, question='青杉预约')
    assert result[0]['text'] == '青杉预约提前三天'
