# Stage 1: build frontend
FROM node:22-slim AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: runtime
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app/backend

# Install Python deps (postgres extra, no dev group)
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --extra postgres --no-dev

# App code and Alembic
COPY backend/app ./app
COPY backend/alembic ./alembic
COPY backend/alembic.ini ./alembic.ini
COPY backend/entrypoint.sh ./entrypoint.sh
RUN chmod +x entrypoint.sh

# Built frontend served by FastAPI in production
# Place alongside backend/ so main.py's ../frontend/dist path resolves correctly
COPY --from=frontend /build/dist /app/frontend/dist

# Speech-to-text disabled by default; set WHISPER_ENABLED=true to enable
# (requires a PVC for the ~1.5 GB model cache)
ENV WHISPER_ENABLED=false

EXPOSE 8000

ENTRYPOINT ["./entrypoint.sh"]
