#!/usr/bin/env python3
"""
Leaves and deletes every conversation in your Messenger Marketplace inbox.

Python/Playwright rewrite of cleanup-marketplace-chats.js — same behavior, but
this one drives a real, persistent browser session instead of a one-shot
DevTools console paste, so it can also carry you through login on first run.

Setup (once):
    pip install -r requirements.txt
    playwright install chromium

Usage:
    python cleanup_marketplace_chats.py

To stop early: press Ctrl+C. It finishes whatever it's currently doing, then
stops cleanly and prints a summary.

See README.md for the full explanation of how login works and why it's
designed this way.
"""

import os
import random
import sys
import time
from getpass import getpass
from pathlib import Path

from playwright.sync_api import sync_playwright

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

MARKETPLACE_URL = "https://www.messenger.com/marketplace/"
PROFILE_DIR = Path(__file__).parent / ".browser-profile"
MAX_ITERATIONS = 400  # safety cap, well above any realistic inbox size
MAX_SAME_TITLE_REPEATS = 4

# Runs once per top conversation in the list: opens its menu, leaves the group
# (if that option exists) and deletes the chat, confirming both dialogs. This
# is the same algorithm as cleanup-marketplace-chats.js (including its bug
# fixes for null containers and stale titles) — kept as one evaluate() call so
# it can use Facebook's own DOM state directly instead of round-tripping every
# micro-step through Playwright locators.
PROCESS_ONE_JS = """
async () => {
  function sleep(ms) { return new Promise((r) => setTimeout(r, ms)); }
  function jitter(min, max) { return min + Math.random() * (max - min); }

  function getListContainer() {
    return Array.from(document.querySelectorAll("div")).find((e) => {
      const s = getComputedStyle(e);
      return (
        (s.overflowY === "auto" || s.overflowY === "scroll") &&
        e.scrollHeight > e.clientHeight + 50
      );
    });
  }
  function getRowButtons(container) {
    return Array.from(container.querySelectorAll('[aria-label^="More options for"]'));
  }
  function getOpenMenuItems() {
    return Array.from(document.querySelectorAll('[role="menuitem"]'));
  }
  async function clickMenuItemStartingWith(text) {
    for (let i = 0; i < 15; i++) {
      const items = getOpenMenuItems();
      const item = items.find((el) => el.innerText && el.innerText.trim().startsWith(text));
      if (item) { item.click(); return true; }
      await sleep(50);
    }
    return false;
  }
  async function menuHasItemStartingWith(text) {
    for (let i = 0; i < 15; i++) {
      const items = getOpenMenuItems();
      if (items.some((el) => el.innerText && el.innerText.trim().startsWith(text))) return true;
      if (items.length > 0) return false;
      await sleep(50);
    }
    return false;
  }
  async function clickDialogButtonExact(text) {
    for (let attempt = 0; attempt < 25; attempt++) {
      const dialog = document.querySelector('[role="dialog"]');
      if (dialog) {
        const buttons = Array.from(dialog.querySelectorAll('[role="button"], button'));
        const btn = buttons.find((b) => b.innerText && b.innerText.trim() === text);
        if (btn) { btn.click(); return true; }
      }
      await sleep(80);
    }
    return false;
  }
  async function waitForDialogToClose() {
    for (let i = 0; i < 25; i++) {
      if (!document.querySelector('[role="dialog"]')) return true;
      await sleep(80);
    }
    return false;
  }
  function pressEscape() {
    document.body.dispatchEvent(
      new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true })
    );
  }

  let container = getListContainer();
  if (!container) return { status: "error", title: null, error: "list-container-not-found" };

  container.scrollTop = 0;
  await sleep(100);
  let rows = getRowButtons(container);
  if (rows.length === 0) {
    container.scrollTop = container.scrollHeight;
    await sleep(400);
    container.scrollTop = 0;
    await sleep(250);
    rows = getRowButtons(container);
    if (rows.length === 0) return { status: "empty" };
  }

  const rowBtn = rows[0];
  let title = (rowBtn.getAttribute("aria-label") || "").replace("More options for", "").trim();

  rowBtn.click();
  await sleep(jitter(120, 220));

  const hasLeave = await menuHasItemStartingWith("Leave group");
  if (hasLeave) {
    const clickedLeave = await clickMenuItemStartingWith("Leave group");
    if (clickedLeave) {
      const confirmedLeave = await clickDialogButtonExact("Leave group");
      if (confirmedLeave) {
        await waitForDialogToClose();
      } else {
        pressEscape();
        return { status: "error", title, error: "could-not-confirm-leave" };
      }
    }
    await sleep(jitter(150, 250));

    container = getListContainer();
    if (!container) return { status: "error", title, error: "list-container-lost-after-leave" };
    container.scrollTop = 0;
    await sleep(100);
    const rowsAfterLeave = getRowButtons(container);
    const rowAgain =
      rowsAfterLeave.find((r) => (r.getAttribute("aria-label") || "").includes(title)) ||
      rowsAfterLeave[0];
    if (!rowAgain) return { status: "error", title, error: "row-disappeared-before-delete" };
    // The original row sometimes vanishes from the list once you leave it rather than
    // sticking around for the delete step — if so we fell back to whatever's now on top,
    // so re-derive the title to keep the caller's log/summary accurate.
    title = (rowAgain.getAttribute("aria-label") || "").replace("More options for", "").trim() || title;
    rowAgain.click();
    await sleep(jitter(120, 220));
  }

  const clickedDelete = await clickMenuItemStartingWith("Delete chat");
  if (!clickedDelete) {
    pressEscape();
    return { status: "error", title, error: "delete-option-not-found" };
  }
  const confirmedDelete = await clickDialogButtonExact("Delete chat");
  if (!confirmedDelete) {
    pressEscape();
    return { status: "error", title, error: "could-not-confirm-delete" };
  }
  await waitForDialogToClose();
  return { status: "deleted", title };
}
"""

