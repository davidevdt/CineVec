import argparse

from cinevec.logging import logger
from cinevec.data_loader import load_and_store_data
from cinevec.db.build_rag_db import get_engine, create_schema 
from cinevec.db.ingest_rag import ingest 



def main(rebuild: bool=False, sample_n: int=None) -> None:
    logger.info("Starting the ingestion process...")
    df = load_and_store_data(sample_n=sample_n)
    print(df.columns)
    logger.info(f"Data loaded successfully. Number of records: {len(df)}")
    movie_items = df.to_dict(orient="records")
    engine = get_engine()
    logger.info("Creating database schema...")
    create_schema(engine, rebuild=rebuild) 
    logger.info("Database schema created successfully. Starting ingestion (this will take ~5 minutes)...")
    ingest(engine, movie_items) 
    logger.info("Ingestion process completed successfully.")

if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument("--rebuild", 
                        action="store_true",
                        help="drop and recreate all tables before ingesting"
    )
    parser.add_argument("--sample-n", 
                    type=int, 
                    default=None,
                    help="ingest only a random sample of N movies (default: all)"
    )
    args = parser.parse_args() 

    main(rebuild=args.rebuild, sample_n=args.sample_n)
