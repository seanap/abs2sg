# Matching Strategy

## Inputs
- ABS title
- ABS authors (if available)

## Candidate Discovery
The sync client searches StoryGraph with `"{title} {authors...}"`, then parses the first set of `/books/` links from results.

## Scoring
Candidates are scored with weighted similarity:
- 75% title similarity
- 25% best author similarity

Normalized matching removes punctuation and case differences.

## Threshold
- Config: `MATCH_THRESHOLD` (default `0.70`)
- If best score is below threshold, no update is attempted.
- The book is logged to `errors.log` with context for manual review.

## Manual Review Workflow
1. Open `errors.log`.
2. Find `no_confident_match` rows.
3. Manually verify StoryGraph book URL.
4. Optionally improve title/author metadata in ABS and rerun.

