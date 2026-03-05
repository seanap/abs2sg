from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from .abs_client import AbsClient
from .config import Config
from .matcher import pick_best_candidate
from .models import AbsBook, PlannedAction, ReadingStatus
from .state_store import StateStore
from .storygraph_client import StoryGraphClient, StoryGraphConfig

LOGGER = logging.getLogger(__name__)


@dataclass
class RunStats:
    total_books: int = 0
    planned: int = 0
    skipped_processed: int = 0
    skipped_in_progress: int = 0
    updated: int = 0
    failed: int = 0
    dry_run: bool = False


class SyncEngine:
    def __init__(self, config: Config) -> None:
        self._config = config
        self._abs_client = AbsClient(
            config.abs_url,
            config.abs_token,
            verify_tls=config.abs_verify_tls,
        )
        self._state = StateStore(
            config.data_dir,
            config.processed_log_path,
            config.errors_log_path,
        )

    def run_once(self) -> RunStats:
        started_at = datetime.now(tz=timezone.utc)
        stats = RunStats(dry_run=self._config.dry_run)
        books = self._abs_client.fetch_books(self._config.abs_library_id)
        stats.total_books = len(books)
        actions = self._plan_actions(books, stats)
        stats.planned = len(actions)

        sg_config = StoryGraphConfig(
            base_url=self._config.sg_base_url,
            login_path=self._config.sg_login_path,
            email=self._config.sg_email,
            password=self._config.sg_password,
            headless=self._config.headless,
            search_url_template=self._config.sg_search_url_template,
            login_email_selectors=self._config.sg_login_email_selectors,
            login_password_selectors=self._config.sg_login_password_selectors,
            login_submit_selectors=self._config.sg_login_submit_selectors,
            to_read_selector=self._config.sg_to_read_selector,
            recently_read_selector=self._config.sg_recently_read_selector,
            request_delay_ms=self._config.request_delay_ms,
            request_jitter_ms=self._config.request_jitter_ms,
            challenge_wait_seconds=self._config.sg_challenge_wait_seconds,
            data_dir=str(self._config.data_dir),
        )

        if self._config.dry_run:
            for action in actions:
                LOGGER.info(
                    "DRY_RUN planned: %s (%s) -> %s",
                    action.book.title,
                    action.book.abs_id,
                    action.target_shelf,
                )
            self._write_summary(stats, started_at)
            return stats

        with StoryGraphClient(sg_config) as storygraph:
            for index, action in enumerate(actions, start=1):
                if index > self._config.max_actions_per_run:
                    LOGGER.warning(
                        "Reached MAX_ACTIONS_PER_RUN=%s, stopping",
                        self._config.max_actions_per_run,
                    )
                    break
                self._execute_action(storygraph, action, stats)

        self._write_summary(stats, started_at)
        return stats

    def _plan_actions(self, books: list[AbsBook], stats: RunStats) -> list[PlannedAction]:
        actions: list[PlannedAction] = []
        for book in books:
            shelf = self._target_shelf(book.status)
            if shelf is None:
                stats.skipped_in_progress += 1
                continue
            if self._state.is_processed(book.abs_id, shelf):
                stats.skipped_processed += 1
                continue
            actions.append(PlannedAction(book=book, target_shelf=shelf))
        return actions

    def _execute_action(
        self,
        storygraph: StoryGraphClient,
        action: PlannedAction,
        stats: RunStats,
    ) -> None:
        book = action.book
        try:
            candidates = storygraph.search_books(book.title, book.authors)
            best, score = pick_best_candidate(
                book,
                candidates,
                threshold=self._config.match_threshold,
            )
            if best is None:
                stats.failed += 1
                self._state.append_error(
                    abs_id=book.abs_id,
                    title=book.title,
                    reason="no_confident_match",
                    details={
                        "authors": book.authors,
                        "candidate_count": len(candidates),
                        "threshold": self._config.match_threshold,
                        "score": score,
                    },
                )
                return

            storygraph.set_shelf(best.url, action.target_shelf)
            self._state.append_processed(book.abs_id, action.target_shelf, best.url, score)
            stats.updated += 1
            LOGGER.info(
                "Updated %s (%s) -> %s (%s)",
                book.title,
                book.abs_id,
                action.target_shelf,
                best.url,
            )
        except Exception as exc:  # noqa: BLE001
            stats.failed += 1
            screenshot_path = self._screenshot_path(book.abs_id)
            try:
                storygraph.capture_failure(str(screenshot_path))
            except Exception:  # noqa: BLE001
                pass
            self._state.append_error(
                abs_id=book.abs_id,
                title=book.title,
                reason="sync_exception",
                details={"error": str(exc), "target_shelf": action.target_shelf},
            )
            LOGGER.exception("Failed syncing %s (%s)", book.title, book.abs_id)

    def _target_shelf(self, status: ReadingStatus) -> str | None:
        if status is ReadingStatus.UNREAD:
            return "to-read"
        if status is ReadingStatus.FINISHED:
            return "recently-read"
        return None

    def _write_summary(self, stats: RunStats, started_at: datetime) -> None:
        ended_at = datetime.now(tz=timezone.utc)
        payload = asdict(stats)
        payload["started_at"] = started_at.isoformat()
        payload["ended_at"] = ended_at.isoformat()
        payload["duration_seconds"] = round((ended_at - started_at).total_seconds(), 2)
        self._config.data_dir.mkdir(parents=True, exist_ok=True)
        self._config.run_summary_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=True),
            encoding="utf-8",
        )
        LOGGER.info("Run summary written to %s", self._config.run_summary_path)

    def _screenshot_path(self, abs_id: str) -> Path:
        folder = self._config.data_dir / "screenshots"
        folder.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        return folder / f"{timestamp}_{abs_id}.png"
