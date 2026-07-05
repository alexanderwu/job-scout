# Job Scout task runner. Run `just` (or `just --list`) to see all recipes.
#
# These are thin, memorable aliases over the underlying uv/docker commands —
# the same ones CI runs (see .github/workflows/ci.yml), so `just check`
# locally is the same gate a pull request has to pass.

# Show available recipes when run with no arguments.
default:
    @just --list

# Create/update the virtualenv with the pinned Python and all dependencies.
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

# Run the test suite.
test *args:
    uv run pytest {{ args }}

# Format code in place.
fmt:
    uv run ruff format .

# Lint, auto-fixing what can be fixed safely.
lint:
    uv run ruff check --fix .

# Static type check (strict).
typecheck:
    uv run mypy

# Run the full CI gate locally: format check, lint, typecheck, tests.
check:
    uv run ruff format --check .
    uv run ruff check .
    uv run mypy
    uv run pytest
