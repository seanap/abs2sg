from abs2sg.abs_client import AbsClient
from abs2sg.models import ReadingStatus


def make_client() -> AbsClient:
    return AbsClient("http://abs.example", "token", verify_tls=False)


def test_parse_progress_prefers_current_user_entry() -> None:
    client = make_client()
    client._current_user_id = "user-2"  # noqa: SLF001
    parsed = client._parse_progress(  # noqa: SLF001
        [
            {"userId": "user-1", "progress": 0.1},
            {"userId": "user-2", "isFinished": True, "progress": 0.2},
        ]
    )
    assert parsed is not None
    assert parsed["is_finished"] is True


def test_parse_progress_normalizes_percent_fields() -> None:
    client = make_client()
    parsed = client._parse_progress({"percentComplete": 75})  # noqa: SLF001
    assert parsed is not None
    assert parsed["ratio"] == 0.75


def test_extract_status_uses_user_progress_map() -> None:
    client = make_client()
    client._user_progress_by_item = {"book-1": {"isFinished": True}}  # noqa: SLF001
    status = client._extract_status({"id": "book-1", "media": {}}, "book-1")  # noqa: SLF001
    assert status is ReadingStatus.FINISHED


def test_extract_status_uses_item_detail_fallback() -> None:
    client = make_client()
    client._item_progress_cache = {"book-2": {"mediaProgress": {"progress": 0.55}}}  # noqa: SLF001
    status = client._extract_status({"id": "book-2", "media": {}}, "book-2")  # noqa: SLF001
    assert status is ReadingStatus.IN_PROGRESS


def test_parse_progress_ignores_empty_dict() -> None:
    client = make_client()
    parsed = client._parse_progress({})  # noqa: SLF001
    assert parsed is None


def test_extract_status_skips_empty_progress_and_uses_fallback() -> None:
    client = make_client()
    client._item_progress_cache = {  # noqa: SLF001
        "book-3": {"mediaProgress": {"isFinished": True}}
    }
    status = client._extract_status({"id": "book-3", "mediaProgress": {}}, "book-3")  # noqa: SLF001
    assert status is ReadingStatus.FINISHED
