FROM node:22.12.0-bookworm-slim AS webbuild

WORKDIR /build
COPY web ./web
COPY tests/js/test_scanner_core.mjs ./tests/js/test_scanner_core.mjs
COPY tests/js/test_scanner_ui.mjs ./tests/js/test_scanner_ui.mjs
WORKDIR /build/web
RUN npm ci && npm run build && node ../tests/js/test_scanner_core.mjs && node ../tests/js/test_scanner_ui.mjs

FROM python:3.12-slim-bookworm

ARG GIT_COMMIT=unknown
LABEL org.opencontainers.image.revision="${GIT_COMMIT}"

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    SCANNER_GIT_COMMIT=${GIT_COMMIT}

COPY pyproject.toml README.md ./
COPY src ./src
COPY --from=webbuild /build/web/dist ./web/dist

RUN pip install --no-cache-dir .

EXPOSE 8020

CMD ["uvicorn", "inventory_scanner.app:app", \
     "--host", "0.0.0.0", "--port", "8020", \
     "--workers", "1", \
     "--log-level", "warning", \
     "--limit-concurrency", "40", \
     "--backlog", "64", \
     "--timeout-keep-alive", "5"]
