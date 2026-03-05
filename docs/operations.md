# Operations Guide

## Safety Defaults
- Run `DRY_RUN=true` before any real sync.
- Keep `MAX_ACTIONS_PER_RUN` low initially (for example `20`).
- Keep `REQUEST_DELAY_MS` >= `2000` to avoid hammering StoryGraph.

## Regular Run

```bash
docker compose up --build
```

## Scheduled Run
Set `SYNC_INTERVAL_MINUTES` to a positive value (for example `1440` for daily):

```env
SYNC_INTERVAL_MINUTES=1440
```

Then run the same compose command; the container loops with sleep intervals.

## Logs and Artifacts
- `processed_activities.log`: JSONL idempotency ledger
- `errors.log`: JSONL error and manual-review queue
- `run_summary.json`: last run metrics
- `screenshots/*.png`: browser capture on failure
- `debug/*.(png|html)`: login debug artifacts when auth selectors fail

## Recovery
If StoryGraph layout changes break automation:
1. Inspect screenshot in `data/screenshots`.
2. Update selector env vars:
- `SG_TO_READ_SELECTOR`
- `SG_RECENTLY_READ_SELECTOR`
 - `SG_LOGIN_EMAIL_SELECTORS`
 - `SG_LOGIN_PASSWORD_SELECTORS`
 - `SG_LOGIN_SUBMIT_SELECTORS`
3. Re-run with `DRY_RUN=true`.
