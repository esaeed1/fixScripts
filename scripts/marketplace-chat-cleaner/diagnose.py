#!/usr/bin/env python3
"""
Read-only diagnostic for marketplace-chat-cleaner.

Opens the real Brave profile, navigates to Messenger Marketplace, and reports
exactly what it finds (page URL, login state, how many conversations it can
see) plus a screenshot — without ever clicking Leave or Delete. Makes no
changes to your account. Not part of the normal cleanup flow; just for
figuring out why the real script isn't behaving as expected.
"""

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).parent))
from cleanup_marketplace_chats import (  # noqa: E402
    MARKETPLACE_URL,
    count_conversations,
    find_brave_executable,
    find_brave_user_data_dir,
    goto_marketplace,
    is_brave_running,
    is_logged_out,
    wait_for_page_ready,
)


def main():
    if is_brave_running():
        print("Brave is currently running — close it fully first, then re-run this.")
        sys.exit(1)

    brave_path = find_brave_executable()
    if not brave_path:
        print("Could not find Brave automatically. Set BRAVE_PATH and try again.")
        sys.exit(1)
    user_data_dir = find_brave_user_data_dir()
    print(f"Brave executable: {brave_path}")
    print(f"Brave profile dir: {user_data_dir}")

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir,
            executable_path=brave_path,
            headless=False,
            no_viewport=True,
        )
        page = context.pages[0] if context.pages else context.new_page()

        print(f"Navigating to {MARKETPLACE_URL} ...")
        goto_marketplace(page)
        print(f"URL right after navigation: {page.url}")

        print("Waiting 20s flat (same as the real script's first-load wait)...")
        page.wait_for_timeout(20000)
        print(f"URL after 20s wait: {page.url}")

        state = wait_for_page_ready(page, timeout_s=45)
        print(f"wait_for_page_ready() result: {state}")
        print(f"Final URL: {page.url}")
        print(f"is_logged_out(): {is_logged_out(page)}")

        row_count = page.locator('[aria-label^="More options for"]').count()
        print(f"Conversation row buttons found: {row_count}")

        scrollable_count = page.evaluate(
            """
            () => Array.from(document.querySelectorAll("div")).filter((e) => {
                const s = getComputedStyle(e);
                return (s.overflowY === "auto" || s.overflowY === "scroll")
                    && e.scrollHeight > e.clientHeight + 50;
            }).length
            """
        )
        print(f"Elements matching the 'scrollable container' heuristic: {scrollable_count}")

        counted = count_conversations(page)
        print(f"count_conversations() (real, read-only, scroll-only fn) result: {counted}")

        screenshot_path = Path(__file__).parent / "diagnose-screenshot.png"
        page.screenshot(path=str(screenshot_path))
        print(f"Saved screenshot to {screenshot_path}")

        context.close()
        print("Done. Nothing was clicked or changed.")


if __name__ == "__main__":
    main()
