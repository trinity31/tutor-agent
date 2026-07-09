# --- Stage 1: React 빌드 ---
FROM node:20-slim AS frontend
WORKDIR /app/web
COPY web/package*.json ./
RUN npm ci
COPY web/ ./
# PostHog 계측은 빌드타임 변수 — Railway 서비스 변수를 빌드 ARG로 주입해야
# 번들에 포함된다 (미설정 시 계측 비활성). phc_ 키는 공개 키라 노출 무방.
ARG VITE_POSTHOG_KEY=""
ARG VITE_POSTHOG_HOST=""
ENV VITE_POSTHOG_KEY=$VITE_POSTHOG_KEY \
    VITE_POSTHOG_HOST=$VITE_POSTHOG_HOST
RUN npm run build

# --- Stage 2: Python 서버 ---
FROM python:3.13-slim
WORKDIR /app

# ffmpeg — 낭독 오디오 MP3 인코딩용 (없으면 WAV 폴백, 용량 6배)
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# uv 설치
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# 의존성 설치
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# 소스 복사
COPY tutor_agent/ tutor_agent/
COPY auth_config.yaml ./
# 온보딩 샘플 자산(가입 시 샘플 클래스 시딩용 PDF + 사전생성 오디오)
COPY seeds/ seeds/

# React 빌드 결과 복사
COPY --from=frontend /app/web/dist web/dist/

EXPOSE 8000

CMD uv run uvicorn tutor_agent.platforms.api:app --host 0.0.0.0 --port ${PORT:-8000}
