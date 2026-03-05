# Architecture Overview

## Flow
1. Pull books from ABS API.
2. Classify status (`unread`, `finished`, `in_progress`).
3. Convert status into target shelf:
- `unread` -> `to-read`
- `finished` -> `recently-read`
4. Skip entries already present in `processed_activities.log`.
5. Search StoryGraph and score candidates.
6. Apply shelf action via Playwright.
7. Write outcomes:
- success -> `processed_activities.log`
- failure/no-match -> `errors.log`
- run metrics -> `run_summary.json`

## Components
- `AbsClient`: ABS endpoint calls and payload normalization.
- `StoryGraphClient`: login, search, shelf clicks, screenshot capture.
- `matcher`: title/author similarity scoring.
- `StateStore`: JSONL append-only ledger + error tracking.
- `SyncEngine`: orchestration, limits, dry-run behavior.

## Safety Controls
- Delay + jitter between StoryGraph interactions.
- Max actions per run.
- Append-only idempotency ledger prevents repeated updates.
- Dry-run mode for validation before write operations.

