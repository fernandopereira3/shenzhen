FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim

# Chromium + chromedriver do sistema pro bot do Braga (Selenium)
RUN apt-get update \
    && apt-get install -y --no-install-recommends chromium chromium-driver \
    && rm -rf /var/lib/apt/lists/*

ENV CHROME_BIN=/usr/bin/chromium \
    CHROMEDRIVER_PATH=/usr/bin/chromedriver \
    DB_DIR=/data \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app
RUN mkdir -p /data
COPY pyproject.toml uv.lock ./
RUN uv venv /app/.venv && uv sync --frozen --no-dev --no-install-project
COPY . .

VOLUME /data
EXPOSE 8000

# runserver (não gunicorn): o agendador roda em thread e só sobe com runserver (main/apps.py)
CMD ["sh", "-c", "for db in default braga news_ fucador; do python manage.py migrate --database $db; done && exec python manage.py runserver 0.0.0.0:8000 --noreload"]
