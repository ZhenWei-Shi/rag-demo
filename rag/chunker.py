# EN: Sentence-boundary-aware text chunker.
#     Splits text at natural sentence boundaries instead of arbitrary character positions,
#     preserving semantic coherence within each chunk.
# ZH: 基于句子边界的文本分块器。
#     在自然句子边界处分割，而非任意字符位置，优先保持语义连贯；超出预算的长句仍需拆分。


def chunk_text(text: str, max_size: int = 1000, overlap: int = 0, *, token_count=None, max_tokens=None) -> list[str]:
    """
    EN: Split `text` into chunks of at most `max_size` characters.
        Prefers splitting at sentence-ending punctuation to keep chunks coherent.
    ZH: 将文本切分为最多 `max_size` 字符的分块。
        优先在句末标点处分割，保持分块语义连贯。
    """
    if max_size <= 0 or not 0 <= overlap < max_size:
        raise ValueError("Require max_size > 0 and 0 <= overlap < max_size")
    if token_count is not None and (max_tokens is None or max_tokens < 1):
        raise ValueError("A positive token budget is required")
    # EN: Normalize whitespace to a single space.
    # ZH: 将多余空白符规范化为单个空格。
    text = " ".join(text.split())
    if not text:
        return []

    chunks = []
    start = 0
    while start < len(text):
        end = start + max_size
        end = min(end, len(text))
        if token_count is not None and token_count(text[start:end]) > max_tokens:
            low, high = start + 1, end
            while low < high:
                middle = (low + high + 1) // 2
                if token_count(text[start:middle]) <= max_tokens:
                    low = middle
                else:
                    high = middle - 1
            end = low
        if end < len(text):
            # EN: Scan backward from the split point for sentence-ending punctuation.
            # ZH: 从分割点向前扫描，寻找句末标点作为更自然的切分位置。
            for sep in [". ", "! ", "? ", "; ", " "]:
                pos = text.rfind(sep, start + overlap, end)
                if pos != -1:
                    end = pos + len(sep)
                    break
        if token_count is not None:
            while end > start and token_count(text[start:end].strip()) > max_tokens:
                end -= 1
            if end == start:
                raise ValueError("A character cannot fit within the token budget")
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = max(start + 1, end - overlap)
    return chunks
