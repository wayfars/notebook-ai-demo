"""Shared grounded-answer request and citation validation helpers."""
from __future__ import annotations

import re
from typing import Any

from .prompts import SYSTEM_PROMPT

ABSTENTION_HINTS = (
    "not contain enough information", "not enough information", "cannot answer",
    "can't answer", "do not know", "don't know", "unable to answer",
)
MARKER_RE = re.compile(r"\[(S[^\]\s]*)\]")


def build_context(documents: list[dict], citations: list[dict]) -> str:
    return "\n\n".join(
        f'<source id="{citation["marker"]}" title="{doc["title"]}">\n{doc["body"]}\n</source>'
        for doc, citation in zip(documents, citations)
    )


def request_answer(client: Any, model: str, question: str, documents: list[dict],
                   citations: list[dict], max_tokens: int) -> dict:
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT + "\n\n" + build_context(documents, citations)},
            {"role": "user", "content": question},
        ],
        temperature=0.1,
        max_tokens=max_tokens,
    )
    if not response.choices:
        return {"answer": "", "finish_reason": "empty_choices", "usage": _usage(response)}
    choice = response.choices[0]
    return {
        "answer": (choice.message.content or "").strip(),
        "finish_reason": choice.finish_reason or "unknown",
        "usage": _usage(response),
    }


def validate_answer(answer: str, finish_reason: str | None, citations: list[dict]) -> dict:
    markers = list(dict.fromkeys(MARKER_RE.findall(answer)))
    known = {citation["marker"] for citation in citations}
    unknown = [marker for marker in markers if marker not in known]
    has_valid_marker = any(marker in known for marker in markers)
    abstained = any(hint in answer.casefold() for hint in ABSTENTION_HINTS)
    return {
        "markers": markers,
        "unknown_markers": unknown,
        "missing_citations": not has_valid_marker and not abstained,
        "has_valid_marker": has_valid_marker,
        "citation_marker_integrity": has_valid_marker and not unknown,
        "complete": finish_reason == "stop" and bool(answer.strip()),
        "abstained": abstained,
    }


def has_expected_phrase(answer: str, alternatives: list[str]) -> bool:
    folded = answer.casefold()
    return any(phrase.casefold() in folded for phrase in alternatives)


def _usage(response: Any) -> dict:
    usage = getattr(response, "usage", None)
    return {
        "prompt_tokens": getattr(usage, "prompt_tokens", None),
        "completion_tokens": getattr(usage, "completion_tokens", None),
        "total_tokens": getattr(usage, "total_tokens", None),
    }
