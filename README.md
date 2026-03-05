# ABS -> StoryGraph Sync

Dockerized utility to sync Audiobookshelf (ABS) library status into StoryGraph shelves.

## What It Does
- ABS `unread` books -> StoryGraph `To-Read`
- ABS `finished` books -> StoryGraph `Recently Read` (best-effort through StoryGraph UI automation)
- Skips already-processed `(book, shelf)` pairs using a local log ledger
- Writes non-matches and automation failures to an error log for manual review

## Why Playwright
StoryGraph does not expose a public API for this workflow, so this project uses Playwright (Chromium) to automate login, search, and shelf updates.

## Quick Start
1. Copy `.env.example` to `.env` and fill in your ABS + StoryGraph credentials.
2. Set `DRY_RUN=true` for first run.
3. Run:

```bash
docker compose up --build
```

4. Review outputs in `./data`:
- `processed_activities.log`
- `errors.log`
- `run_summary.json`
- `screenshots/` for UI failure captures
- `debug/` for login-page screenshot + HTML dumps when auth fails

## Main Config (`.env`)
- `ABS_URL`, `ABS_TOKEN`, `ABS_LIBRARY_ID`
- `SG_EMAIL`, `SG_PASSWORD`
- `SG_LOGIN_EMAIL_SELECTORS`, `SG_LOGIN_PASSWORD_SELECTORS`, `SG_LOGIN_SUBMIT_SELECTORS`
- `DRY_RUN`, `MAX_ACTIONS_PER_RUN`
- `REQUEST_DELAY_MS`, `REQUEST_JITTER_MS`
- `SG_CHALLENGE_WAIT_SECONDS` (wait time for Cloudflare verification page)
- `SG_LOGIN_MAX_ATTEMPTS`, `SG_LOGIN_RETRY_DELAY_SECONDS`
- `SG_STORAGE_STATE_PATH`, `SG_SAVE_STORAGE_STATE`
- `SG_STORAGE_STATE_B64` (optional base64 Playwright storage_state JSON)
- `SG_COOKIE_HEADER` (optional raw Cookie header copied from browser request)
- `SG_TRY_EXISTING_SESSION_FIRST` (skip direct login when valid session already exists)
- `MATCH_THRESHOLD`
- `SYNC_INTERVAL_MINUTES` (`0` = run once, `>0` = loop)
- `ERROR_RETRY_MINUTES` (retry delay after failed run in loop mode)

## Local Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
playwright install chromium
pytest
ruff check .
python -m abs2sg.main
```

## Docker Hub Publishing
Set repository secrets:
- `DOCKERHUB_USERNAME`
- `DOCKERHUB_TOKEN`

Tag and push:

```bash
git tag v0.1.0
git push origin v0.1.0
```

The `docker-publish.yml` workflow builds and pushes `${DOCKERHUB_USERNAME}/abs2sg` tags.

## Known Limits
- StoryGraph UI selectors can change; override selectors via env vars if needed.
- StoryGraph can present Cloudflare bot checks. The app will wait `SG_CHALLENGE_WAIT_SECONDS` and then log explicit challenge errors plus debug artifacts.
- Matching is heuristic (title + author similarity). Ambiguous books are logged for review.
- Low-quality StoryGraph entries marked as `user-added` / `missing page info` are skipped during matching and blocked again at update time as a safety net.
- `in_progress` ABS books are intentionally skipped in v1.

## Session Import (Cloudflare Workaround)
Fast path (recommended):
1. In Firefox Network tab, copy the full `cookie` request header value from a logged-in StoryGraph request.
2. Set `SG_COOKIE_HEADER=<that value>` in `.env`.

If server-side login is blocked, import a browser-authenticated session:
1. Obtain a Playwright `storage_state.json` from a successful manual browser login.
2. Base64-encode it and set `SG_STORAGE_STATE_B64` in `.env`.
3. Keep `SG_TRY_EXISTING_SESSION_FIRST=true`.

Linux example:
```bash
base64 -w0 storage_state.json
```

Helper script (run on a machine with GUI browser access):
```bash
python scripts/capture_storygraph_state.py --print-b64
```

## Docs
- `docs/architecture.md`
- `docs/matching.md`
- `docs/operations.md`
