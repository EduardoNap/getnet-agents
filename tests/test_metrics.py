"""Retrieval metrics on rankings small enough to compute by hand."""
import math

import pytest

from evals import metrics

GOLD = {"a"}


def test_gold_first():
    ranked = ["a", "a", "b", "c"]
    assert metrics.recall_at_k(ranked, GOLD, 1) == 1
    assert metrics.reciprocal_rank(ranked, GOLD) == 1
    assert metrics.ndcg_at_k(ranked, GOLD, 3) == 1
    assert metrics.context_precision(ranked, GOLD, 4) == 0.5


def test_gold_third():
    ranked = ["b", "c", "a", "d"]
    assert metrics.recall_at_k(ranked, GOLD, 1) == 0
    assert metrics.recall_at_k(ranked, GOLD, 3) == 1
    assert metrics.reciprocal_rank(ranked, GOLD) == pytest.approx(1 / 3)
    assert metrics.ndcg_at_k(ranked, GOLD, 3) == pytest.approx(1 / math.log2(4))
    assert metrics.context_precision(ranked, GOLD, 4) == 0.25


def test_gold_absent():
    ranked = ["b", "c", "d"]
    assert metrics.recall_at_k(ranked, GOLD, 3) == 0
    assert metrics.reciprocal_rank(ranked, GOLD) == 0
    assert metrics.ndcg_at_k(ranked, GOLD, 3) == 0
    assert metrics.context_precision(ranked, GOLD, 3) == 0


def test_two_acceptable_pages():
    gold = {"a", "b"}
    assert metrics.recall_at_k(["c", "b"], gold, 2) == 1  # either page is enough
    assert metrics.ndcg_at_k(["a", "b", "c"], gold, 3) == 1
    # Only one of the two found, at the top: 1 / (1 + 1/log2(3)).
    assert metrics.ndcg_at_k(["a", "c", "d"], gold, 3) == pytest.approx(1 / (1 + 1 / math.log2(3)))


def test_chunks_of_the_same_page_count_once_in_the_page_ranking():
    assert metrics.pages(["a", "a", "b", "a", "c"]) == ["a", "b", "c"]
    assert metrics.ndcg_at_k(["b", "b", "b", "a"], GOLD, 2) == pytest.approx(1 / math.log2(3))


def test_empty_ranking():
    assert metrics.context_precision([], GOLD, 6) == 0
    assert metrics.reciprocal_rank([], GOLD) == 0
