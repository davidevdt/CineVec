"""
Retrieval layer of the TMDB dataset: five search modes over one table.
"""

from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import Select, bindparam, cast, desc, func, select, text
from sqlalchemy.dialects.postgresql import ARRAY, REAL
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from cinevec.ingestion.db.model_rag import EMBED_DIM, Movie
from cinevec.ingestion.embed.embedder import Embedder

# ts_rank's own A,B,C defaults; D stays 0.0, no label is assigned to it.
_DEFAULT_WEIGHTS = {"title": 1.0, "plot": 0.4, "genres": 0.2}


def _weight_array(weights: dict | None = None) -> list[float]:
    """text-search rank requires weights in D,C,B,A order."""
    w = {**_DEFAULT_WEIGHTS, **(weights or {})}
    return [0.0, w["genres"], w["plot"], w["title"]]


COLS = (
    Movie.id,
    Movie.title,
    Movie.year,
    Movie.genres,
    Movie.language,
    Movie.rating,
    Movie.vote_count,
    Movie.weighted_rating,
    Movie.plot,
)


# ---------------------------------------------------------------- Helpers
def _apply_filters(
    stmt: Select,
    genre: str | None = None,
    language: str | None = None,
    year_min: int | None = None,
    year_max: int | None = None,
    rating_min: float | None = None,
    rating_max: float | None = None,
    min_votes: int | None = None,
) -> Select:
    if genre:
        stmt = stmt.where(
            func.array_to_string(Movie.genres, " ").ilike(f"%{genre}%")
        )
    if language:
        stmt = stmt.where(Movie.language == language.lower())
    if year_min is not None:
        stmt = stmt.where(Movie.year >= year_min)
    if year_max is not None:
        stmt = stmt.where(Movie.year <= year_max)
    if rating_min is not None:
        stmt = stmt.where(Movie.rating >= rating_min)
    if rating_max is not None:
        stmt = stmt.where(Movie.rating <= rating_max)
    if min_votes is not None:
        stmt = stmt.where(Movie.vote_count >= min_votes)

    return stmt


def _run(engine: Engine, stmt: Select) -> list[dict]:
    """Runs the query and returns results in form of list of dicts."""
    with Session(engine) as s:
        return [dict(r) for r in s.execute(stmt).mappings().all()]


# ---------------------------------------------------------------- 1. Filter
def filter_search(
    engine: Engine, limit: int = 10, sort_by_rating: bool = True, **filters
) -> list[dict]:
    stmt = _apply_filters(select(*COLS), **filters)
    order = (
        Movie.weighted_rating.desc().nulls_last()
        if sort_by_rating
        else Movie.year.desc().nulls_last()
    )
    return _run(engine, stmt.order_by(order).limit(limit))


# ---------------------------------------------------------------- 2. Text-Search
def text_search(
    engine: Engine,
    query: str,
    limit: int = 10,
    weights: dict | None = None,
    norm: int = 0,
    **filters,
) -> list[dict]:
    """
    weights: labels weights (a dict),
    norm: text-search rank-normalization flag
    (0=none, 1=divide by 1+log(doc length), 32=rank/(rank+1))
    """
    # the following function stems the query words and structures the parsing
    tsq = func.websearch_to_tsquery("english", query)
    warr = cast(_weight_array(weights), ARRAY(REAL))
    # score the movies:
    score = func.ts_rank(warr, Movie.search_doc, tsq, norm).label("score")
    stmt = (
        _apply_filters(select(*COLS, score), **filters)
        # @@ = "document matches query": filters to true matches; ts_rank only ranks them
        .where(Movie.search_doc.op("@@")(tsq))
        .order_by(desc("score"))
        .limit(limit)
    )
    return _run(engine, stmt)


# ---------------------------------------------------------------- 3. Vector Search
def vector_search(
    engine: Engine, embedder: Embedder, query: str, limit: int = 10, **filters
) -> list[dict]:
    distance = Movie.embedding.cosine_distance(embedder.encode(query)).label(
        "score"
    )
    stmt = (
        _apply_filters(select(*COLS, distance), **filters)
        .where(Movie.embedding.is_not(None))
        .order_by(distance)
        .limit(limit)
    )

    return _run(engine, stmt)


# ---------------------------------------------------------------- 4. Similar
def similar_search(
    engine: Engine, title: str, limit: int = 10, **filters
) -> dict:
    """Nearest neighbors of a movie's own stored embedding."""
    with Session(engine) as s:
        # Resolve a fuzzy title to one movie
        ref = s.execute(
            select(Movie.id, Movie.title)
            .where(Movie.title.ilike(f"%{title}%"))
            .order_by(func.length(Movie.title))
            .limit(1)
        ).first()
    if ref is None:
        return {"error": f"No movie found matching '{title}'."}

    ref_vec = (
        select(Movie.embedding).where(Movie.id == ref.id).scalar_subquery()
    )
    distance = Movie.embedding.cosine_distance(ref_vec).label("score")
    stmt = (
        _apply_filters(select(*COLS, distance), **filters)
        .where(Movie.id != ref.id, Movie.embedding.is_not(None))
        .order_by(distance)
        .limit(limit)
    )
    return {"reference": ref.title, "results": _run(engine, stmt)}


