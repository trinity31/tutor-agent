# --- Stage 1: React 빌드 ---
FROM node:20-slim AS frontend
WORKDIR /app/web
COPY web/package*.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

# --- Stage 2: Python 서버 ---
FROM python:3.13-slim
WORKDIR /app

# uv 설치
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# 의존성 설치
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# 소스 복사
COPY tutor_agent/ tutor_agent/
COPY auth_config.yaml ./

# React 빌드 결과 복사
COPY --from=frontend /app/web/dist web/dist/

EXPOSE 8000

CMD uv run uvicorn tutor_agent.platforms.api:app --host 0.0.0.0 --port ${PORT:-8000}
