from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import NamedTuple

from .models import AbsBook, StoryGraphCandidate


def normalize_text(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9\s]", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


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


def is_low_quality_candidate(candidate: StoryGraphCandidate) -> bool:
    snippet = candidate.snippet.lower()
    if "missing page info" in snippet:
        return True
    if "user-added" in snippet or "user added" in snippet:
        return True
    return False


def candidate_quality_score(candidate: StoryGraphCandidate) -> float:
    snippet = candidate.snippet.lower()
    score = 0.0

    if re.search(r"\b\d+\s*pages?\b", snippet):
        score += 0.35
    if re.search(r"\b\d+\s*h(\s*\d+\s*m)?\b", snippet):
        score += 0.30

    editions_match = re.search(r"\b(\d+)\s*editions?\b", snippet)
    if editions_match:
        editions = int(editions_match.group(1))
        if editions <= 1:
            score -= 0.10
        else:
            score += min(editions, 5) * 0.04

    if "no description" in snippet:
        score -= 0.30
    if "missing page info" in snippet:
        score -= 0.45
    if "user-added" in snippet or "user added" in snippet:
        score -= 0.45
    if "digital" in snippet and "pages" not in snippet:
        score -= 0.05

    return max(-1.0, min(1.0, score))


class RankedCandidate(NamedTuple):
    candidate: StoryGraphCandidate
    similarity: float
    quality: float


def rank_candidates(book: AbsBook, candidates: list[StoryGraphCandidate]) -> list[RankedCandidate]:
    ranked = [
        RankedCandidate(
            candidate=candidate,
            similarity=score_candidate(book, candidate),
            quality=candidate_quality_score(candidate),
        )
        for candidate in candidates
        if not is_low_quality_candidate(candidate)
    ]
    ranked.sort(key=lambda item: (item.similarity, item.quality), reverse=True)
    return ranked


def pick_best_candidate(
    book: AbsBook,
    candidates: list[StoryGraphCandidate],
    threshold: float,
    tie_delta: float = 0.04,
    min_quality: float = 0.0,
) -> tuple[StoryGraphCandidate | None, float]:
    if not candidates:
        return None, 0.0

    ranked = rank_candidates(book, candidates)
    if not ranked:
        best_low_quality = max(candidates, key=lambda candidate: score_candidate(book, candidate))
        return None, score_candidate(book, best_low_quality)

    best_similarity = ranked[0].similarity
    if best_similarity < threshold:
        return None, best_similarity

    delta = max(tie_delta, 0.0)
    contenders = [
        item
        for item in ranked
        if item.similarity >= max(threshold, best_similarity - delta)
    ]
    chosen = max(contenders, key=lambda item: (item.quality, item.similarity))

    if chosen.quality < min_quality:
        return None, chosen.similarity
    return chosen.candidate, chosen.similarity
