FROM python:3.13-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src ./src

# Bust cache on every deploy so new tool files are always picked up
ARG CACHEBUST=1

RUN pip install --no-cache-dir .

ENV PYTHONUNBUFFERED=1
ENV PORT=8000
EXPOSE 8000

CMD ["sh", "-c", "uvicorn paprika_mcp.server_http:asgi_app --host 0.0.0.0 --port ${PORT:-8000}"]
