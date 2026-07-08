"""
Build the movie database from the TMDB-style dataframe.
"""

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from cinevec.ingestion.db.model_rag import Movie
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from cinevec.logging import logger
from cinevec.ingestion.embed import get_embedder
from box import ConfigBox

BATCH = 256 # embedding batch size 


def ingest(engine: Engine, movies: list[dict], config: ConfigBox) -> bool:
    """Ingest movies incrementally: rows whose id already exists are
    skipped (and never embedded). Safe to re-run."""
    embedder = get_embedder(config)
    try:
        # 1. Which movies are already there? Skip them before embedding.
        with Session(engine) as session:
            existing = set(session.scalars(select(Movie.id)))
        new = [x for x in movies if x["id"] not in existing]
        logger.info(f"{len(existing)} movies already in db, {len(new)} new.")
        if not new:
            return True

        # 2. Embed only the newcomers — this is where the minutes live.
        docs = [
            f"{x['title']}. Genres: {', '.join(x['genres'] or [])}. {x['plot'] or ''}"
            for x in new
        ]

        # 3. Insert with a conflict guard as a race-condition safety net.
        with Session(engine) as session:
            for i in range(0, len(new), BATCH):
                chunk = new[i:i + BATCH]
                vecs = embedder.encode_batch(docs[i:i + BATCH])
                rows = [dict(x, embedding=vec) for x, vec in zip(chunk, vecs)]
                session.execute(
                    insert(Movie)
                    .values(rows)
                    .on_conflict_do_nothing(index_elements=[Movie.id])
                )
                session.commit()
                logger.info(f"Ingested {min(i + BATCH, len(new))}/{len(new)}")
        logger.info("All new movies successfully ingested to db.")
    except Exception:
        logger.exception("Error ingesting movies")
        return False

    return True