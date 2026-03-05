from __future__ import annotations

import base64
import json
import logging
import random
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote_plus

from playwright.sync_api import Browser, Page, Playwright, sync_playwright

from .models import StoryGraphCandidate

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class StoryGraphConfig:
    base_url: str
    login_path: str
    email: str
    password: str
    headless: bool
    search_url_template: str
    login_email_selectors: str
    login_password_selectors: str
    login_submit_selectors: str
    to_read_selector: str
    recently_read_selector: str
    request_delay_ms: int
    request_jitter_ms: int
    challenge_wait_seconds: int
    login_max_attempts: int
    login_retry_delay_seconds: int
    storage_state_path: str
    save_storage_state: bool
    storage_state_b64: str
    cookie_header: str
    try_existing_session_first: bool
    data_dir: str


class StoryGraphClient:
    def __init__(self, config: StoryGraphConfig) -> None:
        self._config = config
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._page: Page | None = None

    def __enter__(self) -> StoryGraphClient:
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=self._config.headless)
        self._maybe_write_storage_state_from_b64()
        self._maybe_write_storage_state_from_cookie_header()
        context_kwargs: dict = {}
        storage_path = Path(self._config.storage_state_path)
        if storage_path.exists():
            context_kwargs["storage_state"] = str(storage_path)
            LOGGER.info("Loading StoryGraph storage state from %s", storage_path)
        context = self._browser.new_context(**context_kwargs)
        self._page = context.new_page()
        try:
            self.login()
        except Exception as exc:  # noqa: BLE001
            self._dump_debug_artifacts("login_failed")
            raise RuntimeError(f"StoryGraph login failed ({self.page.url}): {exc}") from exc
        return self

    def __exit__(self, exc_type, exc, exc_tb) -> None:
        if self._browser is not None:
            self._browser.close()
        if self._playwright is not None:
            self._playwright.stop()

    @property
    def page(self) -> Page:
        if self._page is None:
            raise RuntimeError("StoryGraph client is not initialized")
        return self._page

    def login(self) -> None:
        last_error: Exception | None = None
        max_attempts = max(self._config.login_max_attempts, 1)
        for attempt in range(1, max_attempts + 1):
            try:
                self._login_once()
                self._save_storage_state()
                LOGGER.info("StoryGraph login complete")
                return
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if attempt >= max_attempts:
                    raise
                delay = max(self._config.login_retry_delay_seconds, 1)
                LOGGER.warning(
                    "StoryGraph login attempt %s/%s failed: %s; retrying in %ss",
                    attempt,
                    max_attempts,
                    exc,
                    delay,
                )
                self.page.wait_for_timeout(delay * 1000)
        if last_error is not None:
            raise last_error

    def _login_once(self) -> None:
        if self._config.try_existing_session_first:
            if self._session_is_already_authenticated():
                return

        login_url = f"{self._config.base_url}{self._config.login_path}"
        self.page.goto(login_url, wait_until="domcontentloaded", timeout=45_000)
        self._dismiss_common_prompts()

        # If persisted session is still valid, login form may never appear.
        if not self._is_login_page() and not self._is_cloudflare_challenge():
            self._sleep()
            return

        self._wait_for_login_surface()
        self._fill_login_email()
        self._fill_login_password()
        self._submit_login()
        self.page.wait_for_load_state("networkidle", timeout=45_000)
        self._sleep()
        if self._is_login_page():
            self._dump_debug_artifacts("login_still_on_signin")
            raise RuntimeError(
                "StoryGraph login appears to have failed; still on login form"
            )

    def _session_is_already_authenticated(self) -> bool:
        self.page.goto(self._config.base_url, wait_until="domcontentloaded", timeout=45_000)
        self._dismiss_common_prompts()
        self._sleep()
        if self._is_cloudflare_challenge():
            return False
        if self._is_login_page():
            return False
        LOGGER.info("StoryGraph session appears authenticated without login form")
        return True

    def search_books(
        self,
        title: str,
        authors: list[str],
        limit: int = 8,
    ) -> list[StoryGraphCandidate]:
        query = f"{title} {' '.join(authors)}".strip()
        url = self._config.search_url_template.format(query=quote_plus(query))
        self.page.goto(url, wait_until="domcontentloaded", timeout=45_000)
        self.page.wait_for_load_state("networkidle", timeout=45_000)
        self._sleep()

        anchors = self.page.locator("a[href*='/books/']")
        count = min(anchors.count(), limit * 2)
        seen: set[str] = set()
        candidates: list[StoryGraphCandidate] = []

        for index in range(count):
            anchor = anchors.nth(index)
            try:
                href = anchor.get_attribute("href")
                if not href:
                    continue
                full_url = self._absolute_url(href)
                if full_url in seen:
                    continue
                seen.add(full_url)
                text = (anchor.inner_text(timeout=2_000) or "").strip()
                if not text:
                    continue
                candidate_title = text.split("\n")[0].strip()
                snippet = text
                parsed_authors = self._extract_authors_from_snippet(snippet)
                candidates.append(
                    StoryGraphCandidate(
                        url=full_url,
                        title=candidate_title,
                        authors=parsed_authors,
                        snippet=snippet,
                    )
                )
                if len(candidates) >= limit:
                    break
            except Exception:  # noqa: BLE001
                continue

        return candidates

    def set_shelf(self, storygraph_url: str, target_shelf: str) -> None:
        self.page.goto(storygraph_url, wait_until="domcontentloaded", timeout=45_000)
        self.page.wait_for_load_state("networkidle", timeout=45_000)
        self._sleep()

        if target_shelf == "to-read":
            if self._click_first(
                [
                    selector.strip()
                    for selector in self._config.to_read_selector.split(",")
                    if selector.strip()
                ],
                required=False,
            ):
                self._sleep()
                return
            if self._set_status_via_select(["to read", "to-read", "want to read"]):
                self._sleep()
                return
            if self._set_status_via_menu(["to-read", "to read", "want to read"]):
                self._sleep()
                return
            raise RuntimeError(
                "Could not set to-read shelf. "
                f"Available clickable labels: {self._collect_clickable_labels()}"
            )

        if target_shelf == "recently-read":
            if self._click_first(
                [
                    selector.strip()
                    for selector in self._config.recently_read_selector.split(",")
                    if selector.strip()
                ],
                required=False,
            ):
                self._sleep()
                return
            if self._set_status_via_select(["read", "finished", "done"]):
                self._sleep()
                return
            if self._set_status_via_menu(["read", "finished", "done"]):
                self._sleep()
                return
            raise RuntimeError(
                "Could not set recently-read shelf. "
                f"Available clickable labels: {self._collect_clickable_labels()}"
            )

        raise ValueError(f"Unsupported target shelf: {target_shelf}")

    def capture_failure(self, path: str) -> None:
        self.page.screenshot(path=path, full_page=True)

    def _fill_first(self, selectors: list[str], value: str, *, required: bool = True) -> bool:
        for selector in selectors:
            try:
                locator = self.page.locator(selector).first
                if locator.count() == 0:
                    continue
                locator.fill(value)
                return True
            except Exception:  # noqa: BLE001
                continue
        if required:
            raise RuntimeError(f"Could not find field for selectors: {selectors}")
        return False

    def _click_first(self, selectors: list[str], *, required: bool = True) -> bool:
        for selector in selectors:
            try:
                locator = self.page.locator(selector).first
                if locator.count() == 0:
                    continue
                locator.click(timeout=10_000)
                return True
            except Exception:  # noqa: BLE001
                continue
        if required:
            raise RuntimeError(f"Could not click any selector: {selectors}")
        return False

    def _fill_login_email(self) -> None:
        selectors = self._parse_selector_csv(self._config.login_email_selectors)
        if self._fill_first(selectors, self._config.email, required=False):
            return
        if self._fill_by_label(["Email", "E-mail", "Username"], self._config.email):
            return
        if self._fill_by_placeholder(["Email", "Username"], self._config.email):
            return
        raise RuntimeError("Could not locate login email/username field")

    def _fill_login_password(self) -> None:
        selectors = self._parse_selector_csv(self._config.login_password_selectors)
        if self._fill_first(selectors, self._config.password, required=False):
            return
        if self._fill_by_label(["Password"], self._config.password):
            return
        if self._fill_by_placeholder(["Password"], self._config.password):
            return
        raise RuntimeError("Could not locate login password field")

    def _submit_login(self) -> None:
        selectors = self._parse_selector_csv(self._config.login_submit_selectors)
        if self._click_first(selectors, required=False):
            return
        try:
            self.page.keyboard.press("Enter")
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError("Could not submit login form") from exc

    def _fill_by_label(self, labels: list[str], value: str) -> bool:
        for label in labels:
            try:
                locator = self.page.get_by_label(label, exact=False).first
                if locator.count() == 0:
                    continue
                locator.fill(value)
                return True
            except Exception:  # noqa: BLE001
                continue
        return False

    def _fill_by_placeholder(self, placeholders: list[str], value: str) -> bool:
        for placeholder in placeholders:
            try:
                locator = self.page.get_by_placeholder(placeholder, exact=False).first
                if locator.count() == 0:
                    continue
                locator.fill(value)
                return True
            except Exception:  # noqa: BLE001
                continue
        return False

    def _is_login_page(self) -> bool:
        if "sign_in" in self.page.url or "login" in self.page.url:
            return True
        return self.page.locator("input[type='password']").count() > 0

    def _wait_for_login_surface(self) -> None:
        deadline = time.time() + max(self._config.challenge_wait_seconds, 5)
        while time.time() < deadline:
            if self._has_login_surface():
                return
            if self._is_cloudflare_challenge():
                self.page.wait_for_timeout(2_000)
                continue
            self.page.wait_for_timeout(1_000)

        if self._is_cloudflare_challenge():
            ray_id = self._extract_cloudflare_ray_id()
            raise RuntimeError(
                "Blocked by Cloudflare challenge; no login form available "
                f"after {self._config.challenge_wait_seconds}s (ray_id={ray_id})"
            )
        raise RuntimeError("StoryGraph login form did not appear before timeout")

    def _has_login_surface(self) -> bool:
        email_selectors = self._parse_selector_csv(self._config.login_email_selectors)
        password_selectors = self._parse_selector_csv(self._config.login_password_selectors)
        has_email = any(self.page.locator(selector).count() > 0 for selector in email_selectors)
        has_password = any(
            self.page.locator(selector).count() > 0 for selector in password_selectors
        )
        return has_email and has_password

    def _is_cloudflare_challenge(self) -> bool:
        try:
            title = self.page.title().lower()
        except Exception:  # noqa: BLE001
            title = ""
        if "just a moment" in title:
            return True
        if "__cf_chl" in self.page.url:
            return True
        return (
            self.page.locator("input[name='cf-turnstile-response']").count() > 0
            or self.page.locator("text=Performing security verification").count() > 0
            or self.page.locator("text=Enable JavaScript and cookies to continue").count() > 0
        )

    def _extract_cloudflare_ray_id(self) -> str:
        try:
            text = self.page.locator(".ray-id code").first.inner_text(timeout=1_000).strip()
            if text:
                return text
        except Exception:  # noqa: BLE001
            pass
        try:
            html = self.page.content()
            match = re.search(r"Ray ID:\s*<code>([^<]+)</code>", html, flags=re.IGNORECASE)
            if match:
                return match.group(1).strip()
        except Exception:  # noqa: BLE001
            pass
        return "unknown"

    def _parse_selector_csv(self, raw: str) -> list[str]:
        return [selector.strip() for selector in raw.split(",") if selector.strip()]

    def _set_status_via_select(self, terms: list[str]) -> bool:
        try:
            selects = self.page.locator("select")
            count = min(selects.count(), 10)
        except Exception:  # noqa: BLE001
            return False

        for index in range(count):
            select = selects.nth(index)
            try:
                options = select.locator("option")
                option_count = min(options.count(), 50)
                for option_index in range(option_count):
                    option = options.nth(option_index)
                    label = (option.inner_text(timeout=1_000) or "").strip().lower()
                    if not label:
                        continue
                    if any(term in label for term in terms):
                        value = option.get_attribute("value")
                        if value is None:
                            continue
                        select.select_option(value=value, timeout=5_000)
                        return True
            except Exception:  # noqa: BLE001
                continue
        return False

    def _set_status_via_menu(self, terms: list[str]) -> bool:
        openers = [
            "button:has-text('Status')",
            "button:has-text('Read Status')",
            "button:has-text('Shelf')",
            "button[aria-haspopup='menu']",
            "button[aria-haspopup='listbox']",
            "button:has-text('Want to Read')",
            "button:has-text('To-Read')",
            "button:has-text('To Read')",
            "button:has-text('Currently Reading')",
            "button:has-text('Read')",
        ]
        self._click_first(openers, required=False)
        self.page.wait_for_timeout(500)

        for term in terms:
            if self._click_label_candidates(
                [
                    term,
                    term.replace("-", " "),
                    term.title(),
                    term.upper(),
                ]
            ):
                return True
        return False

    def _click_label_candidates(self, labels: list[str]) -> bool:
        for label in labels:
            clean = label.strip()
            if not clean:
                continue
            try:
                for role in ("button", "menuitem", "link", "option"):
                    locator = self.page.get_by_role(role, name=clean, exact=False).first
                    if locator.count() > 0:
                        locator.click(timeout=5_000)
                        return True
            except Exception:  # noqa: BLE001
                pass
            try:
                if self._click_first(
                    [
                        f"button:has-text('{clean}')",
                        f"a:has-text('{clean}')",
                        f"li:has-text('{clean}')",
                        f"[role='menuitem']:has-text('{clean}')",
                    ],
                    required=False,
                ):
                    return True
            except Exception:  # noqa: BLE001
                continue
        return False

    def _collect_clickable_labels(self) -> list[str]:
        try:
            nodes = self.page.locator("button, a, [role='button'], [role='menuitem']")
            count = min(nodes.count(), 80)
            labels: list[str] = []
            for index in range(count):
                text = (nodes.nth(index).inner_text(timeout=500) or "").strip()
                if not text:
                    continue
                if text in labels:
                    continue
                labels.append(text)
            return labels[:20]
        except Exception:  # noqa: BLE001
            return []

    def _dismiss_common_prompts(self) -> None:
        self._click_first(
            [
                "button:has-text('Accept all')",
                "button:has-text('Accept All')",
                "button:has-text('I agree')",
                "button:has-text('Accept')",
            ],
            required=False,
        )

    def _dump_debug_artifacts(self, reason: str) -> None:
        try:
            root = Path(self._config.data_dir) / "debug"
            root.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            prefix = root / f"{stamp}_{reason}"
            self.page.screenshot(path=str(prefix.with_suffix(".png")), full_page=True)
            prefix.with_suffix(".html").write_text(self.page.content(), encoding="utf-8")
            LOGGER.info("Wrote login debug artifacts to %s*", prefix)
        except Exception:  # noqa: BLE001
            LOGGER.warning("Could not write login debug artifacts")

    def _save_storage_state(self) -> None:
        if not self._config.save_storage_state:
            return
        try:
            path = Path(self._config.storage_state_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            self.page.context.storage_state(path=str(path))
            LOGGER.info("Saved StoryGraph storage state to %s", path)
        except Exception:  # noqa: BLE001
            LOGGER.warning("Could not save StoryGraph storage state")

    def _maybe_write_storage_state_from_b64(self) -> None:
        raw = self._config.storage_state_b64
        if not raw:
            return
        try:
            decoded = base64.b64decode(raw)
            payload = json.loads(decoded.decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("storage state is not a JSON object")
            path = Path(self._config.storage_state_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload), encoding="utf-8")
            LOGGER.info("Loaded StoryGraph storage state from SG_STORAGE_STATE_B64")
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError("Invalid SG_STORAGE_STATE_B64 payload") from exc

    def _maybe_write_storage_state_from_cookie_header(self) -> None:
        raw = self._config.cookie_header
        if not raw:
            return

        try:
            cookies = []
            for part in raw.split(";"):
                token = part.strip()
                if not token or "=" not in token:
                    continue
                name, value = token.split("=", 1)
                cookies.append(
                    {
                        "name": name.strip(),
                        "value": value.strip(),
                        "domain": "app.thestorygraph.com",
                        "path": "/",
                        "expires": -1,
                        "httpOnly": False,
                        "secure": True,
                        "sameSite": "Lax",
                    }
                )

            if not cookies:
                raise ValueError("no valid cookie pairs found")

            payload = {"cookies": cookies, "origins": []}
            path = Path(self._config.storage_state_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload), encoding="utf-8")
            LOGGER.info(
                "Loaded StoryGraph storage state from SG_COOKIE_HEADER (%s cookies)",
                len(cookies),
            )
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError("Invalid SG_COOKIE_HEADER payload") from exc

    def _absolute_url(self, href: str) -> str:
        if href.startswith("http://") or href.startswith("https://"):
            return href
        return f"{self._config.base_url}{href}"

    def _extract_authors_from_snippet(self, snippet: str) -> list[str]:
        lines = [line.strip() for line in snippet.splitlines() if line.strip()]
        if len(lines) < 2:
            return []
        possible = lines[1]
        if possible.lower().startswith("by "):
            possible = possible[3:]
        authors = [
            token.strip()
            for token in possible.replace("&", ",").replace(" and ", ",").split(",")
            if token.strip()
        ]
        return authors

    def _sleep(self) -> None:
        base = max(self._config.request_delay_ms, 0)
        jitter = max(self._config.request_jitter_ms, 0)
        extra = random.randint(0, jitter) if jitter > 0 else 0
        self.page.wait_for_timeout(base + extra)
