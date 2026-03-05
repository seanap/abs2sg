from __future__ import annotations

from collections import Counter
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
        self._current_user_id: str | None = None
        self._user_progress_by_item: dict[str, Any] = {}
        self._item_progress_cache: dict[str, dict[str, Any] | None] = {}

    def fetch_books(self, library_id: str | None) -> list[AbsBook]:
        self._current_user_id = None
        self._user_progress_by_item = {}
        self._item_progress_cache = {}
        self._load_user_context()

        payload = self._fetch_library_items(library_id)
        items = self._extract_items(payload)
        books: list[AbsBook] = []
        for item in items:
            book = self._parse_book(item)
            if book is None:
                continue
            books.append(book)
        status_counts = Counter(book.status.value for book in books)
        LOGGER.info(
            "ABS status distribution: unread=%s finished=%s in_progress=%s unknown=%s",
            status_counts.get(ReadingStatus.UNREAD.value, 0),
            status_counts.get(ReadingStatus.FINISHED.value, 0),
            status_counts.get(ReadingStatus.IN_PROGRESS.value, 0),
            status_counts.get(ReadingStatus.UNKNOWN.value, 0),
        )
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
        status = self._extract_status(item, abs_id)
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

    def _extract_status(self, item: dict[str, Any], abs_id: str) -> ReadingStatus:
        progress = self._extract_progress(item, abs_id=abs_id)
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

    def _extract_progress(
        self,
        item: dict[str, Any],
        *,
        abs_id: str,
        allow_detail_lookup: bool = True,
    ) -> dict[str, Any] | None:
        progress_sources = self._collect_progress_sources(item)
        mapped = self._user_progress_by_item.get(abs_id)
        if mapped is not None:
            progress_sources.insert(0, mapped)

        for source in progress_sources:
            parsed = self._parse_progress(source)
            if parsed is not None:
                return parsed

        if allow_detail_lookup:
            detail_payload = self._fetch_item_detail(abs_id)
            if detail_payload is not None:
                detail_progress = self._extract_progress(
                    detail_payload,
                    abs_id=abs_id,
                    allow_detail_lookup=False,
                )
                if detail_progress is not None:
                    return detail_progress
        return None

    def _parse_progress(self, source: Any) -> dict[str, Any] | None:
        if source is None:
            return None
        if isinstance(source, list):
            return self._parse_progress_list(source)
        if not isinstance(source, dict):
            return None

        is_finished = bool(
            source.get("isFinished")
            or source.get("finished")
            or source.get("isRead")
            or source.get("read")
        )
        ratio = 0.0
        for key in (
            "progress",
            "progressPct",
            "percentComplete",
            "percentage",
            "completionPercentage",
            "progressPercent",
        ):
            value = source.get(key)
            as_float = self._as_float(value)
            if as_float is None:
                continue
            ratio = max(ratio, as_float)
        current_time = source.get("currentTime") or source.get("position")
        duration = source.get("duration")
        if isinstance(current_time, int | float | str) and isinstance(duration, int | float | str):
            current_time_float = self._as_float(current_time)
            duration_float = self._as_float(duration)
            if (
                current_time_float is not None
                and duration_float is not None
                and duration_float > 0
            ):
                ratio = max(ratio, current_time_float / duration_float)

        if ratio > 1.0:
            if ratio <= 100.0:
                ratio = ratio / 100.0
            else:
                ratio = 1.0

        ratio = max(0.0, min(1.0, ratio))
        return {"is_finished": is_finished, "ratio": ratio}

    def _parse_progress_list(self, source: list[Any]) -> dict[str, Any] | None:
        parsed_entries: list[tuple[int, float, dict[str, Any]]] = []
        for entry in source:
            parsed = self._parse_progress(entry)
            if parsed is None:
                continue
            match_rank = 0
            if isinstance(entry, dict):
                entry_user_id = self._extract_user_id(entry)
                if (
                    self._current_user_id
                    and entry_user_id
                    and entry_user_id == self._current_user_id
                ):
                    match_rank = 1
            parsed_entries.append((match_rank, parsed.get("ratio", 0.0), parsed))

        if not parsed_entries:
            return None

        parsed_entries.sort(
            key=lambda row: (
                row[0],  # prefer entries for current user
                1 if row[2].get("is_finished", False) else 0,
                row[1],  # then highest ratio
            ),
            reverse=True,
        )
        return parsed_entries[0][2]

    def _load_user_context(self) -> None:
        candidates = ["/api/me", "/api/users/me"]
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
                payload = response.json()
                user, progress_entries = self._extract_user_context(payload)
                if user is not None:
                    self._current_user_id = user
                if progress_entries:
                    self._user_progress_by_item = progress_entries
                LOGGER.info(
                    "Loaded ABS user context via %s (user_id=%s, progress_entries=%s)",
                    path,
                    self._current_user_id or "unknown",
                    len(self._user_progress_by_item),
                )
                return
            except Exception as exc:  # noqa: BLE001
                LOGGER.debug("ABS user context endpoint failed (%s): %s", path, exc)
                continue

    def _extract_user_context(self, payload: Any) -> tuple[str | None, dict[str, Any]]:
        if not isinstance(payload, dict):
            return None, {}

        roots = [payload]
        for key in ("user", "data", "result"):
            nested = payload.get(key)
            if isinstance(nested, dict):
                roots.append(nested)

        user_id: str | None = None
        progress_map: dict[str, Any] = {}

        for root in roots:
            maybe_user = root.get("id")
            if user_id is None and maybe_user is not None:
                user_id = str(maybe_user)

            for key in ("mediaProgress", "userMediaProgress", "progress"):
                entries = root.get(key)
                if not isinstance(entries, list):
                    continue
                for entry in entries:
                    if not isinstance(entry, dict):
                        continue
                    item_id = self._extract_item_id(entry)
                    if not item_id:
                        continue
                    progress_map[item_id] = entry

        return user_id, progress_map

    def _collect_progress_sources(self, item: dict[str, Any]) -> list[Any]:
        sources = [
            item.get("mediaProgress"),
            item.get("userMediaProgress"),
            item.get("progress"),
            (item.get("media") or {}).get("progress"),
        ]
        for key in ("libraryItem", "item", "data"):
            nested = item.get(key)
            if isinstance(nested, dict):
                sources.extend(
                    [
                        nested.get("mediaProgress"),
                        nested.get("userMediaProgress"),
                        nested.get("progress"),
                        (nested.get("media") or {}).get("progress"),
                    ]
                )
        return sources

    def _fetch_item_detail(self, abs_id: str) -> dict[str, Any] | None:
        if abs_id in self._item_progress_cache:
            return self._item_progress_cache[abs_id]

        candidates = [
            f"/api/items/{abs_id}?expanded=1&include=progress",
            f"/api/items/{abs_id}?include=progress",
            f"/api/items/{abs_id}?expanded=1",
            f"/api/items/{abs_id}",
        ]
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
                payload = response.json()
                if isinstance(payload, dict):
                    self._item_progress_cache[abs_id] = payload
                    return payload
            except Exception:  # noqa: BLE001
                continue

        self._item_progress_cache[abs_id] = None
        return None

    def _extract_item_id(self, payload: dict[str, Any]) -> str:
        candidates = [
            payload.get("libraryItemId"),
            payload.get("libraryItemID"),
            payload.get("itemId"),
            payload.get("itemID"),
            payload.get("mediaItemId"),
            payload.get("bookId"),
        ]
        library_item = payload.get("libraryItem")
        if isinstance(library_item, dict):
            candidates.append(library_item.get("id"))
        for value in candidates:
            if value is None:
                continue
            token = str(value).strip()
            if token:
                return token
        return ""

    def _extract_user_id(self, payload: dict[str, Any]) -> str:
        candidates = [
            payload.get("userId"),
            payload.get("userID"),
            payload.get("userid"),
        ]
        user = payload.get("user")
        if isinstance(user, dict):
            candidates.append(user.get("id"))
        for value in candidates:
            if value is None:
                continue
            token = str(value).strip()
            if token:
                return token
        return ""

    def _as_float(self, value: Any) -> float | None:
        if isinstance(value, int | float):
            return float(value)
        if isinstance(value, str):
            token = value.strip().replace("%", "")
            if not token:
                return None
            try:
                return float(token)
            except Exception:  # noqa: BLE001
                return None
        return None
