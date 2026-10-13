# creatorloop MCP server over stdio, no local Python needed.
#   docker build -t creatorloop .
#   docker run -i --rm -v creatorloop:/data creatorloop
# Settings (.env), the database and content folders live in the /data volume (CREATORLOOP_HOME).

FROM ghcr.io/astral-sh/uv:0.9-python3.14-trixie-slim AS build
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src
RUN uv sync --locked --no-dev --no-editable

FROM python:3.14-slim-trixie
# cloudflared exposes images to Instagram for a minute when publishing carousels (Reels don't need it)
ARG CLOUDFLARED_VERSION=2026.10.0
ARG TARGETARCH
ADD --chmod=755 https://github.com/cloudflare/cloudflared/releases/download/${CLOUDFLARED_VERSION}/cloudflared-linux-${TARGETARCH} /usr/local/bin/cloudflared

COPY --from=build /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    CREATORLOOP_HOME=/data
VOLUME /data
ENTRYPOINT ["creatorloop"]
