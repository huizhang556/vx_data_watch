ARG NODE_IMAGE=node:24-alpine
ARG PYTHON_IMAGE=python:3.12-slim
ARG APP_VERSION=0.3.2

FROM ${NODE_IMAGE} AS frontend-build
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM ${PYTHON_IMAGE} AS runtime
ARG APP_VERSION
LABEL org.opencontainers.image.title="VX Data Watch" \
      org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.source="https://github.com/huizhang556/vx_data_watch"
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend \
    VX_DATA_DIR=/app/data \
    VX_DATABASE_URL=sqlite:////app/data/vx_data.db \
    VX_COOKIE_SECURE=false
WORKDIR /app
RUN sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 curl \
    && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml ./
COPY backend/ ./backend/
COPY alembic.ini ./
COPY --from=frontend-build /build/frontend/dist ./frontend/dist
RUN --mount=type=cache,target=/root/.cache/pip \
    python -m pip install ".[ocr]" \
    && useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/data \
    && chown -R appuser:appuser /app
USER appuser
VOLUME ["/app/data"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/api/health || exit 1
CMD ["uvicorn", "app.main:app", "--app-dir", "backend", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
