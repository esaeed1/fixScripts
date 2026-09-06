#!/usr/bin/env python3
"""
Leaves and deletes every conversation in your Messenger Marketplace inbox.

Opens your actual, already-installed Brave browser using your real profile
(same cookies, same saved logins) instead of a separate managed browser — so
in the common case you're already logged into Facebook and nothing here ever
sees or types your password. If you're not logged in, it just pauses and lets
you log in yourself in the window that opens.

Setup (once):
    pip install -r requirements.txt

Usage:
    python cleanup_marketplace_chats.py

To stop early: press Ctrl+C. It finishes whatever it's currently doing, then
stops cleanly and prints a summary.

See README.md for more on how this finds Brave and why it's designed this way.
"""

import os
import random
import sys
import time
from pathlib import Path

import psutil
from playwright.sync_api import sync_playwright

MARKETPLACE_URL = "https://www.messenger.com/marketplace/"
MAX_ITERATIONS = 400  # safety cap, well above any realistic inbox size
MAX_SAME_TITLE_REPEATS = 4

# Runs once per top conversation in the list: opens its menu, leaves the group
# (if that option exists) and deletes the chat, confirming both dialogs. Kept
# as one evaluate() call (with retries/null-checks for Facebook's own flaky
# re-renders) so it can act on the DOM directly instead of round-tripping every
# micro-step through Playwright locators.
PROCESS_ONE_JS = """
async () => {
  function sleep(ms) { return new Promise((r) => setTimeout(r, ms)); }
  function jitter(min, max) { return min + Math.random() * (max - min); }

  // Facebook's exact wording for these two menu items has drifted before (e.g. "Leave
  // group" vs "Leave conversation"), so match a few plausible phrasings case-insensitively
  // instead of one exact string.
  const LEAVE_TEXTS = ["leave group", "leave conversation", "leave chat"];
  const DELETE_TEXTS = ["delete chat", "delete conversation"];

  function getListContainer() {
    return Array.from(document.querySelectorAll("div")).find((e) => {
      const s = getComputedStyle(e);
      return (
        (s.overflowY === "auto" || s.overflowY === "scroll") &&
        e.scrollHeight > e.clientHeight + 50
      );
    });
  }
  // Queried page-wide, not scoped to the "scrollable container" — with only a handful of
  // conversations the list doesn't overflow the visible area at all, so there may be no
  // scrollable container to find even though the conversation rows are right there in the DOM.
  function getRowButtons() {
    return Array.from(document.querySelectorAll('[aria-label^="More options for"]'));
  }
  function getOpenMenuItems() {
    return Array.from(document.querySelectorAll('[role="menuitem"]'));
  }
  async function clickMenuItemMatching(candidates) {
    for (let i = 0; i < 15; i++) {
      const items = getOpenMenuItems();
      const item = items.find((el) => {
        const text = (el.innerText || "").trim().toLowerCase();
        return candidates.some((c) => text.startsWith(c));
      });
      if (item) { item.click(); return true; }
      await sleep(50);
    }
    return false;
  }
  async function menuHasItemMatching(candidates) {
    for (let i = 0; i < 15; i++) {
      const items = getOpenMenuItems();
      if (items.some((el) => {
        const text = (el.innerText || "").trim().toLowerCase();
        return candidates.some((c) => text.startsWith(c));
      })) return true;
      if (items.length > 0) return false;
      await sleep(50);
    }
    return false;
  }
  async function clickDialogButtonMatching(candidates) {
    for (let attempt = 0; attempt < 25; attempt++) {
      const dialog = document.querySelector('[role="dialog"]');
      if (dialog) {
        const buttons = Array.from(dialog.querySelectorAll('[role="button"], button'));
        const btn = buttons.find((b) => {
          const text = (b.innerText || "").trim().toLowerCase();
          return candidates.some((c) => text === c || text.startsWith(c));
        });
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

  let rows = getRowButtons();
  if (rows.length === 0) {
    // Nothing found yet. If there's a scrollable container, nudge it to force any lazy
    // content to render, then re-check. If there's no container at all (a short list has
    // nothing to scroll), there's nothing more to try — the inbox really is empty.
    const container = getListContainer();
    if (container) {
      container.scrollTop = container.scrollHeight;
      await sleep(400);
      container.scrollTop = 0;
      await sleep(250);
      rows = getRowButtons();
    }
    if (rows.length === 0) return { status: "empty" };
  }

  const rowBtn = rows[0];
  let title = (rowBtn.getAttribute("aria-label") || "").replace("More options for", "").trim();

  rowBtn.click();
  await sleep(jitter(120, 220));

  const hasLeave = await menuHasItemMatching(LEAVE_TEXTS);
  if (hasLeave) {
    // Leaving is mandatory whenever the option is offered — if any step here fails,
    // bail out with an error instead of silently falling through to delete, otherwise
    // a group chat gets deleted locally without you ever actually leaving the group.
    const clickedLeave = await clickMenuItemMatching(LEAVE_TEXTS);
    if (!clickedLeave) {
      pressEscape();
      return { status: "error", title, error: "could-not-click-leave" };
    }
    const confirmedLeave = await clickDialogButtonMatching(LEAVE_TEXTS);
    if (!confirmedLeave) {
      pressEscape();
      return { status: "error", title, error: "could-not-confirm-leave" };
    }
    await waitForDialogToClose();
    await sleep(jitter(150, 250));

    const rowsAfterLeave = getRowButtons();
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

  const clickedDelete = await clickMenuItemMatching(DELETE_TEXTS);
  if (!clickedDelete) {
    pressEscape();
    return { status: "error", title, error: "delete-option-not-found" };
  }
  const confirmedDelete = await clickDialogButtonMatching(DELETE_TEXTS);
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
  function getRows() {
    return Array.from(document.querySelectorAll('[aria-label^="More options for"]'));
  }

  const seen = new Set();
  getRows().forEach((b) => seen.add(b.getAttribute("aria-label")));

  // A scrollable container only exists when the list overflows the visible area (i.e. there
  // are enough conversations to need scrolling) — with a short list there's nothing to scroll,
  // and the count above is already complete.
  const container = Array.from(document.querySelectorAll("div")).find((e) => {
    const s = getComputedStyle(e);
    return (s.overflowY === "auto" || s.overflowY === "scroll") && e.scrollHeight > e.clientHeight + 50;
  });
  if (container) {
    container.scrollTop = 0;
    await sleep(200);
    getRows().forEach((b) => seen.add(b.getAttribute("aria-label")));

    let lastScrollTop = -1, stableRounds = 0, iterations = 0;
    while (stableRounds < 4 && iterations < 500) {
      container.scrollTop += 400;
      await sleep(120);
      getRows().forEach((b) => seen.add(b.getAttribute("aria-label")));
      if (container.scrollTop === lastScrollTop) stableRounds++; else stableRounds = 0;
      lastScrollTop = container.scrollTop;
      iterations++;
    }
    container.scrollTop = 0;
    await sleep(200);
  }

  return seen.size;
}
"""


