from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    return int(value)


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    return float(value)


@dataclass(frozen=True)
class Config:
    abs_url: str
    abs_token: str
    abs_library_id: str | None
    abs_verify_tls: bool
    sg_email: str
    sg_password: str
    sg_base_url: str
    data_dir: Path
    dry_run: bool
    headless: bool
    max_actions_per_run: int
    request_delay_ms: int
    request_jitter_ms: int
    sg_challenge_wait_seconds: int
    sg_login_max_attempts: int
    sg_login_retry_delay_seconds: int
    sg_storage_state_path: Path
    sg_save_storage_state: bool
    sg_storage_state_b64: str
    sg_cookie_header: str
    sg_try_existing_session_first: bool
    match_threshold: float
    match_tie_delta: float
    match_min_quality: float
    sync_interval_minutes: int
    error_retry_minutes: int
    sg_search_url_template: str
    sg_login_path: str
    sg_login_email_selectors: str
    sg_login_password_selectors: str
    sg_login_submit_selectors: str
    sg_to_read_selector: str
    sg_recently_read_selector: str

    @property
    def processed_log_path(self) -> Path:
        return self.data_dir / "processed_activities.log"

    @property
    def errors_log_path(self) -> Path:
        return self.data_dir / "errors.log"

    @property
    def run_summary_path(self) -> Path:
        return self.data_dir / "run_summary.json"

    @staticmethod
    def from_env() -> Config:
        abs_url = os.getenv("ABS_URL", "").rstrip("/")
        abs_token = os.getenv("ABS_TOKEN", "")
        sg_email = os.getenv("SG_EMAIL", "")
        sg_password = os.getenv("SG_PASSWORD", "")

        if not abs_url:
            raise ValueError("ABS_URL is required")
        if not abs_token:
            raise ValueError("ABS_TOKEN is required")
        if not sg_email:
            raise ValueError("SG_EMAIL is required")
        if not sg_password:
            raise ValueError("SG_PASSWORD is required")

        return Config(
            abs_url=abs_url,
            abs_token=abs_token,
            abs_library_id=os.getenv("ABS_LIBRARY_ID"),
            abs_verify_tls=_env_bool("ABS_VERIFY_TLS", True),
            sg_email=sg_email,
            sg_password=sg_password,
            sg_base_url=os.getenv("SG_BASE_URL", "https://app.thestorygraph.com").rstrip("/"),
            data_dir=Path(os.getenv("DATA_DIR", "/data")),
            dry_run=_env_bool("DRY_RUN", False),
            headless=_env_bool("HEADLESS", True),
            max_actions_per_run=_env_int("MAX_ACTIONS_PER_RUN", 100),
            request_delay_ms=_env_int("REQUEST_DELAY_MS", 2500),
            request_jitter_ms=_env_int("REQUEST_JITTER_MS", 1000),
            sg_challenge_wait_seconds=_env_int("SG_CHALLENGE_WAIT_SECONDS", 90),
            sg_login_max_attempts=_env_int("SG_LOGIN_MAX_ATTEMPTS", 3),
            sg_login_retry_delay_seconds=_env_int("SG_LOGIN_RETRY_DELAY_SECONDS", 30),
            sg_storage_state_path=Path(
                os.getenv("SG_STORAGE_STATE_PATH", "/data/storygraph_storage_state.json")
            ),
            sg_save_storage_state=_env_bool("SG_SAVE_STORAGE_STATE", True),
            sg_storage_state_b64=os.getenv("SG_STORAGE_STATE_B64", "").strip(),
            sg_cookie_header=os.getenv("SG_COOKIE_HEADER", "").strip(),
            sg_try_existing_session_first=_env_bool("SG_TRY_EXISTING_SESSION_FIRST", True),
            match_threshold=_env_float("MATCH_THRESHOLD", 0.70),
            match_tie_delta=_env_float("MATCH_TIE_DELTA", 0.04),
            match_min_quality=_env_float("MATCH_MIN_QUALITY", 0.0),
            sync_interval_minutes=_env_int("SYNC_INTERVAL_MINUTES", 0),
            error_retry_minutes=_env_int("ERROR_RETRY_MINUTES", 15),
            sg_search_url_template=os.getenv(
                "SG_SEARCH_URL_TEMPLATE",
                "https://app.thestorygraph.com/browse?search_term={query}",
            ),
            sg_login_path=os.getenv("SG_LOGIN_PATH", "/users/sign_in"),
            sg_login_email_selectors=os.getenv(
                "SG_LOGIN_EMAIL_SELECTORS",
                (
                    "input[name='user[email]'], input[type='email'], input[name='email'], "
                    "input[name*='email' i], input[id*='email' i], input[autocomplete='email']"
                ),
            ),
            sg_login_password_selectors=os.getenv(
                "SG_LOGIN_PASSWORD_SELECTORS",
                (
                    "input[name='user[password]'], input[type='password'], "
                    "input[name='password'], input[name*='password' i]"
                ),
            ),
            sg_login_submit_selectors=os.getenv(
                "SG_LOGIN_SUBMIT_SELECTORS",
                (
                    "button:has-text('Log in'), button:has-text('Sign in'), "
                    "button[type='submit'], input[type='submit']"
                ),
            ),
            sg_to_read_selector=os.getenv(
                "SG_TO_READ_SELECTOR",
                (
                    "button:has-text('To-Read'), button:has-text('To Read'), "
                    "button:has-text('Want to Read'), button:has-text('to-read'), "
                    "a:has-text('To-Read'), a:has-text('Want to Read')"
                ),
            ),
            sg_recently_read_selector=os.getenv(
                "SG_RECENTLY_READ_SELECTOR",
                (
                    "button:has-text('Read'), button:has-text('Mark as read'), "
                    "button:has-text('Finished'), a:has-text('Read'), a:has-text('Finished')"
                ),
            ),
        )
