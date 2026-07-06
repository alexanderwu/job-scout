# Job Scout task runner. Run `just` (or `just --list`) to see all recipes.
#
# These are thin, memorable aliases over the underlying uv/docker commands —
# the same ones CI runs (see .github/workflows/ci.yml), so `just check`
# locally is the same gate a pull request has to pass.
#
# The Python app lives in backend/, so its recipes carry a
# [working-directory('backend')] attribute. Docker/infra recipes run from
# the repo root, where docker-compose.yml lives.

# Show available recipes when run with no arguments.
default:
    @just --list

# Create/update the virtualenv with the pinned Python and all dependencies.
[working-directory('backend')]
install:
    uv sync

# Start local Postgres (pgvector) + Redis in the background.
up:
    docker compose up -d

# Stop the local services (keeps the Postgres volume / data).
down:
    docker compose down

# Stop the local services AND delete their data volumes (fresh slate).
reset:
    docker compose down --volumes

# Apply any pending database migrations (needs `just up` first).
[working-directory('backend')]
migrate:
    uv run alembic upgrade head

# Create a new migration from model changes; review before committing!
[working-directory('backend')]
makemigration message:
    uv run alembic revision --autogenerate -m "{{ message }}"

# Run ingestion once, in the foreground.
[working-directory('backend')]
ingest:
    uv run jobscout ingest

# Start the background job worker (processes queued ingestion runs).
[working-directory('backend')]
worker:
    uv run rq worker ingest --url "${REDIS_URL:-redis://localhost:6379/0}"

# Start the cron scheduler (enqueues ingestion every INGEST_INTERVAL_MINUTES).
[working-directory('backend')]
cron:
    uv run rq cron jobscout.schedules --url "${REDIS_URL:-redis://localhost:6379/0}"

# Run the test suite.
[working-directory('backend')]
test *args:
    uv run pytest {{ args }}

# Format code in place.
[working-directory('backend')]
fmt:
    uv run ruff format .

# Lint, auto-fixing what can be fixed safely.
[working-directory('backend')]
lint:
    uv run ruff check --fix .

# Static type check (strict).
[working-directory('backend')]
typecheck:
    uv run mypy

# Run the full CI gate locally: format check, lint, typecheck, tests.
[working-directory('backend')]
check:
    uv run ruff format --check .
    uv run ruff check .
    uv run mypy
    uv run pytest