COUNT_ALL_JS = """
async () => {
  function sleep(ms) { return new Promise((r) => setTimeout(r, ms)); }
  const container = Array.from(document.querySelectorAll("div")).find((e) => {
    const s = getComputedStyle(e);
    return (s.overflowY === "auto" || s.overflowY === "scroll") && e.scrollHeight > e.clientHeight + 50;
  });
  if (!container) return -1;

  const seen = new Set();
  container.scrollTop = 0;
  await sleep(200);
  Array.from(container.querySelectorAll('[aria-label^="More options for"]'))
    .forEach((b) => seen.add(b.getAttribute("aria-label")));

  let lastScrollTop = -1, stableRounds = 0, iterations = 0;
  while (stableRounds < 4 && iterations < 500) {
    container.scrollTop += 400;
    await sleep(120);
    Array.from(container.querySelectorAll('[aria-label^="More options for"]'))
      .forEach((b) => seen.add(b.getAttribute("aria-label")));
    if (container.scrollTop === lastScrollTop) stableRounds++; else stableRounds = 0;
    lastScrollTop = container.scrollTop;
    iterations++;
  }
  container.scrollTop = 0;
  await sleep(200);
  return seen.size;
}
"""


def jitter(min_s, max_s):
    return random.uniform(min_s, max_s)


def is_logged_out(page):
    return page.locator('input[name="pass"]').count() > 0 or "/login" in page.url


def do_login(page):
    """
    Guided, one-time login. Runs only on the very first use (or if the saved
    browser profile's session ever expires) — see README.md for why this is
    safe-ish to automate here but wasn't in the plain DevTools-console version.
    """
    email = os.environ.get("FB_EMAIL") or input("Facebook email or phone: ").strip()
    password = os.environ.get("FB_PASSWORD") or getpass("Facebook password (hidden): ")

    page.goto("https://www.facebook.com/login")
    page.fill('input[name="email"]', email)
    page.fill('input[name="pass"]', password)
    page.click('button[name="login"]')
    page.wait_for_timeout(2000)

    print(
        "\nIf Facebook is showing a security check, a code prompt, or a "
        "'save this browser' screen, handle it in the browser window now."
    )
    input("Press Enter here once you're logged in and can see Messenger... ")


