from __future__ import annotations

import logging
import time

from .config import Config
from .logging_utils import configure_logging
from .sync_engine import SyncEngine

LOGGER = logging.getLogger(__name__)


def run() -> int:
    configure_logging()
    try:
        config = Config.from_env()
    except Exception as exc:  # noqa: BLE001
        LOGGER.error("Invalid configuration: %s", exc)
        return 2

    engine = SyncEngine(config)
    interval_minutes = config.sync_interval_minutes
    if interval_minutes <= 0:
        engine.run_once()
        return 0

    LOGGER.info("Starting loop mode: every %s minute(s)", interval_minutes)
    while True:
        engine.run_once()
        sleep_seconds = interval_minutes * 60
        LOGGER.info("Sleeping for %s seconds", sleep_seconds)
        time.sleep(sleep_seconds)


if __name__ == "__main__":
    raise SystemExit(run())

