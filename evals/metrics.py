"""Retrieval metrics. `ranked` is the list of page URLs of the returned chunks, best first.

A question can have more than one acceptable page (`gold`): any of them answers it.
"""
import math


def pages(ranked: list[str]) -> list[str]:
    """The ranking of pages: each page once, at the position of its best chunk."""
    return list(dict.fromkeys(ranked))


def recall_at_k(ranked: list[str], gold: set[str], k: int) -> float:
    """1 when an acceptable page is among the first k chunks, else 0."""
    return float(any(source in gold for source in ranked[:k]))


def reciprocal_rank(ranked: list[str], gold: set[str]) -> float:
    """1 / position of the first chunk from an acceptable page; 0 when there is none."""
    for position, source in enumerate(ranked, start=1):
        if source in gold:
            return 1 / position
    return 0.0


def ndcg_at_k(ranked: list[str], gold: set[str], k: int) -> float:
    """Normalised discounted cumulative gain over the page ranking: rewards acceptable pages near the top."""
    top = pages(ranked)[:k]
    gain = sum(1 / math.log2(position + 1) for position, source in enumerate(top, start=1) if source in gold)
    ideal = sum(1 / math.log2(position + 1) for position in range(1, min(len(gold), k) + 1))
    return gain / ideal if ideal else 0.0


def context_precision(ranked: list[str], gold: set[str], k: int) -> float:
    """Share of the first k chunks that come from an acceptable page: how much of the context is useful."""
    top = ranked[:k]
    return sum(source in gold for source in top) / len(top) if top else 0.0


def wilson(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """The 95% Wilson interval of a rate: the range the true rate plausibly lies in, given n trials."""
    if n == 0:
        return (0.0, 1.0)
    rate = successes / n
    denominator = 1 + z * z / n
    centre = (rate + z * z / (2 * n)) / denominator
    half = z * math.sqrt(rate * (1 - rate) / n + z * z / (4 * n * n)) / denominator
    return (max(0.0, centre - half), min(1.0, centre + half))
