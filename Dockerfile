# syntax=docker/dockerfile:1.7
# 所有阶段均使用原生 ARM64；不要在 AMD64 模拟器中验收模型性能。
FROM node:26-bookworm-slim AS frontend-build
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim-bookworm AS python-build
ARG TARGETARCH
RUN test "$TARGETARCH" = arm64
ENV VIRTUAL_ENV=/opt/venv PATH=/opt/venv/bin:$PATH \
    HF_HOME=/opt/pte-models/hf TORCH_HOME=/opt/pte-models/torch \
    NLTK_DATA=/opt/pte-models/nltk PTE_MODELS_DIR=/opt/pte-models \
    PTE_OPENPRONOUNCE_MODEL_PATH=/opt/pte-models/openpronounce
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl ffmpeg espeak-ng libgomp1 libsndfile1 && \
    rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY backend/requirements.lock backend/requirements-alignment.lock \
     backend/requirements-pronunciation.lock backend/requirements-llm.lock backend/
COPY backend/pyproject.toml backend/
COPY backend/app/ backend/app/
RUN python -m venv /opt/venv && \
    python -m pip install --no-cache-dir -r backend/requirements.lock \
      -r backend/requirements-alignment.lock \
      -r backend/requirements-pronunciation.lock \
      -r backend/requirements-llm.lock
COPY scripts/prefetch_container_models.py scripts/
# 下载实际调用的两个模型并离线重新加载；构建失败即阻止发布镜像。
RUN python scripts/prefetch_container_models.py prefetch
RUN --network=none HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
    python scripts/prefetch_container_models.py verify

FROM python:3.11-slim-bookworm AS runtime
ARG TARGETARCH
RUN test "$TARGETARCH" = arm64
ENV VIRTUAL_ENV=/opt/venv PATH=/opt/venv/bin:$PATH \
    PYTHONPATH=/app/backend PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    HF_HOME=/opt/pte-models/hf TORCH_HOME=/opt/pte-models/torch \
    NLTK_DATA=/opt/pte-models/nltk PTE_MODELS_DIR=/opt/pte-models \
    PTE_OPENPRONOUNCE_MODEL_PATH=/opt/pte-models/openpronounce \
    HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
    PTE_DATA_DIR=/app/data PTE_LAN_MODE=true \
    ALIGNMENT_PROVIDER=whisperx LLM_PROVIDER=none
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg espeak-ng tesseract-ocr tesseract-ocr-eng libgomp1 libsndfile1 && \
    rm -rf /var/lib/apt/lists/* && mkdir -p /app/data
WORKDIR /app
COPY --from=python-build /opt/venv /opt/venv
COPY --from=python-build /opt/pte-models /opt/pte-models
COPY backend/ backend/
COPY --from=frontend-build /build/frontend/dist frontend/dist/
COPY scripts/prefetch_container_models.py scripts/
EXPOSE 8765
# 探针走本机 TCP，避免把 Basic Auth 密码传进命令行参数或构建层。
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s CMD python -c "import socket; s=socket.create_connection(('127.0.0.1',8765),3); s.close()"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8765", "--workers", "1"]
