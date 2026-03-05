from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class ProcessedKey:
    abs_id: str
    shelf: str

    @property
    def serial(self) -> str:
        return f"{self.abs_id}|{self.shelf}"


class StateStore:
    def __init__(self, data_dir: Path, processed_log_path: Path, errors_log_path: Path) -> None:
        self._data_dir = data_dir
        self._processed_log_path = processed_log_path
        self._errors_log_path = errors_log_path
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._processed_log_path.touch(exist_ok=True)
        self._errors_log_path.touch(exist_ok=True)
        self._processed = self._load_processed()

    def is_processed(self, abs_id: str, shelf: str) -> bool:
        return ProcessedKey(abs_id=abs_id, shelf=shelf).serial in self._processed

    def append_processed(self, abs_id: str, shelf: str, storygraph_url: str, score: float) -> None:
        payload = {
            "timestamp": _utc_now(),
            "abs_id": abs_id,
            "shelf": shelf,
            "storygraph_url": storygraph_url,
            "match_score": round(score, 4),
        }
        self._append_jsonl(self._processed_log_path, payload)
        self._processed.add(ProcessedKey(abs_id=abs_id, shelf=shelf).serial)

    def append_error(
        self,
        abs_id: str,
        title: str,
        reason: str,
        details: dict | None = None,
    ) -> None:
        payload = {
            "timestamp": _utc_now(),
            "abs_id": abs_id,
            "title": title,
            "reason": reason,
            "details": details or {},
        }
        self._append_jsonl(self._errors_log_path, payload)

    def _load_processed(self) -> set[str]:
        processed: set[str] = set()
        if not self._processed_log_path.exists():
            return processed
        for line in self._processed_log_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
                abs_id = str(payload["abs_id"])
                shelf = str(payload["shelf"])
                processed.add(ProcessedKey(abs_id=abs_id, shelf=shelf).serial)
            except Exception:  # noqa: BLE001
                continue
        return processed

    def _append_jsonl(self, path: Path, payload: dict) -> None:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=True) + "\n")


def _utc_now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()
