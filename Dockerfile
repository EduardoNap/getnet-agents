FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    FASTEMBED_CACHE_PATH=/app/.cache/fastembed \
    ANONYMIZED_TELEMETRY=False \
    STATE_DIR=/app/state

WORKDIR /app

# Dependencies first, so code changes do not reinstall them.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Run as an unprivileged user. /app/state holds the database and the demo keys; compose mounts a volume there.
RUN useradd --create-home app && mkdir /app/state && chown app /app /app/state
USER app

COPY --chown=app app ./app
COPY --chown=app data ./data

# Build the vector index from the committed snapshot. This also downloads the
# embedding model into the image, so the container needs no network for retrieval.
RUN python -m app.rag.ingest

COPY --chown=app tests ./tests
COPY --chown=app evals ./evals
COPY --chown=app monitoring ./monitoring
COPY --chown=app pytest.ini .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
