"""
db_test.py — quick sanity checks and test queries against the CineVec database.

Usage:
    python db_test.py                     # dataset stats + all five search modes
    python db_test.py --quick             # skip embedding-based modes (no model load)
    python db_test.py "SELECT ... "       # run arbitrary SQL and print the rows

Edit the QUERIES section at the bottom to taste — this file is meant to be
a scratchpad, not production code.
"""

from sqlalchemy import text

from cinevec.ingestion.db.build_rag_db import get_engine


# ---------------------------------------------------------------- helpers
def raw_sql(engine, sql: str) -> None:
    """Run arbitrary SQL. SELECTs print rows; other statements are committed."""
    with engine.begin() as conn:
        result = conn.execute(text(sql))
        if result.returns_rows:
            rows = result.mappings().all()
            print(f"-- {len(rows)} row(s)")
            for r in rows:
                print("  ", dict(r))
        else:
            print(f"-- OK ({result.rowcount} row(s) affected)")


if __name__ == "__main__":
    engine = get_engine()

    query = "SELECT * FROM movies LIMIT 5"
    raw_sql(engine, query)