def count_conversations(page):
    return page.evaluate(COUNT_ALL_JS)


def process_top_conversation(page):
    return page.evaluate(PROCESS_ONE_JS)


def run_cleanup(page):
    print("Counting conversations, please wait...")
    initial_count = count_conversations(page)
    if initial_count == -1:
        print(
            "Could not find the Marketplace chat list. Make sure you're on "
            "messenger.com/marketplace/ with the inbox list visible."
        )
        return
    print(f"Found {initial_count} Marketplace conversations. Starting cleanup...")

    deleted_titles = []
    skipped = []
    errors = []
    last_title_seen = None
    same_title_repeats = 0
    stagnant_empty_rounds = 0
    total_iterations = 0

    try:
        while total_iterations < MAX_ITERATIONS:
            total_iterations += 1

            try:
                result = process_top_conversation(page)
            except Exception as e:
                # A DOM hiccup (Facebook re-rendering mid-click, a detached node, a
                # container that went missing for a moment) shouldn't kill the whole
                # run — log it, back off briefly, and keep going.
                print(f"Unexpected error, recovering: {e}")
                errors.append({"title": None, "error": str(e)})
                time.sleep(0.5)
                continue

            status = result.get("status")
            title = result.get("title")

            if status == "empty":
                stagnant_empty_rounds += 1
                print(f"Inbox appears empty (check {stagnant_empty_rounds}/3)...")
                if stagnant_empty_rounds >= 3:
                    print("Marketplace inbox is empty. Done.")
                    break
                continue
            stagnant_empty_rounds = 0

            if title == last_title_seen:
                same_title_repeats += 1
            else:
                same_title_repeats = 0
                last_title_seen = title

            if same_title_repeats >= MAX_SAME_TITLE_REPEATS:
                print(f'Skipping "{title}" after repeated failures to delete it.')
                skipped.append(title)
                same_title_repeats = 0
                last_title_seen = None
                time.sleep(0.5)
                continue

            if status == "deleted":
                deleted_titles.append(title)
                print(f"Deleted ({len(deleted_titles)}): {title}")
            elif status == "error":
                print(f'"{title}": {result.get("error")}')
                errors.append({"title": title, "error": result.get("error")})

            time.sleep(jitter(0.25, 0.5))
    except KeyboardInterrupt:
        print("\nStopped by user (Ctrl+C).")

    if total_iterations >= MAX_ITERATIONS:
        print("Hit the safety iteration cap — stopping. Re-run the script to continue.")

    print("---- Marketplace cleanup summary ----")
    print(f"Found at start: {initial_count}")
    print(f"Deleted: {len(deleted_titles)}")
    if skipped:
        print(f"Skipped (repeated failures): {len(skipped)}", skipped)
    if errors:
        print(f"Errors recovered from: {len(errors)}", errors)
    print("Deleted titles:", deleted_titles)


def main():
    PROFILE_DIR.mkdir(exist_ok=True)

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            str(PROFILE_DIR),
            headless=False,
            viewport={"width": 1280, "height": 900},
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(MARKETPLACE_URL)
        page.wait_for_timeout(1500)

        if is_logged_out(page):
            print("Not logged in yet in this browser profile.")
            do_login(page)
            page.goto(MARKETPLACE_URL)
            page.wait_for_timeout(1500)

        if is_logged_out(page):
            print("Still doesn't look logged in — aborting.")
            context.close()
            sys.exit(1)

        run_cleanup(page)
        context.close()


if __name__ == "__main__":
    main()
