import os
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

import pytest
from rag.chunker import chunk_text
from rag.embedder import _get_model, chunk_document


@pytest.mark.parametrize("text", [
    "English document data. " * 120 + "The final access code is INDIGO.",
    "这是中文资料。支持窗口是早九点到晚五点。" * 80 + "最后的代号是青竹。",
    "word, English中文🙂 & punctuation! " * 120,
    "a" * 2100,
])
def test_actual_model_budget_preserves_tail_and_content(text):
    model = _get_model()
    chunks = chunk_document(text)
    assert len(chunks) > 1
    assert all(len(model.tokenizer.encode(chunk, add_special_tokens=True, truncation=False)) <= model.max_seq_length
               for chunk in chunks)
    # Whitespace normalization is the existing contract; nonspace characters survive.
    assert "".join("".join(chunks).split()) == "".join(text.split())
    assert text.split()[-1] in chunks[-1] or text[-10:] in chunks[-1]


@pytest.mark.parametrize("size,overlap", [(0, 0), (10, 10), (10, -1)])
def test_invalid_chunk_parameters(size, overlap):
    with pytest.raises(ValueError):
        chunk_text("text", max_size=size, overlap=overlap)


def test_overlap_finishes_at_end_of_input():
    chunks = chunk_text("0123456789" * 3, max_size=10, overlap=2)
    assert len(chunks) == 4
    assert chunks[-1].endswith("89")
