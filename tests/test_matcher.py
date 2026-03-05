from abs2sg.matcher import (
    candidate_quality_score,
    canonical_title,
    is_low_quality_candidate,
    normalize_text,
    pick_best_candidate,
    rank_candidates,
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


def test_candidate_quality_score_prefers_richer_metadata() -> None:
    rich = StoryGraphCandidate(
        url="rich",
        title="Example",
        authors=["Author"],
        snippet="Example\nAuthor\n384 pages • digital • 2020 • 4 editions",
    )
    poor = StoryGraphCandidate(
        url="poor",
        title="Example",
        authors=["Author"],
        snippet="Example\nAuthor\nmissing page info • digital • 1 edition",
    )
    assert candidate_quality_score(rich) > candidate_quality_score(poor)


def test_pick_best_candidate_prefers_better_quality_on_near_tie() -> None:
    book = AbsBook(
        abs_id="4",
        title="Example Book",
        authors=["Some Author"],
        status=ReadingStatus.UNREAD,
        raw={},
    )
    candidates = [
        StoryGraphCandidate(
            url="thin",
            title="Example Book",
            authors=["Some Author"],
            snippet="Example Book\nSome Author\n1 edition • digital",
        ),
        StoryGraphCandidate(
            url="rich",
            title="Example Book",
            authors=["Some Author"],
            snippet="Example Book\nSome Author\n412 pages • digital • 5 editions",
        ),
    ]
    best, score = pick_best_candidate(
        book,
        candidates,
        threshold=0.7,
        tie_delta=0.05,
        min_quality=0.0,
    )
    assert best is not None
    assert best.url == "rich"
    assert score >= 0.7


def test_rank_candidates_orders_by_similarity_then_quality() -> None:
    book = AbsBook(
        abs_id="5",
        title="Focused Work",
        authors=["Alex Writer"],
        status=ReadingStatus.UNREAD,
        raw={},
    )
    candidates = [
        StoryGraphCandidate(
            url="a",
            title="Focused Work",
            authors=["Alex Writer"],
            snippet="Focused Work\nAlex Writer\n1 edition • digital",
        ),
        StoryGraphCandidate(
            url="b",
            title="Focused Work",
            authors=["Alex Writer"],
            snippet="Focused Work\nAlex Writer\n320 pages • 3 editions",
        ),
    ]
    ranked = rank_candidates(book, candidates)
    assert ranked
    assert ranked[0].candidate.url == "b"


def test_canonical_title_strips_series_and_subtitle() -> None:
    assert canonical_title("The Psychology of Money: Timeless Lessons") == "the psychology of money"
    assert canonical_title("Primal Hunter 4") == "primal hunter 4"
    assert canonical_title("Omega Rising, Book 1") == "omega rising"


def test_score_candidate_prefers_subtitle_variant_of_same_book() -> None:
    book = AbsBook(
        abs_id="6",
        title="The Psychology of Money",
        authors=["Morgan Housel"],
        status=ReadingStatus.UNREAD,
        raw={},
    )
    candidate = StoryGraphCandidate(
        url="u1",
        title="The Psychology of Money: Timeless Lessons on Wealth, Greed, and Happiness",
        authors=["Morgan Housel"],
        snippet="256 pages • paperback • 2020 • 84 editions",
    )
    assert score_candidate(book, candidate) >= 0.80


def test_pick_best_candidate_allows_exact_title_when_quality_is_slightly_negative() -> None:
    book = AbsBook(
        abs_id="7",
        title="Tower of Jack",
        authors=["Sean O."],
        status=ReadingStatus.UNREAD,
        raw={},
    )
    candidates = [
        StoryGraphCandidate(
            url="u1",
            title="Tower of Jack",
            authors=["Sean O."],
            snippet="missing duration info • audio • 1 edition",
        )
    ]
    best, score = pick_best_candidate(book, candidates, threshold=0.7, min_quality=0.0)
    assert best is not None
    assert best.url == "u1"
    assert score >= 0.7


def test_pick_best_candidate_rejects_study_guides_even_with_name_overlap() -> None:
    book = AbsBook(
        abs_id="8",
        title="Never Flinch",
        authors=["Stephen King"],
        status=ReadingStatus.UNREAD,
        raw={},
    )
    candidates = [
        StoryGraphCandidate(
            url="guide",
            title="Study Guide: Never Flinch by Stephen King",
            authors=["Unknown"],
            snippet="43 pages • paperback • 1 edition",
        )
    ]
    best, _ = pick_best_candidate(book, candidates, threshold=0.3, min_quality=-0.2)
    assert best is None
