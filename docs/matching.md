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

Candidate quality is also estimated from search-result metadata:
- positive signals: page count, audiobook duration, multiple editions
- negative signals: `missing page info`, `user-added`, very sparse snippets

## Threshold
- Config: `MATCH_THRESHOLD` (default `0.70`)
- If best score is below threshold, no update is attempted.
- The book is logged to `errors.log` with context for manual review.
- Config: `MATCH_TIE_DELTA` (default `0.04`)
- If multiple candidates are within this similarity window, the higher-quality candidate is chosen.
- Config: `MATCH_MIN_QUALITY` (default `0.0`)
- If chosen candidate quality is below this value, the match is rejected.

## Manual Review Workflow
1. Open `manual_review.log` (and `errors.log` for stack-level failures).
2. Find `no_confident_match` rows.
3. Check `top_ranked` scores in `details` to see rejected/considered candidates.
4. Manually verify StoryGraph book URL.
5. Optionally improve title/author metadata in ABS and rerun.
