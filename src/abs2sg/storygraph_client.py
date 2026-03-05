from __future__ import annotations

import logging
import random
from dataclasses import dataclass
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
    to_read_selector: str
    recently_read_selector: str
    request_delay_ms: int
    request_jitter_ms: int


class StoryGraphClient:
    def __init__(self, config: StoryGraphConfig) -> None:
        self._config = config
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._page: Page | None = None

    def __enter__(self) -> StoryGraphClient:
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=self._config.headless)
        context = self._browser.new_context()
        self._page = context.new_page()
        self.login()
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
        login_url = f"{self._config.base_url}{self._config.login_path}"
        self.page.goto(login_url, wait_until="domcontentloaded", timeout=45_000)
        self._fill_first(
            [
                "input[name='user[email]']",
                "input[type='email']",
                "input[name='email']",
            ],
            self._config.email,
        )
        self._fill_first(
            [
                "input[name='user[password]']",
                "input[type='password']",
                "input[name='password']",
            ],
            self._config.password,
        )
        self._click_first(
            [
                "button:has-text('Log in')",
                "button:has-text('Sign in')",
                "input[type='submit']",
            ]
        )
        self.page.wait_for_load_state("networkidle", timeout=45_000)
        if "sign_in" in self.page.url:
            raise RuntimeError("StoryGraph login appears to have failed")
        self._sleep()
        LOGGER.info("StoryGraph login complete")

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
            self._click_first(
                [
                    selector.strip()
                    for selector in self._config.to_read_selector.split(",")
                    if selector.strip()
                ]
            )
            self._sleep()
            return

        if target_shelf == "recently-read":
            self._click_first(
                [
                    selector.strip()
                    for selector in self._config.recently_read_selector.split(",")
                    if selector.strip()
                ]
            )
            self._sleep()
            return

        raise ValueError(f"Unsupported target shelf: {target_shelf}")

    def capture_failure(self, path: str) -> None:
        self.page.screenshot(path=path, full_page=True)

    def _fill_first(self, selectors: list[str], value: str) -> None:
        for selector in selectors:
            try:
                locator = self.page.locator(selector).first
                if locator.count() == 0:
                    continue
                locator.fill(value)
                return
            except Exception:  # noqa: BLE001
                continue
        raise RuntimeError(f"Could not find field for selectors: {selectors}")

    def _click_first(self, selectors: list[str]) -> None:
        for selector in selectors:
            try:
                locator = self.page.locator(selector).first
                if locator.count() == 0:
                    continue
                locator.click(timeout=10_000)
                return
            except Exception:  # noqa: BLE001
                continue
        raise RuntimeError(f"Could not click any selector: {selectors}")

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
