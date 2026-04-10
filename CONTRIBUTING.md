# Contributing

Bug reports, feature ideas, and pull requests are all welcome.

## Local Development

```bash
# Requirements: Python 3.12+, Node.js 20+, uv, pnpm, ffmpeg

# Install dependencies
uv sync
cd frontend && pnpm install && cd ..

# Initialize the database
uv run alembic upgrade head

# Start the backend (terminal 1)
uv run uvicorn server.app:app --reload --port 1241

# Start the frontend (terminal 2)
cd frontend && pnpm dev

# Open http://localhost:5173
```

## Run Tests

```bash
# Backend tests
python -m pytest

# Frontend typecheck + tests
cd frontend && pnpm check
```

## Code Quality

**Lint & format (ruff):**

```bash
uv run ruff check . && uv run ruff format .
```

- Enabled rule sets: `E`, `F`, `I`, `UP`
- Ignored rules: `E402`, `E501`
- Line length: `120`
- CI enforcement: `ruff check . && ruff format --check .`

**Test coverage:**

- CI target: at least `80%`
- `asyncio_mode = "auto"` so async tests do not need manual markers

## Commit Messages

Use the [Conventional Commits](https://www.conventionalcommits.org/) format:

```text
feat: describe a new feature
fix: describe a bug fix
refactor: describe a refactor
docs: describe a docs change
chore: describe a build/tooling change
```
