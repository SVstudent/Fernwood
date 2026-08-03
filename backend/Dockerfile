# Fernwood backend — portable image (Render / Fly / Railway / Cloud Run).
#
# Two non-obvious things this file exists to get right:
#
#   FONTS. The advertisement's end card is drawn with Pillow, and python:slim
#   ships with NO fonts at all. Pillow silently falls back to a tiny bitmap
#   font, so the brand name and CTA come out microscopic — a broken-looking ad
#   with no error anywhere. fonts-dejavu-core is what app/pipeline/assemble.py
#   looks for on Linux.
#
#   SINGLE WORKER. The SSE run registry is in-process. With >1 worker a browser
#   can connect to a worker that has never heard of its run, and the campaign
#   appears to hang forever. Do not add --workers.
#
# ffmpeg is NOT installed here: imageio-ffmpeg vendors a static binary in its
# wheel, so the cut works with no system package.

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /bin/uv

WORKDIR /app

# Dependencies first so code edits don't invalidate the dependency layer.
# --frozen honours the committed uv.lock: genblaze is young and its signatures
# have moved between patch releases, so a fresh resolve at deploy time is a
# self-inflicted outage.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY app ./app

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8787

# $PORT is injected by the host; 8787 is the local default.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8787}"]
