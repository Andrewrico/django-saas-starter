# syntax=docker/dockerfile:1
FROM python:3.12-slim AS builder
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /build
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY requirements/base.txt requirements/base.txt
RUN pip install -r requirements/base.txt

# Litestream (optional SQLite backups, docs/deployment.md), pinned and verified against
# https://github.com/benbjohnson/litestream/releases/download/v0.5.17/checksums.txt
FROM alpine:3.20 AS litestream
ARG TARGETARCH
ARG LITESTREAM_VERSION=0.5.17
ARG LITESTREAM_SHA256_AMD64=cfb371176d164437ae869f8351cfde49bd1804ae71c61923f75c9cba9c9c006d
ARG LITESTREAM_SHA256_ARM64=f8ca4a050095c1efbda2c4365172e61bf9d955ea0d9ac42f448b52e51819baa5
RUN set -eux; \
    # Builders without BuildKit (e.g. Cloud Build's default) don't set TARGETARCH: use the machine type.
    if [ -z "${TARGETARCH:-}" ]; then case "$(uname -m)" in x86_64) TARGETARCH=amd64 ;; aarch64) TARGETARCH=arm64 ;; esac; fi; \
    case "$TARGETARCH" in \
      amd64) arch=x86_64; sum="$LITESTREAM_SHA256_AMD64" ;; \
      arm64) arch=arm64;  sum="$LITESTREAM_SHA256_ARM64" ;; \
      *) echo "unsupported architecture: $TARGETARCH" >&2; exit 1 ;; \
    esac; \
    wget -q -O /tmp/ls.tar.gz "https://github.com/benbjohnson/litestream/releases/download/v${LITESTREAM_VERSION}/litestream-${LITESTREAM_VERSION}-linux-${arch}.tar.gz"; \
    echo "${sum}  /tmp/ls.tar.gz" | sha256sum -c -; \
    tar -xzf /tmp/ls.tar.gz -C /usr/local/bin litestream

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PATH="/opt/venv/bin:$PATH" PORT=8000 \
    DB_PATH=/data/db.sqlite3
RUN groupadd --system app && useradd --system --gid app --home-dir /app --no-create-home app \
    && mkdir -p /data && chown app:app /data
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY --from=litestream /usr/local/bin/litestream /usr/local/bin/litestream
COPY --chown=app:app . .
# Collect static files at build time. The key is a throwaway used only for this step.
RUN DEBUG=false SECRET_KEY=build-only-not-a-secret DJANGO_READ_DOT_ENV_FILE=false \
    python manage.py collectstatic --noinput && chown -R app:app /app/staticfiles \
    && chmod +x /app/scripts/docker-entrypoint.sh
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import os,urllib.request as u; u.urlopen('http://127.0.0.1:%s/healthz' % os.environ.get('PORT','8000'))" || exit 1
# No arguments: gunicorn (under Litestream when LITESTREAM_REPLICA_URL is set). See the script.
ENTRYPOINT ["/app/scripts/docker-entrypoint.sh"]