def jitter(min_s, max_s):
    return random.uniform(min_s, max_s)


def is_brave_running():
    return any(
        "brave" in (proc.info.get("name") or "").lower()
        for proc in psutil.process_iter(["name"])
    )


def is_logged_out(page):
    return page.locator('input[name="pass"]').count() > 0 or "/login" in page.url


def has_conversation_list(page):
    return page.locator('[aria-label^="More options for"]').count() > 0


def goto_marketplace(page):
    # domcontentloaded, not the default "load" — Messenger keeps live
    # websocket connections open forever, so waiting for full network idle
    # would hang. wait_for_page_ready() below handles the actual SPA render.
    page.goto(MARKETPLACE_URL, wait_until="domcontentloaded", timeout=60000)


def wait_for_page_ready(page, timeout_s=45):
    """Facebook's SPA can take a long time to finish rendering, especially
    right after Brave launches cold with a full real profile — poll for an
    actual signal (login form or the conversation list) instead of guessing
    a fixed delay."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if is_logged_out(page):
            return "login"
        if has_conversation_list(page):
            return "list"
        time.sleep(0.5)
    return "timeout"


def find_brave_executable():
    """Locate the user's real Brave install. Override with BRAVE_PATH if it's
    somewhere non-standard."""
    override = os.environ.get("BRAVE_PATH")
    if override:
        return override

    if sys.platform == "win32":
        local_appdata = os.environ.get("LOCALAPPDATA", "")
        program_files = os.environ.get("PROGRAMFILES", r"C:\Program Files")
        program_files_x86 = os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")
        candidates = [
            os.path.join(local_appdata, "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
            os.path.join(program_files, "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
            os.path.join(program_files_x86, "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
        ]
    elif sys.platform == "darwin":
        candidates = ["/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"]
    else:
        candidates = ["/usr/bin/brave-browser", "/usr/bin/brave", "/snap/bin/brave"]

    return next((c for c in candidates if c and os.path.isfile(c)), None)


def find_brave_user_data_dir():
    """Locate Brave's real profile folder (cookies, saved logins, everything).
    Override with BRAVE_USER_DATA_DIR if it's somewhere non-standard."""
    override = os.environ.get("BRAVE_USER_DATA_DIR")
    if override:
        return override

    if sys.platform == "win32":
        local_appdata = os.environ.get("LOCALAPPDATA", "")
        return os.path.join(local_appdata, "BraveSoftware", "Brave-Browser", "User Data")
    elif sys.platform == "darwin":
        return str(Path.home() / "Library" / "Application Support" / "BraveSoftware" / "Brave-Browser")
    else:
        return str(Path.home() / ".config" / "BraveSoftware" / "Brave-Browser")


