from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ReadingStatus(str, Enum):
    UNREAD = "unread"
    FINISHED = "finished"
    IN_PROGRESS = "in_progress"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class AbsBook:
    abs_id: str
    title: str
    authors: list[str]
    status: ReadingStatus
    raw: dict[str, Any] = field(repr=False)


@dataclass(frozen=True)
class StoryGraphCandidate:
    url: str
    title: str
    authors: list[str]
    snippet: str = ""


@dataclass(frozen=True)
class PlannedAction:
    book: AbsBook
    target_shelf: str

