"""Storage and retrieval. A local Chroma collection, searched by meaning and by keywords.

Two rankings of every chunk are made and then fused:
- by meaning: cosine similarity of multilingual embeddings (finds paraphrases, and Portuguese pages
  for English questions);
- by keywords: BM25 over the chunk and its page title (finds exact words, product names and error
  codes, which the small embedding model often misses).
evals/diagnose.py showed why both are needed, and evals/retrieval.py measures each one alone.
"""
import math
import re
import unicodedata
from collections import Counter, defaultdict
from functools import lru_cache

import chromadb
from fastembed import TextEmbedding

from app.config import settings

COLLECTION = "getnet_kb"
CANDIDATES = 40  # how deep the evaluation looks; the agent receives the top 6
# Weights of the two rankings in the fusion, chosen on the development questions of evals/retrieval_set.jsonl
# and confirmed on its blind split. Keywords count double: on this corpus they are the stronger signal.
VECTOR_WEIGHT = 0.5
KEYWORD_WEIGHT = 1.0
TITLE_REPEATS = 3  # a word in the page title counts as much as three in the chunk
RRF_K = 60  # the usual constant of reciprocal rank fusion: flattens the gap between neighbouring ranks
BM25_K1, BM25_B = 1.5, 0.75


@lru_cache
def _embedder() -> TextEmbedding:
    # Multilingual 
    return TextEmbedding(model_name=settings.embedding_model)


def embed(texts: list[str]) -> list[list[float]]:
    return [vector.tolist() for vector in _embedder().embed(texts)]


@lru_cache
def _client() -> chromadb.ClientAPI:
    return chromadb.PersistentClient(path=str(settings.chroma_dir))


def get_collection(reset: bool = False) -> chromadb.Collection:
    client = _client()
    if reset and COLLECTION in [c.name for c in client.list_collections()]:
        client.delete_collection(COLLECTION)
    return client.get_or_create_collection(COLLECTION, configuration={"hnsw": {"space": "cosine"}})


STEM_LENGTH = 6  # "antecipar" and "antecipação" both become "anteci": a crude stemmer that needs no dictionary


def tokens(text: str) -> list[str]:
    """Lower-case word stems without accents. "Wi-Fi" and "1-19" are also kept joined, as people type them."""
    text = "".join(c for c in unicodedata.normalize("NFKD", text.lower()) if not unicodedata.combining(c))
    words = re.findall(r"[a-z0-9]+", text) + [a + b for a, b in re.findall(r"([a-z0-9]+)-([a-z0-9]+)", text)]
    return [word[:STEM_LENGTH] for word in words if len(word) > 1]


def fuse(rankings: list[list], weights: list[float]) -> list:
    """Reciprocal rank fusion: an item scores weight / (60 + rank) in each ranking it appears in."""
    scores: dict = defaultdict(float)
    for ranking, weight in zip(rankings, weights):
        if weight:
            for rank, item in enumerate(ranking, 1):
                scores[item] += weight / (RRF_K + rank)
    return sorted(scores, key=scores.get, reverse=True)


@lru_cache
def _keyword_index() -> dict:
    """Every chunk and its word counts, read once from the collection. Cleared when the index is rebuilt."""
    collection = get_collection()
    if collection.count() == 0:
        from app.rag.ingest import build_index

        build_index()
        collection = get_collection()
    stored = collection.get(include=["documents", "metadatas"])
    counts = [Counter(tokens(text) + tokens(meta["title"]) * TITLE_REPEATS) for text, meta in zip(stored["documents"], stored["metadatas"])]
    lengths = [sum(count.values()) for count in counts]
    chunks_with = Counter(word for count in counts for word in count)
    return {
        "ids": stored["ids"],
        "chunks": dict(zip(stored["ids"], zip(stored["documents"], stored["metadatas"]))),
        "counts": counts,
        "lengths": lengths,
        "average_length": sum(lengths) / len(lengths),
        "chunks_with": chunks_with,
    }


def _by_keywords(query: str) -> list[str]:
    """Chunk ids ranked by BM25. Chunks sharing no word with the query are left out."""
    index, total = _keyword_index(), len(_keyword_index()["ids"])
    scored = []
    for chunk_id, count, length in zip(index["ids"], index["counts"], index["lengths"]):
        score = 0.0
        for word in set(tokens(query)):
            frequency = count.get(word, 0)
            if frequency:
                rarity = math.log(1 + (total - index["chunks_with"][word] + 0.5) / (index["chunks_with"][word] + 0.5))
                score += rarity * frequency * (BM25_K1 + 1) / (
                    frequency + BM25_K1 * (1 - BM25_B + BM25_B * length / index["average_length"])
                )
        if score:
            scored.append((score, chunk_id))
    return [chunk_id for _score, chunk_id in sorted(scored, reverse=True)]


def _by_meaning(query: str) -> list[str]:
    index = _keyword_index()
    return get_collection().query(query_embeddings=embed([query]), n_results=len(index["ids"]))["ids"][0]


def search(query: str, k: int = 6, keyword_weight: float = KEYWORD_WEIGHT, vector_weight: float = VECTOR_WEIGHT) -> list[dict]:
    """Hybrid search: the k best chunks for the query, each with its source URL.

    The whole index (a few hundred chunks) is ranked twice, by meaning and by keywords, and the
    two rankings are fused. A weight of 0 leaves that ranking out, which is how the evaluation
    measures each one alone.
    """
    chunks = _keyword_index()["chunks"]
    rankings = [_by_meaning(query) if vector_weight else [], _by_keywords(query) if keyword_weight else []]
    ranked = fuse(rankings, [vector_weight, keyword_weight])[:k]
    return [
        {"text": chunks[chunk_id][0], "source": chunks[chunk_id][1]["source"], "title": chunks[chunk_id][1]["title"], "rank": position}
        for position, chunk_id in enumerate(ranked, 1)
    ]
