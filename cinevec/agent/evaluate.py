"""
Offline retrieval evaluation: how often does hybrid_search put the right movie
in the top k, for a set of (movie_id, question) pairs?

Used by notebooks/retrieval_tuning.ipynb to pick the search parameters in
config/config.yaml. Nothing here runs at request time.
"""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import pandas as pd
from sqlalchemy.engine import Engine

from cinevec.agent import search


class CachedEmbedder:
    """Stands in for Embedder, returning vectors computed up front.

    hybrid_search calls embedder.encode(query) on every call, so a sweep of N
    configs over M questions would run N*M ONNX passes. Embedding each question
    once and looking it up here makes that M.
    """

    def __init__(self, vectors: dict):
        self.vectors = vectors
        self.misses = 0

    def encode(self, text, normalize=True):
        if text not in self.vectors:
            # Counted rather than raised so a sweep does not die halfway; the
            # notebook asserts this stays at 0.
            self.misses += 1
            raise KeyError(f"No cached embedding for {text[:60]!r}")
        return self.vectors[text]


def hit_rate(
    ranked_ids: list[list[int]], expected: list[int], k: int = 5
) -> float:
    """Share of questions whose movie appears in the top k."""
    hits = sum(1 for ids, want in zip(ranked_ids, expected) if want in ids[:k])
    return hits / len(expected) if expected else 0.0


def mrr(ranked_ids: list[list[int]], expected: list[int], k: int = 5) -> float:
    """Mean reciprocal rank: 1/position of the movie, 0 if outside the top k.

    Rewards putting the right answer first, not merely somewhere in the list.
    """
    total = 0.0
    for ids, want in zip(ranked_ids, expected):
        for position, movie_id in enumerate(ids[:k], start=1):
            if movie_id == want:
                total += 1 / position
                break
    return total / len(expected) if expected else 0.0


@dataclass
class SearchConfig:
    """One point in the parameter space."""

    title: float
    plot: float
    genres: float
    rrf_k: int
    n_candidates: int
    text_mode: str = "fallback"

    @property
    def weights(self) -> dict:
        # floats, not ints: _weight_array prepends 0.0 and psycopg refuses a
        # mixed int/float array.
        return {
            "title": float(self.title),
            "plot": float(self.plot),
            "genres": float(self.genres),
        }

    def as_dict(self) -> dict:
        return {
            "title": self.title,
            "plot": self.plot,
            "genres": self.genres,
            "rrf_k": self.rrf_k,
            "n_candidates": self.n_candidates,
            "text_mode": self.text_mode,
        }


def _search_one(engine, embedder, question, config, limit):
    rows = search.hybrid_search(
        engine,
        embedder,
        question,
        limit=limit,
        weights=config.weights,
        rrf_k=config.rrf_k,
        n_candidates=config.n_candidates,
        text_mode=config.text_mode,
    )
    return [r["id"] for r in rows]


def evaluate_config(
    engine: Engine,
    embedder,
    pairs: list[tuple[int, str]],
    config: SearchConfig,
    k: int = 5,
    workers: int = 8,
) -> dict:
    """Run every question through one config and score the results.

    Queries run on a thread pool: the Engine is thread-safe and hybrid_search
    opens its own Session per call, so the only shared state is the connection
    pool.
    """
    expected = [movie_id for movie_id, _ in pairs]
    questions = [question for _, question in pairs]

    with ThreadPoolExecutor(max_workers=workers) as pool:
        ranked = list(
            pool.map(
                lambda q: _search_one(engine, embedder, q, config, k),
                questions,
            )
        )

    return {
        **config.as_dict(),
        f"hit@{k}": hit_rate(ranked, expected, k),
        f"mrr@{k}": mrr(ranked, expected, k),
    }


def sweep(
    engine: Engine,
    embedder,
    pairs: list[tuple[int, str]],
    configs: list[SearchConfig],
    k: int = 5,
    workers: int = 8,
    progress=None,
) -> pd.DataFrame:
    """Score every config, best first. `progress` takes an iterable (e.g. tqdm)."""
    iterator = configs if progress is None else progress(configs)
    rows = [
        evaluate_config(engine, embedder, pairs, c, k=k, workers=workers)
        for c in iterator
    ]
    return pd.DataFrame(rows).sort_values(
        f"hit@{k}", ascending=False, ignore_index=True
    )


def weight_grid(
    values: list[float],
    rrf_k: int,
    n_candidates: int,
    text_mode: str = "fallback",
) -> list[SearchConfig]:
    """All weight combinations whose largest weight is 1.0.

    ts_rank caps weights at 1.0, and its ranking is unchanged if every weight is
    scaled by the same constant. So each distinct ranking is a ray through the
    origin, and every ray meets the unit cube on the face where max = 1.0.
    Enumerating only that face covers the whole space without duplicates -- and
    unlike fixing title=1.0, it can still reach plot > title.
    """
    return [
        SearchConfig(t, p, g, rrf_k, n_candidates, text_mode)
        for t in values
        for p in values
        for g in values
        if max(t, p, g) == 1.0
    ]


def fusion_grid(
    weights: dict,
    rrf_ks: list[int],
    n_candidates: list[int],
    text_mode: str = "fallback",
) -> list[SearchConfig]:
    """rrf_k x n_candidates, holding the text weights fixed."""
    return [
        SearchConfig(
            weights["title"],
            weights["plot"],
            weights["genres"],
            k,
            n,
            text_mode,
        )
        for k in rrf_ks
        for n in n_candidates
    ]