def wait_for_manual_login(page):
    """This script never handles your password in any form — if you're not
    already logged in via your real Brave profile, you log in by hand here."""
    print(
        "\nNot logged in yet. Log into Facebook/Messenger yourself in the Brave "
        "window that just opened — this script never sees or types your password."
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
    if is_brave_running():
        print(
            "Brave appears to already be running. Chromium-based browsers only allow "
            "one process per profile, so close every Brave window first — check the "
            "system tray and Task Manager for any lingering 'Brave' process, since a "
            "background instance can keep running after you close the last window — "
            "then re-run this script."
        )
        sys.exit(1)

    brave_path = find_brave_executable()
    if not brave_path:
        print(
            "Could not find Brave automatically. Set the BRAVE_PATH environment "
            "variable to your brave.exe location and try again."
        )
        sys.exit(1)
    user_data_dir = find_brave_user_data_dir()
    print(f"Using Brave at: {brave_path}")

    with sync_playwright() as p:
        try:
            context = p.chromium.launch_persistent_context(
                user_data_dir,
                executable_path=brave_path,
                headless=False,
                no_viewport=True,
            )
        except Exception:
            print(
                "Could not open Brave with your existing profile — this usually "
                "means Brave is still running somewhere. Close every Brave window "
                "(check the system tray / Task Manager) and try again."
            )
            raise

        page = context.pages[0] if context.pages else context.new_page()
        print("Loading Messenger Marketplace — this can take a while on a cold start...")
        goto_marketplace(page)
        page.wait_for_timeout(20000)  # flat wait for the first load before checking anything
        state = wait_for_page_ready(page)

        if state == "login":
            wait_for_manual_login(page)
            goto_marketplace(page)
            state = wait_for_page_ready(page)

        if state != "list":
            print(
                f"\nStill don't see the Marketplace inbox list (currently at {page.url}, "
                f"state={state}).\n"
                "If Facebook redirected you somewhere else (e.g. a single open "
                "conversation instead of the inbox list), navigate to the Marketplace "
                "inbox yourself in the Brave window now."
            )
            input("Press Enter here once the conversation list is visible... ")
            state = wait_for_page_ready(page, timeout_s=20)
            if state != "list":
                print("Still can't find any conversations — aborting.")
                context.close()
                sys.exit(1)

        run_cleanup(page)
        context.close()


if __name__ == "__main__":
    main()
