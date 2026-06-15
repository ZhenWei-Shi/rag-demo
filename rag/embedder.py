# EN: Embedding model singleton. Loads `all-MiniLM-L6-v2` once and reuses it for all requests.
# ZH: 嵌入模型单例。`all-MiniLM-L6-v2` 只加载一次，所有请求复用同一实例。

from sentence_transformers import SentenceTransformer

_model: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
    # EN: Lazy-load the model on first call; subsequent calls return the cached instance.
    # ZH: 首次调用时懒加载模型，后续调用直接返回缓存实例。
    global _model
    if _model is None:
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model


def warmup() -> None:
    # EN: Pre-load the model at server startup to avoid cold-start latency on the first request.
    # ZH: 在服务启动时预热模型，避免第一次请求的冷启动延迟。
    _get_model().encode(["warmup"], batch_size=1)


def embed(texts: list[str]) -> list[list[float]]:
    # EN: Encode a list of strings into dense vector embeddings.
    # ZH: 将字符串列表编码为稠密向量嵌入。
    return _get_model().encode(texts, batch_size=64).tolist()
