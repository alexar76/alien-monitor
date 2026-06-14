# Alien Monitor — production image with UNI mode (embedded Anvil + Foundry deploy).
#
# Build from monorepo root (required for contracts/evm):
#   docker compose -f alien-monitor/docker-compose.prod.yml build
#
FROM node:20-alpine AS frontend
WORKDIR /build/frontend
COPY alien-monitor/frontend/package.json alien-monitor/frontend/package-lock.json ./
RUN npm install --silent
COPY alien-monitor/frontend/ ./
ARG VITE_BASE_PATH=/monitor/
ARG VITE_ALIEN_API_TOKEN=
ENV VITE_BASE_PATH=${VITE_BASE_PATH}
ENV VITE_ALIEN_API_TOKEN=${VITE_ALIEN_API_TOKEN}
RUN npm run build

FROM ghcr.io/foundry-rs/foundry:v1.3.1 AS foundry

FROM python:3.12-slim AS runtime
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates libstdc++6 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=foundry /usr/local/bin/anvil /usr/local/bin/anvil
COPY --from=foundry /usr/local/bin/forge /usr/local/bin/forge
COPY --from=foundry /usr/local/bin/cast /usr/local/bin/cast

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ALIEN_MODE=universe \
    ALIEN_PORT=9100 \
    ALIEN_HOST=127.0.0.1 \
    AICOM_ROOT=/app \
    AICOM_CONTRACTS_EVM_DIR=/app/contracts/evm \
    ALIEN_UNIVERSE_ANVIL_STATE_DIR=/app/data/universe/anvil-state \
    ALIEN_UNIVERSE_AUTO_START=1 \
    PATH="/usr/local/bin:${PATH}"

COPY alien-monitor/backend/requirements.txt ./backend/
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY alien-monitor/backend/ ./backend/
COPY alien-monitor/config/ ./config/
COPY contracts/evm/ ./contracts/evm/
COPY --from=frontend /build/frontend/dist ./frontend/dist

# Warm Foundry artifacts for Escrow/NFT (deploy scripts compile on first bootstrap).
RUN cd /app/contracts/evm && forge build src/

WORKDIR /app/backend
EXPOSE 9100
HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=5 \
  CMD python -c "import json,urllib.request; d=json.loads(urllib.request.urlopen('http://127.0.0.1:9100/api/health',timeout=5).read()); exit(0 if d.get('status')=='ok' and (d.get('mode')!='universe' or d.get('blockchain_ready')) else 1)"

CMD ["python", "main.py"]
