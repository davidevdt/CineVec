import argparse
from cinevec.ingestion import orchestrate_ingestion
from cinevec.agent.movie_agent import main as agent_main

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

    orchestrate_ingestion(rebuild=args.rebuild, sample_n=args.sample_n)

    agent_main()