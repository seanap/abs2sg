from __future__ import annotations

import re
from difflib import SequenceMatcher

from .models import AbsBook, StoryGraphCandidate


def normalize_text(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9\s]", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value


def similarity(left: str, right: str) -> float:
    left_norm = normalize_text(left)
    right_norm = normalize_text(right)
    if not left_norm or not right_norm:
        return 0.0
    return SequenceMatcher(a=left_norm, b=right_norm).ratio()


def score_candidate(book: AbsBook, candidate: StoryGraphCandidate) -> float:
    title_score = similarity(book.title, candidate.title)

    if not book.authors or not candidate.authors:
        return title_score

    author_score = max(
        similarity(book_author, candidate_author)
        for book_author in book.authors
        for candidate_author in candidate.authors
    )
    return (0.75 * title_score) + (0.25 * author_score)


def pick_best_candidate(
    book: AbsBook,
    candidates: list[StoryGraphCandidate],
    threshold: float,
) -> tuple[StoryGraphCandidate | None, float]:
    if not candidates:
        return None, 0.0

    best = max(candidates, key=lambda candidate: score_candidate(book, candidate))
    score = score_candidate(book, best)
    if score < threshold:
        return None, score
    return best, score

