from __future__ import annotations

import os

from fastapi import FastAPI, Query

from .models import CommitMemoryUpdateRequest, ProposeMemoryUpdateRequest
from .service import MemoryService

MEMORY_ROOT = os.environ.get("CLAWMIND_MEMORY_ROOT", "examples/memory")
service = MemoryService(MEMORY_ROOT)
app = FastAPI(title="ClawMind Memory API", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/memory/{user_id}/profile")
def read_profile(user_id: str) -> dict:
    return service.read_profile(user_id).to_dict()


@app.get("/memory/{user_id}/preferences")
def read_preferences(user_id: str) -> dict:
    return service.read_preferences(user_id).to_dict()


@app.get("/memory/{user_id}/search")
def search_memory(
    user_id: str,
    query: str = Query(..., min_length=2),
    scopes: list[str] | None = Query(default=None),
    top_k: int = Query(default=8, ge=1, le=50),
) -> dict:
    return service.search_memory(
        user_id=user_id,
        query=query,
        scopes=scopes,
        top_k=top_k,
    ).to_dict()


@app.post("/memory/proposals")
def propose_memory_update(payload: dict) -> dict:
    request = ProposeMemoryUpdateRequest(**payload)
    return service.propose_memory_update(request).to_dict()


@app.post("/memory/commit")
def commit_memory_update(payload: dict) -> dict:
    request = CommitMemoryUpdateRequest(**payload)
    return service.commit_memory_update(request).to_dict()
