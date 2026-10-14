FROM node:22-bookworm-slim AS web
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN --mount=type=secret,id=rg_ca \
    if [ -f /run/secrets/rg_ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/rg_ca; fi; npm ci
COPY frontend/ ./
ENV VITE_DEPLOYMENT_MODE=staging
RUN npm run build

FROM python:3.12-slim-bookworm AS app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY backend/requirements.txt ./requirements.txt
RUN --mount=type=secret,id=rg_ca \
    if [ -f /run/secrets/rg_ca ]; then export PIP_CERT=/run/secrets/rg_ca; fi; \
    pip install --no-cache-dir --require-hashes -r requirements.txt
RUN groupadd --gid 10001 rg && useradd --uid 10001 --gid rg --no-create-home rg \
    && mkdir -p /workspace/dhruva/data && chown -R rg:rg /workspace/dhruva/data
COPY --chown=rg:rg backend/app ./app
COPY --from=web --chown=rg:rg /build/dist ./web
ENV RG_WEB_DIR=/app/web RG_DATA_DIR=/workspace/dhruva/data
USER rg
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-proxy-headers"]
