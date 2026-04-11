FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock README.md /app/
COPY src /app/src

RUN uv sync --frozen --no-dev

CMD ["uv", "run", "telegram-scraper", "--help"]
