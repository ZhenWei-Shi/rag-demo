"""Offline reindex from complete stored chunk text; retain the full data backup."""
from rag import store
from rag.embedder import chunk_document, embed
from rag.versioned_store import visible


def main():
    collection = store._col()
    visible_records = visible(collection)
    names = sorted({meta['source'] for _, meta in visible_records})
    total_before, total_after = len(visible_records), 0
    for name in names:
        ids = [identifier for identifier, meta in visible_records if meta['source'] == name]
        records = collection.get(ids=ids, include=['documents', 'metadatas'])
        ordered = sorted(zip(records['documents'], records['metadatas']), key=lambda item: item[1]['chunk_index'])
        text = ' '.join(document for document, _ in ordered)
        chunks = chunk_document(text)
        assert ''.join(''.join(chunks).split()) == ''.join(text.split()), 'Reindex content mismatch'
        store.add_document(chunks, embed(chunks), name)
        total_after += len(chunks)
    assert store.list_documents() == names
    print({'documents': len(names), 'chunks_before': total_before, 'chunks_after': total_after, 'content_preserved': True}, flush=True)


if __name__ == '__main__':
    main()
