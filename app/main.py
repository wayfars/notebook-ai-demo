from __future__ import annotations

import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from openai import OpenAI
from pydantic import BaseModel, Field

from .settings import Settings
from .store import citations_for, connect, load_documents, retrieve_fts, seed_documents
from .generation import request_answer, validate_answer
from .prompts import SYSTEM_PROMPT

ROOT = Path(__file__).resolve().parent.parent
SAMPLE_PATH = ROOT / "data" / "sample_sources.json"
class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


def create_app(settings: Settings | None = None) -> FastAPI:
    cfg = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        with connect(cfg.database_path) as conn:
            if SAMPLE_PATH.exists():
                seed_documents(conn, json.loads(SAMPLE_PATH.read_text()))
        yield

    app = FastAPI(title="Notebook Grounded Chat", lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")

    @app.get("/", response_class=HTMLResponse)
    def index():
        return (ROOT / "templates" / "index.html").read_text()

    @app.get("/api/sources")
    def sources():
        return [{"id": d["id"], "title": d["title"]} for d in load_documents(cfg.database_path)]

    @app.post("/api/ask")
    def ask(request: AskRequest):
        if not request.question.strip():
            raise HTTPException(422, "question must not be blank")
        with connect(cfg.database_path) as conn:
            retrieved = retrieve_fts(conn, request.question.strip())
        if not retrieved:
            return {"answer": "The sources do not contain enough information to answer that question.",
                    "citations": [], "sources": [], "retrieval": "no_match",
                    "citation_validation": {"markers": [], "unknown_markers": [],
                                            "missing_citations": False}}
        citations = citations_for(retrieved)
        try:
            client = OpenAI(base_url=cfg.base_url, api_key=cfg.api_key, timeout=cfg.timeout_seconds)
            generated = request_answer(client, cfg.model, request.question.strip(), retrieved,
                                       citations, cfg.max_tokens)
        except Exception as exc:
            raise HTTPException(502, f"model endpoint request failed ({type(exc).__name__})") from exc
        if generated["finish_reason"] == "empty_choices":
            raise HTTPException(502, "model endpoint returned no completion choices")
        if generated["finish_reason"] == "length":
            raise HTTPException(502, "model response was truncated at the configured token limit")
        answer = generated["answer"]
        if not answer:
            raise HTTPException(502, "model endpoint returned an empty answer")
        validation = validate_answer(answer, generated["finish_reason"], citations)
        if not validation["complete"]:
            raise HTTPException(502, "model endpoint returned an unsupported or incomplete response")
        citation_validation = {k: validation[k] for k in (
            "markers", "unknown_markers", "missing_citations", "has_valid_marker",
            "citation_marker_integrity", "complete", "abstained")}
        return {
            "answer": answer,
            "citations": [c for c in citations if c["marker"] in validation["markers"]],
            "sources": [{**citation, "excerpt": doc["body"]} for doc, citation in zip(retrieved, citations)],
            "retrieval": "matched_sources",
            "citation_validation": citation_validation,
        }

    return app


app = create_app()
