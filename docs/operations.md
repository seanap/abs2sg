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

If logs indicate Cloudflare challenge pages (`Just a moment...` or `cf-turnstile-response`):
1. Increase `SG_CHALLENGE_WAIT_SECONDS` (for example `180`).
2. Increase retries: `SG_LOGIN_MAX_ATTEMPTS=5` and `SG_LOGIN_RETRY_DELAY_SECONDS=45`.
3. Keep runs low-frequency and avoid burst redeploy loops.
4. Review `/data/debug/*.html` and `/data/debug/*.png` for challenge details.

Use persisted browser state to improve repeated runs:
- `SG_STORAGE_STATE_PATH=/data/storygraph_storage_state.json`
- `SG_SAVE_STORAGE_STATE=true`
- `SG_TRY_EXISTING_SESSION_FIRST=true`

Optional import via env (when file copy is inconvenient):
- `SG_STORAGE_STATE_B64=<base64_of_storage_state_json>`

If a run fails in loop mode, retry cadence is controlled by:
- `ERROR_RETRY_MINUTES` (defaults to `15`, not full daily interval)
