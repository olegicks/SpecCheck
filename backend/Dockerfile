# syntax=docker/dockerfile:1
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY pyproject.toml ./
COPY app ./app
COPY scripts ./scripts
COPY samples ./samples
RUN pip install . && useradd --create-home --uid 10001 speccheck
USER speccheck

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"
# Secrets come from the environment at runtime (docker compose env_file / platform secrets),
# never from the image.
CMD ["sh", "-c", "uvicorn app.asgi:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers"]
