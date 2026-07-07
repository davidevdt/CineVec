create-pgvector-db:
	docker run -d \
		--name pgvector \
		--env-file .env \
		-v pgvector_data:/var/lib/postgresql/data \
		-p 5432:5432 \
		pgvector/pgvector:pg17

stop-pgvector-db:
	docker stop pgvector
	docker rm pgvector
