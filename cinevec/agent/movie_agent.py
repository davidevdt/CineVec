"""
The PydanticAI agent for the TMDB dataset.

Run:  python movie_agent.py
      python movie_agent.py "What drama movies were rated the best in the 90s?"
"""

import os
import sys
from dataclasses import dataclass
from typing import Any, Literal

from pydantic_ai import Agent, RunContext
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from cinevec.agent import search
from cinevec.agent.prompts import SYSTEM_PROMPT
from cinevec.ingestion.db.build_rag_db import get_engine
from cinevec.ingestion.db.model_rag import Movie
from cinevec.ingestion.embed import get_embedder
from cinevec.ingestion.embed.embedder import Embedder
from cinevec.utils.file_utils import load_config_file

config = load_config_file()
MODEL = os.getenv("MOVIE_AGENT_MODEL", "openai:gpt-5.4-mini")
MAX_RESULTS = 5
MAX_RESULTS = config.agent_max_results
HYBRID_SEARCH_N_CANDIDATES = config.hybrid_search_n_candidates
RRF_K = config.rrf_k
HYBRID_TEXT_MODE = config.hybrid_text_mode
TITLE_WEIGHT = config.text_search_title_weight
PLOT_WEIGHT = config.text_search_plot_weight
GENRES_WEIGHT = config.text_search_genres_weight
TEXT_SEARCH_WEIGHTS = {
    "title": TITLE_WEIGHT,
    "plot": PLOT_WEIGHT,
    "genres": GENRES_WEIGHT,
}


def clamp(limit: int) -> int:
    return max(1, min(limit, MAX_RESULTS))


@dataclass
class Deps:
    engine: Engine
    embedder: Embedder


agent = Agent(
    MODEL, deps_type=Deps, system_prompt=SYSTEM_PROMPT % ((MAX_RESULTS,) * 3)
)


@agent.tool
def get_movie_details(ctx: RunContext[Deps], title: str) -> dict | str:
    """Look up a single movie by (partial, case-insensitive) title. Returns
    year, genres, language, rating, vote count and plot. Use this to resolve
    reference movies before deriving filters like 'same decade as X'."""
    with Session(ctx.deps.engine) as s:
        row = (
            s.execute(
                select(*search.COLS)
                .where(Movie.title.ilike(f"%{title}%"))
                .order_by(func.length(Movie.title))
                .limit(1)
            )
            .mappings()
            .first()
        )
    return dict(row) if row else f"No movie found matching '{title}'."


@agent.tool
def find_similar_movies(
    ctx: RunContext[Deps],
    title: str,
    year_min: int | None,
    year_max: int | None,
    genre: str | None = None,
    language: str | None = None,
    rating_min: float | None = None,
    rating_max: float | None = None,
    min_votes: int | None = None,
    limit: int = MAX_RESULTS,
) -> dict:
    """Find movies whose plot/theme is most similar to a given movie already
    in the database, by comparing stored embeddings. The reference movie is
    excluded from results. Optional structured filters narrow the candidates
    (language is an ISO 639-1 code like 'en' or 'fr'). For era constraints
    relative to the reference movie, pass explicit year_min/year_max. These
    two are required: pass null for both only if the user gave no era
    constraint at all."""
    return search.similar_search(
        ctx.deps.engine,
        title,
        limit=clamp(limit),
        genre=genre,
        language=language,
        year_min=year_min,
        year_max=year_max,
        rating_min=rating_min,
        rating_max=rating_max,
        min_votes=min_votes,
    )


@agent.tool
def search_movies(
    ctx: RunContext[Deps],
    mode: Literal["filter", "text", "vector", "hybrid"],
    query: str | None = None,
    genre: str | None = None,
    language: str | None = None,
    year_min: int | None = None,
    year_max: int | None = None,
    rating_min: float | None = None,
    rating_max: float | None = None,
    min_votes: int | None = None,
    limit: int = MAX_RESULTS,
) -> list[dict] | list:
    """Search the movie database.

    mode='filter' needs no query; results are sorted by a vote-count-weighted
    rating (best first), which is the right answer to "best rated" questions.
    Modes 'text', 'vector' and 'hybrid' require a query string and rank by
    relevance. All modes accept the same optional filters (genre matches
    case-insensitively; language is an ISO 639-1 code; year and rating ranges
    are inclusive; min_votes filters out little-known movies). At most 5
    results are returned."""
    limit = clamp(limit)
    filters: dict[str, Any] = dict(
        genre=genre,
        language=language,
        year_min=year_min,
        year_max=year_max,
        rating_min=rating_min,
        rating_max=rating_max,
        min_votes=min_votes,
    )

    if mode == "filter":
        return search.filter_search(ctx.deps.engine, limit=limit, **filters)
    if not query:
        return [{"error": "query is required for text/vector/hybrid mode"}]
    if mode == "text":
        return search.text_search(
            ctx.deps.engine,
            query,
            limit=limit,
            weights=TEXT_SEARCH_WEIGHTS,
            **filters,
        )
    if mode == "vector":
        return search.vector_search(
            ctx.deps.engine, ctx.deps.embedder, query, limit=limit, **filters
        )
    return search.hybrid_search(
        ctx.deps.engine,
        ctx.deps.embedder,
        query,
        weights=TEXT_SEARCH_WEIGHTS,
        limit=limit,
        rrf_k=RRF_K,
        n_candidates=HYBRID_SEARCH_N_CANDIDATES,
        text_mode=HYBRID_TEXT_MODE,
        **filters,
    )


def main():
    deps = Deps(engine=get_engine(), embedder=get_embedder(config=config))

    if len(sys.argv) > 1:
        result = agent.run_sync(" ".join(sys.argv[1:]), deps=deps)
        print(result.output)
        return

    print("Movie agent ready. Ctrl-C to quit.")

    history = []
    while True:
        try:
            question = input("\nYou: ").strip()
        except (KeyboardInterrupt, EOFError):
            break
        if not question:
            continue
        result = agent.run_sync(question, deps=deps, message_history=history)
        history = result.all_messages()
        print("\nAgent:", result.output)


if __name__ == "__main__":
    main()
