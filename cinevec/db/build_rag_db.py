import os 
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from cinevec.db.model_rag import Base
from cinevec.logging import logger
from dotenv import load_dotenv


load_dotenv() 
user = os.getenv("POSTGRES_USER")
password = os.getenv("POSTGRES_PASSWORD")
host = os.getenv("POSTGRES_HOST")
port = os.getenv("POSTGRES_PORT", "5432")
db = os.getenv("POSTGRES_DB", "movies")
DSN = f"postgresql+psycopg://{user}:{password}@{host}:{port}/{db}"


def get_engine(dsn: str = DSN) -> Engine:
    engine = create_engine(dsn)
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.execute(text(
            "CREATE OR REPLACE FUNCTION imm_array_to_string(text[]) "
            "RETURNS text LANGUAGE sql IMMUTABLE AS "
            "$$ SELECT coalesce(array_to_string($1, ' '), '') $$"
        ))
    return engine


def create_schema(engine: Engine, rebuild: bool = False) -> None:

    if rebuild:
        logger.info("Rebuilding schema: dropping existing tables...")
        Base.metadata.drop_all(engine)
        logger.info("Existing tables dropped.")
    Base.metadata.create_all(engine)
    logger.info("Database schema created successfully.")


if __name__ == "__main__": 
    engine = get_engine()
    logger.info("Creating schema...")
    create_schema(engine)
    logger.info("Database schema created successfully.")