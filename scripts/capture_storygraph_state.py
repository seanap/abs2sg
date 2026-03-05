#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
from pathlib import Path

from playwright.sync_api import sync_playwright


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Capture StoryGraph browser storage state after manual login.",
    )
    parser.add_argument(
        "--url",
        default="https://app.thestorygraph.com/users/sign_in",
        help="StoryGraph login URL to open.",
    )
    parser.add_argument(
        "--out",
        default="storygraph_storage_state.json",
        help="Path to write Playwright storage state JSON.",
    )
    parser.add_argument(
        "--print-b64",
        action="store_true",
        help="Print base64-encoded storage state for SG_STORAGE_STATE_B64.",
    )
    args = parser.parse_args()

    out_path = Path(args.out).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto(args.url, wait_until="domcontentloaded", timeout=60_000)

        print("Complete StoryGraph login/challenge in the opened browser.")
        input("When you can browse StoryGraph normally, press Enter here...")

        context.storage_state(path=str(out_path))
        browser.close()

    print(f"Saved storage state to: {out_path}")
    if args.print_b64:
        encoded = base64.b64encode(out_path.read_bytes()).decode("utf-8")
        print("\nSG_STORAGE_STATE_B64 value:")
        print(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

