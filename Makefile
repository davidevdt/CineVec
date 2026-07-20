# Start the stack and follow the app log, so ingestion progress is visible.
up:
	docker compose up -d
	docker compose logs -f app

down:
	docker compose down

logs:
	docker compose logs -f app

# Force the next start to re-download the dataset CSV.
reset-csv:
	docker compose exec app rm -f /app/data/top10K-TMDB-movies.csv

grafana:
	@echo "Grafana: http://localhost:$${GRAFANA_HOST_PORT:-3000}"
	docker compose logs -f grafana

# The last 10 recorded questions.
monitoring-tail:
	docker compose exec db psql -U $${POSTGRES_USER} -d $${POSTGRES_DB} -c \
	  "SELECT id, left(question, 40) AS question, total_tokens, \
	   round(cost::numeric, 5) AS cost, tools_used, timestamp \
	   FROM conversations ORDER BY id DESC LIMIT 10;"

# Wipe monitoring history. The movies table is untouched.
reset-monitoring:
	docker compose exec db psql -U $${POSTGRES_USER} -d $${POSTGRES_DB} -c \
	  "TRUNCATE feedback, conversations RESTART IDENTITY;"

# ---------------------------------------------------------------- code quality
# ruff does both jobs (check = lint, format = formatter); mypy adds the type
# checking neither of them does.
format:
	uv run ruff format .
	uv run ruff check . --fix

lint:
	uv run ruff format --check .
	uv run ruff check .

typecheck:
	uv run mypy cinevec app.py

# What CI runs.
check: lint typecheck

.PHONY: up down logs reset-csv grafana monitoring-tail reset-monitoring \
        format lint typecheck check
