from cinevec.logging import logger
from cinevec.ingestion.data_loader import load_and_store_data
from cinevec.ingestion.db.build_rag_db import get_engine, create_schema 
from cinevec.ingestion.db.ingest_rag import ingest 
from cinevec.ingestion.db.query_db import query_db
from cinevec.utils.file_utils import load_config_file


def orchestrate_ingestion(rebuild: bool=False, sample_n: int=None) -> None:
    logger.info("Starting the ingestion process...")
    config = load_config_file()
    df = load_and_store_data(config, sample_n=sample_n)
    logger.info(f"Data loaded successfully. Number of records: {len(df)}")
    movie_items = df.to_dict(orient="records")
    engine = get_engine()
    logger.info("Creating database schema...")
    create_schema(engine, rebuild=rebuild) 
    logger.info("Database schema created successfully. Starting ingestion (this might take take up to ~5 minutes)...")
    ingest(engine, movie_items, config)
    logger.info("Ingestion process completed successfully.")

    logger.info(f"Number of rows in the movies table:")
    query_db(engine, "SELECT COUNT(*) FROM movies")