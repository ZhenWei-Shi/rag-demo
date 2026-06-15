import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from rag.chunker import chunk_text


def test_empty_string():
    assert chunk_text("") == []


def test_whitespace_only():
    assert chunk_text("   \n\t  ") == []


def test_short_text_single_chunk():
    assert chunk_text("Hello world.", max_size=1000) == ["Hello world."]


def test_normalizes_whitespace():
    assert chunk_text("  hello   world  ", max_size=1000) == ["hello world"]


def test_splits_at_sentence_boundary():
    # Text has a clear ". " boundary near the 1000-char mark
    text = ("A" * 600) + ". " + ("B" * 600)
    chunks = chunk_text(text, max_size=1000)
    assert len(chunks) == 2
    assert all(len(c) <= 1000 for c in chunks)
    assert chunks[0].endswith(".")
    assert chunks[1].startswith("B")


def test_splits_at_space_when_no_sentence_boundary():
    # No punctuation — falls back to splitting at a space
    text = ("word " * 300).strip()
    chunks = chunk_text(text, max_size=100)
    assert len(chunks) > 1
    assert all(len(c) <= 100 for c in chunks)


def test_chunks_cover_all_content():
    text = "The quick brown fox. Jumped over the lazy dog. And ran away fast."
    chunks = chunk_text(text, max_size=40)
    joined = " ".join(chunks)
    for word in ["quick", "brown", "fox", "Jumped", "lazy", "dog", "fast"]:
        assert word in joined


def test_no_empty_chunks():
    text = "Hello. World. Foo. Bar."
    chunks = chunk_text(text, max_size=10)
    assert all(c.strip() for c in chunks)


def test_long_word_split_at_max_size():
    # When a token has no split boundary, the chunker hard-cuts at max_size
    long_word = "A" * 2000
    chunks = chunk_text(long_word, max_size=1000)
    assert len(chunks) == 2
    assert all(len(c) <= 1000 for c in chunks)
    assert "".join(chunks) == long_word
