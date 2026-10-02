"""Opt-in evaluation against a configured OpenAI-compatible model endpoint."""
from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from openai import OpenAI

from app.generation import has_expected_phrase, request_answer, validate_answer
from app.prompts import SYSTEM_PROMPT
from app.settings import Settings
from app.store import citations_for, connect, retrieve_fts, seed_documents

ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = ROOT / "data" / "sample_sources.json"
CASES_PATH = ROOT / "evaluation" / "cases.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _status(finish_reason: str, answer: str) -> str:
    if finish_reason == "length":
        return "truncated"
    if finish_reason == "content_filter":
        return "filtered"
    if finish_reason == "tool_calls":
        return "unsupported_finish_reason"
    if finish_reason == "empty_choices":
        return "empty_choices"
    if not answer:
        return "empty_answer"
    if finish_reason != "stop":
        return "unsupported_finish_reason"
    return "completed"


def run_live(limit: int | None = None) -> dict:
    run_started_at = datetime.now(timezone.utc).isoformat()
    cfg = Settings.from_env()
    cases = json.loads(CASES_PATH.read_text())
    if limit is not None:
        if limit < 1:
            raise ValueError("limit must be at least 1")
        cases = cases[:limit]
    documents = json.loads(SOURCE_PATH.read_text())
    outcomes: list[dict] = []
    client = None

    # Evaluations must never read from or mutate the application's configured
    # database; use a disposable index populated only with synthetic sources.
    with tempfile.TemporaryDirectory(prefix="notebook-live-eval-") as temp_dir:
        with connect(Path(temp_dir) / "evaluation.sqlite3") as conn:
            seed_documents(conn, documents)
            for case in cases:
                started = time.perf_counter()
                retrieved = []
                citations: list[dict] = []
                answer = ""
                usage = {"prompt_tokens": None, "completion_tokens": None, "total_tokens": None}
                finish_reason = "retrieval_no_match"
                error = None
                try:
                    retrieved = retrieve_fts(conn, case["question"], limit=3)
                    citations = citations_for(retrieved)
                    if retrieved:
                        if client is None:
                            client = OpenAI(base_url=cfg.base_url, api_key=cfg.api_key,
                                            timeout=cfg.timeout_seconds)
                        generated = request_answer(client, cfg.model, case["question"], retrieved,
                                                   citations, cfg.max_tokens)
                        answer = generated["answer"]
                        finish_reason = generated["finish_reason"]
                        usage = generated["usage"]
                except Exception as exc:
                    error = {"type": type(exc).__name__, "message": "endpoint request failed"}
                    finish_reason = "error"
                latency_ms = round((time.perf_counter() - started) * 1000, 2)
                if not retrieved and error is None:
                    status = "retrieval_no_match"
                elif error is not None:
                    status = "error"
                else:
                    status = _status(finish_reason, answer)

                validation = validate_answer(answer, finish_reason, citations)
                complete = status == "completed"
                expected = set(case["expected_source_ids"])
                known = {citation["marker"]: citation["source_id"] for citation in citations}
                phrase_match = (
                    has_expected_phrase(answer, case["required_answer_terms"])
                    if case["answerable"] and complete else False if case["answerable"] else None
                )
                expected_citation = (
                    complete and any(known.get(marker) in expected for marker in validation["markers"])
                ) if case["answerable"] else None
                marker_integrity = (
                    complete and validation["citation_marker_integrity"]
                ) if case["answerable"] else None
                abstained = (
                    True if status == "retrieval_no_match" else complete and validation["abstained"]
                )
                if status == "retrieval_no_match" and not case["answerable"]:
                    accepted = True
                elif case["answerable"]:
                    accepted = complete and bool(phrase_match) and bool(expected_citation) and bool(marker_integrity)
                else:
                    accepted = complete and abstained
                outcomes.append({
                    "case_id": case["id"],
                    "status": status,
                    "retrieved_source_ids": [doc["id"] for doc in retrieved],
                    "finish_reason": finish_reason,
                    "latency_ms": latency_ms,
                    "usage": usage,
                    "answer": answer,
                    "answer_phrase_check": phrase_match,
                    "abstained": abstained,
                    "citation_markers": validation["markers"],
                    "unknown_citation_markers": validation["unknown_markers"],
                    "citation_marker_integrity": marker_integrity,
                    "cites_expected_source": expected_citation,
                    "answer_accepted": bool(accepted),
                    "error": error,
                })

    answerable = [item for item, case in zip(outcomes, cases) if case["answerable"]]
    unanswerable = [item for item, case in zip(outcomes, cases) if not case["answerable"]]
    total = len(outcomes)
    answerable_count = len(answerable)
    unanswerable_count = len(unanswerable)
    return {
        "mode": "live_model_opt_in",
        "started_at": run_started_at,
        "model": cfg.model,
        "configuration": {
            "temperature": 0.1,
            "max_tokens": cfg.max_tokens,
            "timeout_seconds": cfg.timeout_seconds,
            "source_sha256": _sha256(SOURCE_PATH),
            "cases_sha256": _sha256(CASES_PATH),
            "system_prompt_sha256": hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest(),
        },
        "case_count": total,
        "limited_run": limit is not None,
        "metrics": {
            "answer_phrase_check_rate_answerable": round(sum(bool(i["answer_phrase_check"]) for i in answerable) / answerable_count, 4) if answerable_count else None,
            "expected_source_citation_rate_answerable": round(sum(bool(i["cites_expected_source"]) for i in answerable) / answerable_count, 4) if answerable_count else None,
            "citation_marker_integrity_rate_answerable": round(sum(bool(i["citation_marker_integrity"]) for i in answerable) / answerable_count, 4) if answerable_count else None,
            "abstention_rate_unanswerable": round(sum(bool(i["abstained"]) for i in unanswerable) / unanswerable_count, 4) if unanswerable_count else None,
            "accepted_answer_rate": round(sum(i["answer_accepted"] for i in outcomes) / total, 4) if total else None,
            "endpoint_errors": sum(i["status"] == "error" for i in outcomes),
            "non_completed_model_answers": sum(i["status"] not in ("completed", "retrieval_no_match") for i in outcomes),
        },
        "limitations": (
            "Phrase checks are brittle proxies for answer correctness; citation checks validate marker mapping, "
            "not whether cited text entails each claim. Incomplete, filtered, unsupported, and failed requests "
            "remain in the metric denominators and cannot be accepted. Abstention is detected by a small phrase "
            "list. Review answers and excerpts manually before making quality claims."
        ),
        "cases": outcomes,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True,
                        help="write potentially large result JSON to this path")
    parser.add_argument("--limit", type=int,
                        help="evaluate only the first N cases (useful for a small smoke run)")
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be at least 1")
    report = run_live(limit=args.limit)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"mode": report["mode"], "case_count": report["case_count"],
                      "metrics": report["metrics"]}, indent=2))


if __name__ == "__main__":
    main()
