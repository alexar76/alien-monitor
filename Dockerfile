# Alien Monitor — production image (static UI + FastAPI backend on one port)
FROM node:20-alpine AS frontend
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm install --silent
COPY frontend/ ./
ARG VITE_BASE_PATH=/monitor/
ENV VITE_BASE_PATH=${VITE_BASE_PATH}
RUN npm run build

FROM python:3.12-slim AS runtime
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ALIEN_MODE=real \
    ALIEN_PORT=9100 \
    ALIEN_HOST=127.0.0.1

COPY backend/requirements.txt ./backend/
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/ ./backend/
COPY --from=frontend /build/frontend/dist ./frontend/dist

WORKDIR /app/backend
EXPOSE 9100
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:9100/api/health', timeout=3)"

CMD ["python", "main.py"]
