from sentence_transformers import SentenceTransformer

_model: SentenceTransformer | None = None

def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model

def warmup() -> None:
    _get_model().encode(["warmup"], batch_size=1)

def embed(texts: list[str]) -> list[list[float]]:
    return _get_model().encode(texts, batch_size=64).tolist()
