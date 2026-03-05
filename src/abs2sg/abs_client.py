from __future__ import annotations

import logging
from typing import Any

import requests

from .models import AbsBook, ReadingStatus

LOGGER = logging.getLogger(__name__)


class AbsClient:
    def __init__(self, base_url: str, token: str, verify_tls: bool = True) -> None:
        self._base_url = base_url.rstrip("/")
        self._session = requests.Session()
        self._session.headers.update({"Authorization": f"Bearer {token}"})
        self._verify_tls = verify_tls

    def fetch_books(self, library_id: str | None) -> list[AbsBook]:
        payload = self._fetch_library_items(library_id)
        items = self._extract_items(payload)
        books: list[AbsBook] = []
        for item in items:
            book = self._parse_book(item)
            if book is None:
                continue
            books.append(book)
        LOGGER.info("Fetched %s books from ABS", len(books))
        return books

    def _fetch_library_items(self, library_id: str | None) -> dict[str, Any]:
        candidates: list[str] = []
        if library_id:
            candidates.extend(
                [
                    f"/api/libraries/{library_id}/items?limit=10000",
                    f"/api/libraries/{library_id}/items",
                ]
            )
        candidates.extend(
            [
                "/api/items?limit=10000",
                "/api/items",
            ]
        )

        last_error: Exception | None = None
        for path in candidates:
            try:
                response = self._session.get(
                    f"{self._base_url}{path}",
                    timeout=30,
                    verify=self._verify_tls,
                )
                if response.status_code == 404:
                    continue
                response.raise_for_status()
                LOGGER.info("ABS endpoint selected: %s", path)
                return response.json()
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                LOGGER.warning("ABS endpoint failed (%s): %s", path, exc)
                continue

        raise RuntimeError(f"Could not fetch ABS items from any endpoint: {last_error}")

    def _extract_items(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        for key in ("results", "items", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]
        if isinstance(payload, list):
            return [x for x in payload if isinstance(x, dict)]
        return []

    def _parse_book(self, item: dict[str, Any]) -> AbsBook | None:
        abs_id = str(item.get("id") or "").strip()
        if not abs_id:
            return None

        title = self._extract_title(item)
        if not title:
            return None
        authors = self._extract_authors(item)
        status = self._extract_status(item)
        return AbsBook(abs_id=abs_id, title=title, authors=authors, status=status, raw=item)

    def _extract_title(self, item: dict[str, Any]) -> str:
        metadata = (item.get("media") or {}).get("metadata") or {}
        candidates = [
            metadata.get("title"),
            item.get("title"),
            item.get("name"),
        ]
        for candidate in candidates:
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
        return ""

    def _extract_authors(self, item: dict[str, Any]) -> list[str]:
        metadata = (item.get("media") or {}).get("metadata") or {}
        author_names: list[str] = []
        raw = metadata.get("authorName") or item.get("authorName")
        if isinstance(raw, str):
            author_names.extend(
                [
                    token.strip()
                    for token in raw.replace("&", ",").replace(";", ",").split(",")
                    if token.strip()
                ]
            )
        authors = metadata.get("authors")
        if isinstance(authors, list):
            for author in authors:
                if isinstance(author, dict):
                    name = author.get("name")
                    if isinstance(name, str) and name.strip():
                        author_names.append(name.strip())
                elif isinstance(author, str) and author.strip():
                    author_names.append(author.strip())
        deduped = list(dict.fromkeys(author_names))
        return deduped

    def _extract_status(self, item: dict[str, Any]) -> ReadingStatus:
        progress = self._extract_progress(item)
        if progress is None:
            return ReadingStatus.UNREAD

        if progress.get("is_finished", False):
            return ReadingStatus.FINISHED
        ratio = progress.get("ratio", 0.0)
        if ratio >= 0.98:
            return ReadingStatus.FINISHED
        if ratio <= 0.0:
            return ReadingStatus.UNREAD
        return ReadingStatus.IN_PROGRESS

    def _extract_progress(self, item: dict[str, Any]) -> dict[str, Any] | None:
        progress_sources = [
            item.get("mediaProgress"),
            item.get("userMediaProgress"),
            item.get("progress"),
            (item.get("media") or {}).get("progress"),
        ]
        for source in progress_sources:
            parsed = self._parse_progress(source)
            if parsed is not None:
                return parsed
        return None

    def _parse_progress(self, source: Any) -> dict[str, Any] | None:
        if source is None:
            return None
        if isinstance(source, list):
            for entry in source:
                parsed = self._parse_progress(entry)
                if parsed is not None:
                    return parsed
            return None
        if not isinstance(source, dict):
            return None

        is_finished = bool(source.get("isFinished") or source.get("finished"))
        ratio = 0.0
        for key in ("progress", "percentComplete", "percentage"):
            value = source.get(key)
            if isinstance(value, int | float):
                ratio = max(ratio, float(value))
        current_time = source.get("currentTime") or source.get("position")
        duration = source.get("duration")
        if (
            isinstance(current_time, int | float)
            and isinstance(duration, int | float)
            and duration > 0
        ):
            ratio = max(ratio, float(current_time) / float(duration))

        return {"is_finished": is_finished, "ratio": ratio}
