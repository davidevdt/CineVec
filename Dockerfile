FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# Deps first, so editing the app code does not invalidate this layer.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project


FROM python:3.13-slim-bookworm

# onnxruntime needs the OpenMP runtime library.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

COPY cinevec/ ./cinevec/
COPY config/ ./config/
COPY static/ ./static/
COPY app.py ./

RUN mkdir -p data models

EXPOSE 8000

# --host 0.0.0.0: the default 127.0.0.1 only accepts connections from inside
# the container, which makes the published port look broken.
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
