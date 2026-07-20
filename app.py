"""
FastAPI server for the CineVec movie agent.

Run:  uv run uvicorn app:app --reload
Then: http://127.0.0.1:8000/
"""

import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

# Must run before the imports below: importing movie_agent builds the Agent,
# which reads OPENAI_API_KEY immediately.
load_dotenv()

from cinevec.ingestion import orchestrate_ingestion  # noqa: E402
from cinevec.agent.movie_agent import agent, Deps, MODEL  # noqa: E402
from cinevec.ingestion.db.build_rag_db import get_engine  # noqa: E402
from cinevec.ingestion.embed import get_embedder  # noqa: E402
from cinevec.logging import logger  # noqa: E402
from cinevec.monitoring import (  # noqa: E402
    build_record,
    conversation_exists,
    create_monitoring_schema,
    save_conversation,
    save_feedback,
)
from cinevec.utils.file_utils import load_config_file  # noqa: E402

REBUILD = os.getenv("REBUILD", "false").lower() == "true"
SAMPLE_N = int(os.getenv("SAMPLE_N")) if os.getenv("SAMPLE_N") else None

deps: Deps | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Runs once at startup. Ingestion is safe to repeat: it reuses the
    downloaded CSV and skips movies already in the database, so only the
    first run (empty database) takes minutes."""
    global deps

    orchestrate_ingestion(rebuild=REBUILD, sample_n=SAMPLE_N)

    config = load_config_file()
    deps = Deps(engine=get_engine(), embedder=get_embedder(config=config))

    # Separate call on purpose: orchestrate_ingestion -> create_schema drops
    # every table on the movies Base when REBUILD=true, and monitoring history
    # has to survive that.
    create_monitoring_schema(deps.engine)

    yield


app = FastAPI(title="CineVec movie agent", lifespan=lifespan)

# Relative to this file, so the server works from any working directory.
INDEX_HTML = Path(__file__).parent / "static" / "index.html"


@app.get("/")
def home() -> FileResponse:
    return FileResponse(INDEX_HTML)


class Question(BaseModel):
    question: str


class Answer(BaseModel):
    answer: str
    # None if the conversation could not be recorded; the page then hides the
    # feedback buttons, since a vote would have nothing to point at.
    conversation_id: int | None = None


class FeedbackIn(BaseModel):
    conversation_id: int
    score: Literal[1, -1]   # anything else is rejected before the handler runs


class FeedbackOut(BaseModel):
    status: str
    feedback_id: int


@app.post("/ask", response_model=Answer)
def ask(payload: Question) -> Answer:
    """`def` not `async def`: run_sync blocks, and FastAPI runs sync endpoints
    in a worker thread so one request does not freeze the server."""
    started = time.perf_counter()   # monotonic: a clock step cannot make this negative
    result = agent.run_sync(payload.question, deps=deps)
    response_time = time.perf_counter() - started

    conversation_id = None
    try:
        record = build_record(payload.question, result, MODEL, response_time)
        conversation_id = save_conversation(deps.engine, record)
    except Exception:
        # Monitoring must never cost the user their answer.
        logger.exception("Failed to record conversation")

    return Answer(answer=result.output, conversation_id=conversation_id)


@app.post("/feedback", response_model=FeedbackOut)
def feedback(payload: FeedbackIn) -> FeedbackOut:
    """Record a thumbs up (+1) or down (-1) against an earlier answer."""
    if deps is None:
        raise HTTPException(status_code=503, detail="Agent not ready")
    if not conversation_exists(deps.engine, payload.conversation_id):
        raise HTTPException(
            status_code=404,
            detail=f"No conversation with id {payload.conversation_id}",
        )
    feedback_id = save_feedback(deps.engine, payload.conversation_id, payload.score)
    return FeedbackOut(status="ok", feedback_id=feedback_id)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "agent_ready": deps is not None}
