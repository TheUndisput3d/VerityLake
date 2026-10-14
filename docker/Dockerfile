# syntax=docker/dockerfile:1.7
FROM python:3.14-slim-bookworm AS runtime
ARG GIT_SHA=development
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1     HOME=/home/app ANONYMIZED_TELEMETRY=False GIT_SHA=${GIT_SHA}
WORKDIR /app
RUN groupadd --gid 10001 app && useradd --uid 10001 --gid app --create-home app
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt && pip check
COPY pyproject.toml README.md /app/
COPY src /app/src
RUN pip install --no-deps .
COPY scripts /app/scripts
COPY eval /app/eval
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3   CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4)"
CMD ["uvicorn", "veritylake.api:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log"]