# ---------------------------------------------------------------- 5. Hybrid Search
_HYBRID_FILTERS = {
    "genre": "array_to_string(m.genres, ' ') ILIKE :genre",
    "language": "m.language = :language",
    "year_min": "m.year >= :year_min",
    "year_max": "m.year <= :year_max",
    "rating_min": "m.rating >= :rating_min",
    "rating_max": "m.rating <= :rating_max",
    "min_votes": "m.vote_count >= :min_votes",
}

# How the query text becomes a tsquery for the hybrid text arm.
#   all      websearch_to_tsquery: every word must appear in the same movie.
#            Right for keywords ("heist"), but a plot is two sentences, so any
#            sentence-length query matches nothing at all.
#   any      OR of the stemmed words. Operators (phrases, -negation) are
#            dropped, so this is purely "movies containing any of these words".
#   fallback "all", falling back to "any" only when "all" would return nothing.
#            Queries that already match are ranked exactly as before.
_TSQ_ALL = "websearch_to_tsquery('english', :q)"
_TSQ_ANY = "array_to_string(tsvector_to_array(to_tsvector('english', :q)), ' | ')::tsquery"
_TSQ_FALLBACK = (
    f"(SELECT CASE WHEN EXISTS (SELECT 1 FROM movies WHERE search_doc @@ {_TSQ_ALL})"
    f" THEN {_TSQ_ALL} ELSE {_TSQ_ANY} END)"
)
TEXT_MODES = {"all": _TSQ_ALL, "any": _TSQ_ANY, "fallback": _TSQ_FALLBACK}


def hybrid_search(
    engine: Engine,
    embedder: Embedder,
    query: str,
    limit: int = 10,
    weights: dict | None = None,
    norm: int = 0,
    rrf_k: int = 60,
    n_candidates: int = 30,
    text_mode: str = "fallback",
    **filters,
) -> list[dict]:
    """Reciprocal Rank Fusion in one SQL statement. weights/norm tune the
    text side (see text_search); rrf_k tunes the fusion itself; text_mode
    picks how the query becomes a tsquery (see TEXT_MODES)."""
    tsq = TEXT_MODES[text_mode]
    active = {k: v for k, v in filters.items() if v is not None}
    fsql = "".join(f" AND {_HYBRID_FILTERS[k]}" for k in active)
    params: dict[str, Any] = {}
    for k, v in active.items():
        if k == "genre":
            params[k] = f"%{v}%"
        elif k == "language":
            params[k] = v.lower()
        else:
            params[k] = v
    params |= {
        "q": query,
        "qvec": embedder.encode(query),
        "weights": _weight_array(weights),
        "norm": norm,
        "k": rrf_k,
        "pool": n_candidates,
        "limit": limit,
    }

    stmt = text(f"""
        -- Every ORDER BY here ends in m.id. ts_rank ties are common, and so
        -- are RRF ties (a text-only hit at rank r scores 1/(k+r), exactly the
        -- same as a vector-only hit at rank r). Without a tiebreaker Postgres
        -- returns tied rows in whatever order it likes, so the same query can
        -- come back ordered differently between calls.
        WITH text_hits AS (
            SELECT m.id, row_number() OVER (
                ORDER BY ts_rank(:weights, m.search_doc, {tsq}, :norm) DESC,
                         m.id
            ) AS rank
            FROM movies m
            WHERE m.search_doc @@ {tsq} {fsql}
            -- Explicit, like vec_hits below: :pool has to keep the best rows,
            -- not whichever ones the planner happens to emit first.
            ORDER BY ts_rank(:weights, m.search_doc, {tsq}, :norm) DESC, m.id
            LIMIT :pool
        ),
        vec_hits AS (
            SELECT m.id, row_number() OVER (
                ORDER BY m.embedding <=> :qvec, m.id
            ) AS rank
            FROM movies m
            WHERE m.embedding IS NOT NULL {fsql}
            ORDER BY m.embedding <=> :qvec, m.id
            LIMIT :pool
        ),
        fused AS (
            SELECT coalesce(t.id, v.id) AS id,
                   coalesce(1.0 / (:k + t.rank), 0) +
                   coalesce(1.0 / (:k + v.rank), 0) AS score
            FROM text_hits t
            FULL OUTER JOIN vec_hits v ON t.id = v.id
        )
        SELECT m.id, m.title, m.year, m.genres, m.language, m.rating,
               m.vote_count, m.weighted_rating, m.plot,
               round(f.score, 4) AS score
        FROM fused f JOIN movies m ON m.id = f.id
        ORDER BY f.score DESC, m.id
        LIMIT :limit
    """).bindparams(
        bindparam("qvec", type_=Vector(EMBED_DIM)),
        bindparam("weights", type_=ARRAY(REAL)),
    )

    with Session(engine) as s:
        return [dict(r) for r in s.execute(stmt, params).mappings().all()]
