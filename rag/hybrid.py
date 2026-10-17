"""Small-corpus BM25L + reciprocal rank fusion + MMR (no extra model).

BM25 implementation: https://github.com/dorianbrown/rank_bm25 (Apache-2.0).
MMR: Carbonell & Goldstein, SIGIR 1998, doi:10.1145/290941.291025.
"""
import re
import numpy as np
from rank_bm25 import BM25L

_STOP = set("a an the is are was were be to of in on at for and or with what when where which who why how do does did can may it its i we you".split())


def tokenize(text: str) -> list[str]:
    # Latin identifiers and CJK unigrams/bigrams; same preprocessing on both sides.
    terms = re.findall(r"[a-z0-9]+|[\u3400-\u9fff]+", text.casefold())
    result = []
    for term in terms:
        if "\u3400" <= term[0] <= "\u9fff":
            result.extend(term)
            result.extend(term[i:i+2] for i in range(len(term)-1))
        else:
            if term not in _STOP:
                result.append(term)
    return result


def rank_candidates(col, active_ids, dense_ids, question, limit):
    records = col.get(ids=active_ids, include=["documents"])
    corpus = [tokenize(text) for text in records["documents"]]
    terms = tokenize(question)
    if not terms or not any(corpus):
        return dense_ids[:limit]
    scores = BM25L(corpus).get_scores(terms)
    lexical = sorted(range(len(scores)), key=lambda i: (-scores[i], records["ids"][i]))
    lexical_ids = [records["ids"][i] for i in lexical if scores[i] > 0][:len(dense_ids)]
    if not lexical_ids:
        return dense_ids[:limit]
    candidates = list(dict.fromkeys(dense_ids + lexical_ids))
    relevance = dict.fromkeys(candidates, 0.0)
    for ranking in (dense_ids, lexical_ids):
        for rank, identifier in enumerate(ranking, 1):
            relevance[identifier] += 1.0 / (60 + rank)
    peak = max(relevance.values())
    rows = col.get(ids=candidates, include=["embeddings"])
    vectors = np.asarray(rows["embeddings"], dtype=float)
    vectors /= np.maximum(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-12)
    by_id = dict(zip(rows["ids"], vectors))
    selected = []
    while candidates and len(selected) < limit:
        def marginal(identifier):
            redundancy = max((max(0.0, float(by_id[identifier] @ by_id[old]))
                              for old in selected), default=0.0)
            return 0.65 * relevance[identifier] / peak - 0.35 * redundancy
        best = max(candidates, key=marginal)
        selected.append(best)
        candidates.remove(best)
    return selected
