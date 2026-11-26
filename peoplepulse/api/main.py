"""FastAPI service for the guard-railed GenAI HR query assistant.

Endpoints:
  GET  /health   -- liveness probe.
  GET  /views    -- the allow-listed MIS views the assistant may query.
  POST /query     -- {"question": "..."} -> answer rows or a structured refusal.

Run:  uvicorn peoplepulse.api.main:app --port 8002
"""

from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel, Field

from peoplepulse.api.guardrails import ALLOWED_TABLES
from peoplepulse.api.nl2sql import answer_dict
from peoplepulse.config import LLM_PROVIDER

app = FastAPI(
    title="PeoplePulse HR Query Assistant",
    description=(
        "Natural-language HR analytics over the real IBM HR Attrition dataset, "
        "with SQL guardrails."
    ),
    version="0.1.0",
)


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=500, examples=[
        "What is the attrition rate for employees working overtime?"
    ])
    provider: str | None = Field(
        None, description="Override LLM provider: mock | gemini | ollama"
    )


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "default_provider": LLM_PROVIDER}


@app.get("/views")
def views() -> dict:
    """The only tables the assistant is allowed to read."""
    return {"allowed_views": sorted(ALLOWED_TABLES)}


@app.post("/query")
def query(req: QueryRequest) -> dict:
    """Answer an HR analytics question (or return a structured refusal)."""
    return answer_dict(req.question, req.provider)
