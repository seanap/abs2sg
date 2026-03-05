# Repository Guidelines

## Project Structure & Module Organization
- `src/abs2sg/` core app modules:
  - `abs_client.py` (Audiobookshelf ingestion)
  - `storygraph_client.py` (Playwright browser automation)
  - `matcher.py` (title/author scoring)
  - `state_store.py` (processed/error logs)
  - `sync_engine.py` (orchestration)
- `tests/` unit tests (`test_matcher.py`, `test_state_store.py`)
- `docs/` operational and matching documentation
- `data/` runtime output (`processed_activities.log`, `errors.log`, screenshots), ignored except `data/.gitkeep`
- `.github/workflows/` CI and Docker publish pipelines

## Build, Test, and Development Commands
- `make setup` create `.venv` and install package + dev dependencies
- `make test` run test suite (`pytest`)
- `make lint` run Ruff lint checks
- `make run` run sync locally (`python3 -m abs2sg.main`)
- `make docker-build` build container image
- `make docker-run` run via Docker Compose

For first container run: copy `.env.example` to `.env`, set credentials, and start with `DRY_RUN=true`.

## Coding Style & Naming Conventions
- Python 3.11+, 4-space indentation, type hints for public functions.
- Files and functions use `snake_case`; classes use `PascalCase`.
- Keep modules focused: API client, matching logic, state, and orchestration should remain separated.
- Lint with `ruff check .`; maintain import order and avoid unused code.

## Testing Guidelines
- Framework: `pytest`.
- Add tests for matching logic, state idempotency, and non-network business logic.
- Name tests by behavior (`test_pick_best_candidate_with_threshold`).
- Prefer fast unit tests; avoid live StoryGraph/ABS calls in CI.

## Commit & Pull Request Guidelines
- Use Conventional Commit prefixes: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`.
- Keep commits atomic and scoped to one change concern.
- PRs should include:
  - short problem/solution summary
  - config or env changes
  - test/lint evidence (`make test`, `make lint`)
  - logs/screenshots when automation behavior changes

## Security & Configuration Tips
- Never commit secrets. `.env` is ignored; use `.env.example` as template.
- Keep rate limits conservative (`REQUEST_DELAY_MS`, `MAX_ACTIONS_PER_RUN`) to avoid hammering StoryGraph.
- Review `errors.log` after each run before increasing automation throughput.
