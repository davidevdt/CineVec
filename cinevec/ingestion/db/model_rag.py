"""
Schema for the TMDB-style dataset.

Column mapping from the CSV:
  overview -> plot, vote_average -> rating, release_date -> year (extracted),
  genre (comma-separated string) -> genres text[], original_language -> language
Kept: vote_count (needed for trustworthy "best rated" answers).
Dropped: popularity (stale proprietary snapshot), cast (not in this dataset).
Added: weighted_rating — IMDb-style Bayesian rating computed at ingest,
  so "best rated" doesn't crown a movie with 8.6 from 255 votes.
"""

from pgvector.sqlalchemy import Vector
from sqlalchemy import Computed, Float, Index, Integer, Text
from sqlalchemy.dialects.postgresql import ARRAY, TSVECTOR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


EMBED_DIM = 384


class Base(DeclarativeBase):
    pass


class Movie(Base):
    __tablename__ = "movies"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    title: Mapped[str] = mapped_column(Text)
    year: Mapped[int | None]
    genres: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    language: Mapped[str | None] = mapped_column(Text)   # ISO code, e.g. 'en'
    rating: Mapped[float | None] = mapped_column(Float)          # vote_average
    vote_count: Mapped[int | None] = mapped_column(Integer)
    weighted_rating: Mapped[float | None] = mapped_column(Float)  # Bayesian weighting
    plot: Mapped[str | None] = mapped_column(Text)               # overview
    embedding = mapped_column(Vector(EMBED_DIM), nullable=True)

    search_doc = mapped_column(
        TSVECTOR,
        Computed(
            "setweight(to_tsvector('english', coalesce(title, '')), 'A') || "
            "setweight(to_tsvector('english', coalesce(plot,  '')), 'B') || "
            "setweight(to_tsvector('english', imm_array_to_string(genres)), 'C')",
            persisted=True,
        ),
    )

    __table_args__ = (
        Index("movies_search_idx", "search_doc", postgresql_using="gin"),
        Index("movies_genres_idx", "genres", postgresql_using="gin"),
        Index("movies_year_idx", "year"),
        Index("movies_lang_idx", "language"),
        Index("movies_wr_idx", "weighted_rating"),
        Index("movies_embed_idx", "embedding", postgresql_using="hnsw",
              postgresql_ops={"embedding": "vector_cosine_ops"}),
    )




