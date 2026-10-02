"""Offline document-retrieval evaluation; does not call an LLM."""
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from app.store import connect, retrieve_fts, retrieve_overlap, seed_documents

ROOT = Path(__file__).resolve().parents[1]


def evaluate(cases: list[dict], docs: list[dict], retriever) -> dict:
    answerable = [case for case in cases if case["answerable"]]
    unanswerable = [case for case in cases if not case["answerable"]]
    ranks: list[int] = []
    hits = 0
    for case in answerable:
        got = retriever(case["question"])
        got_ids = [doc["id"] for doc in got]
        expected = set(case["expected_source_ids"])
        rank = next((i for i, source_id in enumerate(got_ids, 1) if source_id in expected), None)
        if rank:
            hits += 1
            ranks.append(rank)
    abstained = sum(not retriever(case["question"]) for case in unanswerable)
    return {
        "answerable_count": len(answerable),
        "unanswerable_count": len(unanswerable),
        "supporting_source_hit_at_3": round(hits / len(answerable), 4) if answerable else None,
        "supporting_source_mrr": round(sum(1 / rank for rank in ranks) / len(answerable), 4) if answerable else None,
        "unanswerable_no_match_rate": round(abstained / len(unanswerable), 4) if unanswerable else None,
        "retrieved_supporting_sources": hits,
        "retrieval_abstentions": abstained,
    }


def run() -> dict:
    docs = json.loads((ROOT / "data/sample_sources.json").read_text())
    cases = json.loads((ROOT / "evaluation/cases.json").read_text())
    with tempfile.TemporaryDirectory(prefix="notebook-eval-") as tmp:
        with connect(Path(tmp) / "eval.sqlite3") as conn:
            seed_documents(conn, docs)
            fts = evaluate(cases, docs, lambda q: retrieve_fts(conn, q, limit=3))
    overlap = evaluate(cases, docs, lambda q: retrieve_overlap(docs, q, limit=3))
    return {
        "title": "Synthetic handbook retrieval evaluation",
        "mode": "offline_retrieval_only",
        "dataset": {"cases": len(cases), "synthetic_sources": len(docs)},
        "metrics": {
            "sqlite_fts5": fts,
            "shared_word_overlap_baseline": overlap,
        },
        "interpretation": (
            "Supporting-source hit rate and MRR measure retrieval on this authored synthetic set. "
            "No model was called, so this report says nothing about generated-answer factuality, "
            "citation faithfulness, latency, or cost. Cases cover straightforward lexical questions; "
            "they do not evaluate conflicting sources, malicious source instructions, or prompt-injection resistance."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="optional path for JSON report")
    args = parser.parse_args()
    report = run()
    rendered = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)
    print(rendered, end="")


if __name__ == "__main__":
    main()
