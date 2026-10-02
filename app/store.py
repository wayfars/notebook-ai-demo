"""Small SQLite store with full-text retrieval for the focused demo."""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Iterable

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  body TEXT NOT NULL
);
CREATE VIRTUAL TABLE IF NOT EXISTS sources_fts USING fts5(
  id UNINDEXED, title, body
);
"""
TOKEN_RE = re.compile(r"[a-z0-9]+", re.I)
STOPWORDS = {
    "about", "after", "again", "also", "among", "and", "any", "are", "around",
    "before", "being", "between", "does", "each", "from", "have", "how", "into",
    "is", "its", "many", "much", "name", "not", "of", "on", "our", "should",
    "that", "the", "their", "them", "there", "these", "this", "those", "what",
    "when", "where", "which", "who", "why", "with", "would", "you", "your",
}


def _terms(text: str) -> list[str]:
    return [w.lower() for w in TOKEN_RE.findall(text) if len(w) > 2 and w.lower() not in STOPWORDS]


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA)
    return conn


def seed_documents(conn: sqlite3.Connection, documents: Iterable[dict]) -> None:
    for document in documents:
        conn.execute(
            "INSERT OR REPLACE INTO sources(id,title,body) VALUES (?,?,?)",
            (document["id"], document["title"], document["body"]),
        )
        conn.execute("DELETE FROM sources_fts WHERE id=?", (document["id"],))
        conn.execute(
            "INSERT INTO sources_fts(id,title,body) VALUES (?,?,?)",
            (document["id"], document["title"], document["body"]),
        )
    conn.commit()


def load_documents(path: Path) -> list[dict]:
    with connect(path) as conn:
        return [dict(row) for row in conn.execute("SELECT id,title,body FROM sources ORDER BY id")]


def _fts_query(text: str) -> str:
    words = list(dict.fromkeys(_terms(text)))[:20]
    return " OR ".join('"' + w.replace('"', '""') + '"' for w in words)


def retrieve_fts(conn: sqlite3.Connection, question: str, limit: int = 3) -> list[dict]:
    query = _fts_query(question)
    if not query:
        return []
    rows = conn.execute(
        """SELECT id,title,body,bm25(sources_fts,0.0,1.0,1.0) AS score
           FROM sources_fts WHERE sources_fts MATCH ? ORDER BY score LIMIT ?""",
        (query, limit),
    ).fetchall()
    return [dict(row) for row in rows]


def retrieve_overlap(documents: list[dict], question: str, limit: int = 3) -> list[dict]:
    """Transparent baseline: rank by shared unique word count, ties by id."""
    terms = set(_terms(question))
    scored = []
    for document in documents:
        words = {w.lower() for w in TOKEN_RE.findall(document["title"] + " " + document["body"])}
        score = len(terms & words)
        if score:
            scored.append((score, document["id"], document))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [doc for _, _, doc in scored[:limit]]


def citations_for(documents: list[dict]) -> list[dict]:
    return [{"marker": f"S{i}", "source_id": d["id"], "title": d["title"]}
            for i, d in enumerate(documents, start=1)]


def citation_is_valid(marker: str, citations: list[dict]) -> bool:
    return any(c["marker"] == marker for c in citations)
