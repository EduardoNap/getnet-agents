"""Why does retrieval miss a question? For each miss: where the right page really ranks.

    python -m evals.diagnose

A page outside the 40 candidates is an embedding problem (reranking cannot help). A page inside
them but below the top 6 is a ranking problem. Blind questions are never read here.
"""
import json
from pathlib import Path

from app.rag.retriever import CANDIDATES, embed, get_collection, search

HERE = Path(__file__).parent
K = 6


def rank_of_gold(sources: list[str], gold: set[str]) -> int | None:
    """1-based position of the first chunk from a gold page, or None."""
    return next((position for position, source in enumerate(sources, 1) if source in gold), None)


def diagnose(question: dict) -> dict:
    query, gold = question.get("pt", question["question"]), set(question["gold"])
    collection = get_collection()
    by_vector = collection.query(query_embeddings=embed([query]), n_results=collection.count())
    vector_rank = rank_of_gold([meta["source"] for meta in by_vector["metadatas"][0]], gold)
    hybrid_rank = rank_of_gold([hit["source"] for hit in search(query, k=CANDIDATES)], gold)
    if hybrid_rank and hybrid_rank <= K:
        cause = "found"
    elif vector_rank is None or vector_rank > CANDIDATES:
        cause = "not among the candidates (embedding)"
    else:
        cause = "among the candidates, ranked too low (ranking)"
    return {"id": question["id"], "question": query, "vector_rank": vector_rank, "hybrid_rank": hybrid_rank, "cause": cause}


if __name__ == "__main__":
    questions = [json.loads(line) for line in (HERE / "retrieval_set.jsonl").read_text(encoding="utf-8").splitlines()]
    rows = [diagnose(question) for question in questions if question["split"] != "blind"]
    for row in rows:
        if row["cause"] != "found":
            print(f"{row['id']:4} vector rank {row['vector_rank']!s:>4}  hybrid rank {row['hybrid_rank']!s:>4}  {row['cause']}: {row['question']}")
    print({cause: sum(row["cause"] == cause for row in rows) for cause in sorted({row["cause"] for row in rows})})
