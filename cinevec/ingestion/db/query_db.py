"""
db_test.py — test queries against the CineVec database.
"""

import sys

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from cinevec.logging import logger
from cinevec.ingestion.db.build_rag_db import get_engine


# ---------------------------------------------------------------- helpers
def query_db(engine, sql: str) -> None:
    """Run arbitrary SQL. SELECTs print rows; other statements are committed."""
    with engine.begin() as conn:
        result = conn.execute(text(sql))
        if result.returns_rows:
            rows = result.mappings().all()
            for r in rows:
                logger.info(f"  {dict(r)}")
        else:
            logger.info(f"-- OK ({result.rowcount} row(s) affected)")


