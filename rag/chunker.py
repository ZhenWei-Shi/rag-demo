# EN: Sentence-boundary-aware text chunker.
#     Splits text at natural sentence boundaries instead of arbitrary character positions,
#     preserving semantic coherence within each chunk.
# ZH: 基于句子边界的文本分块器。
#     在自然句子边界处分割，而非任意字符位置，保证每个分块语义完整。


def chunk_text(text: str, max_size: int = 1000, overlap: int = 0) -> list[str]:
    """
    EN: Split `text` into chunks of at most `max_size` characters.
        Prefers splitting at sentence-ending punctuation to keep chunks coherent.
    ZH: 将文本切分为最多 `max_size` 字符的分块。
        优先在句末标点处分割，保持分块语义连贯。
    """
    # EN: Normalize whitespace to a single space.
    # ZH: 将多余空白符规范化为单个空格。
    text = " ".join(text.split())
    if not text:
        return []

    chunks = []
    start = 0
    while start < len(text):
        end = start + max_size
        if end < len(text):
            # EN: Scan backward from the split point for sentence-ending punctuation.
            # ZH: 从分割点向前扫描，寻找句末标点作为更自然的切分位置。
            for sep in [". ", "! ", "? ", "; ", " "]:
                pos = text.rfind(sep, start + overlap, end)
                if pos != -1:
                    end = pos + len(sep)
                    break
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = end - overlap
        if start >= len(text):
            break
    return chunks
