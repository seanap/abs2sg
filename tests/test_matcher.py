from abs2sg.matcher import (
    is_low_quality_candidate,
    normalize_text,
    pick_best_candidate,
    score_candidate,
)
from abs2sg.models import AbsBook, ReadingStatus, StoryGraphCandidate


def test_normalize_text() -> None:
    assert (
        normalize_text("The Hobbit: An Unexpected Journey!")
        == "the hobbit an unexpected journey"
    )


def test_score_candidate_prefers_title_and_author() -> None:
    book = AbsBook(
        abs_id="1",
        title="Project Hail Mary",
        authors=["Andy Weir"],
        status=ReadingStatus.UNREAD,
        raw={},
    )
    good = StoryGraphCandidate(
        url="https://example.com/books/1",
        title="Project Hail Mary",
        authors=["Andy Weir"],
    )
    bad = StoryGraphCandidate(
        url="https://example.com/books/2",
        title="The Martian",
        authors=["Andy Weir"],
    )

    assert score_candidate(book, good) > score_candidate(book, bad)


def test_pick_best_candidate_with_threshold() -> None:
    book = AbsBook(
        abs_id="2",
        title="Dune",
        authors=["Frank Herbert"],
        status=ReadingStatus.FINISHED,
        raw={},
    )
    candidates = [
        StoryGraphCandidate(url="u1", title="Dune", authors=["Frank Herbert"]),
        StoryGraphCandidate(url="u2", title="Dune Messiah", authors=["Frank Herbert"]),
    ]
    best, score = pick_best_candidate(book, candidates, threshold=0.7)
    assert best is not None
    assert best.url == "u1"
    assert score >= 0.7


def test_low_quality_candidate_detection() -> None:
    low_quality = StoryGraphCandidate(
        url="u1",
        title="Any Book",
        authors=["Any Author"],
        snippet="Any Book\nAny Author\nmissing page info • user-added",
    )
    assert is_low_quality_candidate(low_quality)


def test_pick_best_candidate_skips_low_quality_results() -> None:
    book = AbsBook(
        abs_id="3",
        title="The Hobbit",
        authors=["J.R.R. Tolkien"],
        status=ReadingStatus.UNREAD,
        raw={},
    )
    candidates = [
        StoryGraphCandidate(
            url="bad",
            title="The Hobbit",
            authors=["J.R.R. Tolkien"],
            snippet="The Hobbit\nJ.R.R. Tolkien\nmissing page info • user-added",
        ),
        StoryGraphCandidate(
            url="good",
            title="The Hobbit",
            authors=["J.R.R. Tolkien"],
            snippet="The Hobbit\nJ.R.R. Tolkien\n320 pages",
        ),
    ]
    best, _ = pick_best_candidate(book, candidates, threshold=0.7)
    assert best is not None
    assert best.url == "good"
