from pathlib import Path

from abs2sg.state_store import StateStore


def test_state_store_processed_roundtrip(tmp_path: Path) -> None:
    store = StateStore(
        data_dir=tmp_path,
        processed_log_path=tmp_path / "processed.log",
        errors_log_path=tmp_path / "errors.log",
        manual_review_log_path=tmp_path / "manual_review.log",
    )
    assert store.is_processed("abc", "to-read") is False
    store.append_processed("abc", "to-read", "https://sg/books/1", 0.93)
    assert store.is_processed("abc", "to-read") is True


def test_state_store_error_log(tmp_path: Path) -> None:
    error_path = tmp_path / "errors.log"
    store = StateStore(
        data_dir=tmp_path,
        processed_log_path=tmp_path / "processed.log",
        errors_log_path=error_path,
        manual_review_log_path=tmp_path / "manual_review.log",
    )
    store.append_error("id-1", "Some Book", "no_match", {"foo": "bar"})
    content = error_path.read_text(encoding="utf-8")
    assert "Some Book" in content
    assert "no_match" in content


def test_state_store_manual_review_log(tmp_path: Path) -> None:
    review_path = tmp_path / "manual_review.log"
    store = StateStore(
        data_dir=tmp_path,
        processed_log_path=tmp_path / "processed.log",
        errors_log_path=tmp_path / "errors.log",
        manual_review_log_path=review_path,
    )
    store.append_manual_review(
        abs_id="id-2",
        title="Hard Match",
        target_shelf="to-read",
        reason="all_candidate_attempts_failed",
        details={"attempted_errors": [{"url": "u1", "error": "bad"}]},
    )
    content = review_path.read_text(encoding="utf-8")
    assert "Hard Match" in content
    assert "all_candidate_attempts_failed" in content
