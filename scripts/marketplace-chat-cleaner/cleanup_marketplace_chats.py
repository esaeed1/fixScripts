#!/usr/bin/env python3
"""
Leaves and deletes conversations in your Messenger Marketplace inbox.

Every conversation is LEFT first and only then deleted — deleting on its own
just hides the thread on your side, it doesn't remove you from it. If a chat
offers no leave option at all it's still deleted, and the summary tells you how
many of those there were.

Before it touches anything, it shows your whole inbox as a numbered list and lets
you mark the chats to keep. A kept chat is never opened, never left and never
deleted. You can also pre-set them in keep.txt (one name, phone number or fragment
per line) or with --keep, and skip the list entirely with --no-pick.

Opens your actual, already-installed Brave browser using your real profile
(same cookies, same saved logins) instead of a separate managed browser — so
in the common case you're already logged into Facebook and nothing here ever
sees or types your password. If you're not logged in, it just pauses and lets
you log in yourself in the window that opens.

Setup (once):
    pip install -r requirements.txt

Usage:
    python cleanup_marketplace_chats.py --dry-run     # show what would happen
    python cleanup_marketplace_chats.py               # do it (asks to confirm)
    python cleanup_marketplace_chats.py --keep "555-0123" --keep "Jane"

To stop early: press Ctrl+C. It finishes whatever it's currently doing, then
stops cleanly and prints a summary.

See README.md for more on how this finds Brave and why it's designed this way.
"""

import argparse
import os
import random
import re
import sys
import time
from pathlib import Path

import psutil
from playwright.sync_api import sync_playwright

MARKETPLACE_URL = "https://www.messenger.com/marketplace/"
MAX_ITERATIONS = 400  # safety cap, well above any realistic inbox size
MAX_SAME_TITLE_REPEATS = 4
KEEP_FILE_DEFAULT = Path(__file__).with_name("keep.txt")

# Shared by the Python and JS sides so a keep pattern behaves identically in the
# preview and in the actual run: a pattern has to have at least this many digits
# before it's matched digits-only, otherwise something like "2024" would quietly
# match half your inbox.
MIN_PHONE_DIGITS = 7

# Runs once per conversation: picks the topmost conversation you didn't ask to keep,
# opens its menu, LEAVES it (mandatory whenever the option exists), then re-opens the
# menu and deletes it, confirming both dialogs. Kept as one evaluate() call (with
# retries/null-checks for Facebook's own flaky re-renders) so it can act on the DOM
# directly instead of round-tripping every micro-step through Playwright locators.
PROCESS_ONE_JS = """
async ([skipPatterns, skipExact, minPhoneDigits]) => {
  function sleep(ms) { return new Promise((r) => setTimeout(r, ms)); }
  function jitter(min, max) { return min + Math.random() * (max - min); }
  function textOf(el) {
    return ((el && (el.innerText || el.textContent)) || "").trim().toLowerCase();
  }

  // Facebook's wording drifts between "Leave chat", "Leave group" and "Leave conversation",
  // and the confirm dialog's button is usually shorter than the menu item that opened it
  // (often just "Leave"), so match on the leading verb rather than on whole phrases.
  function startsWithWord(text, word) {
    return text === word || text.startsWith(word + " ");
  }
  function isLeave(el) { return startsWithWord(textOf(el), "leave"); }
  function isDelete(el) { return startsWithWord(textOf(el), "delete"); }

  function digitsOnly(s) { return (s || "").replace(/[^0-9]/g, ""); }
  // A keep pattern matches either as a plain case-insensitive substring of the title, or —
  // for phone numbers — digits against digits, so "+1 (555) 555-0123" still matches a row
  // titled "555 0123" or "+15555550123".
  const exactSkips = new Set(skipExact || []);
  function isKept(title) {
    // Titles you picked by number are matched exactly, not as substrings — otherwise
    // keeping "Alexis - Free fridge" would also keep "Alexis - Free fridge 2".
    if (exactSkips.has(title)) return true;
    const lower = (title || "").toLowerCase();
    const titleDigits = digitsOnly(title);
    return (skipPatterns || []).some((raw) => {
      const p = String(raw == null ? "" : raw).trim();
      if (!p) return false;
      if (lower.includes(p.toLowerCase())) return true;
      let pDigits = digitsOnly(p);
      // Drop anything before the last 10 digits so a pattern written with a country code
      // ("+1 (555) 555-0123") still matches a row titled "555-0123", and vice versa.
      if (pDigits.length > 10) pDigits = pDigits.slice(-10);
      return pDigits.length >= minPhoneDigits && titleDigits.includes(pDigits);
    });
  }

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
  function titleOf(rowBtn) {
    return (rowBtn.getAttribute("aria-label") || "").replace("More options for", "").trim();
  }
  function getOpenMenuItems() {
    const items = Array.from(document.querySelectorAll('[role="menuitem"]'));
    if (items.length > 0) return items;
    // Some builds render the row menu as plain buttons inside the menu container.
    return Array.from(document.querySelectorAll('[role="menu"] [role="button"]'));
  }

  // Facebook streams these menus in: the first item appears well before the last one, so
  // checking as soon as *any* item exists sees a half-built menu and concludes there's no
  // Leave option when there is one — which is exactly how a chat ends up deleted without
  // being left. Wait until the item texts stop changing, or until a Leave item turns up,
  // before deciding what the menu contains.
  async function waitForMenu() {
    let lastSignature = null;
    let stableRounds = 0;
    for (let i = 0; i < 60; i++) {
      const items = getOpenMenuItems();
      if (items.length > 0) {
        if (items.some(isLeave)) return items;
        const signature = items.map(textOf).join("|");
        if (signature === lastSignature) {
          stableRounds++;
          if (stableRounds >= 3) return items;
        } else {
          stableRounds = 0;
        }
        lastSignature = signature;
      }
      await sleep(50);
    }
    return getOpenMenuItems();
  }

  function isVisible(el) {
    if (!el) return false;
    if (el.closest('[aria-hidden="true"]')) return false;
    const rect = el.getBoundingClientRect();
    if (rect.width < 1 || rect.height < 1) return false;
    const style = getComputedStyle(el);
    return style.visibility !== "hidden" && style.display !== "none";
  }
  // Facebook leaves a dismissed dialog mounted in the DOM, so the FIRST [role="dialog"] is
  // often a stale invisible one — which is why confirming Delete kept finding the previous
  // "Leave group" dialog's buttons and timing out. Only look at dialogs that are actually
  // on screen, newest (last in the DOM) first.
  function getOpenDialogs() {
    return Array.from(document.querySelectorAll('[role="dialog"]')).filter(isVisible);
  }
  function getDialogButtons() {
    const dialogs = getOpenDialogs();
    const buttons = [];
    for (let i = dialogs.length - 1; i >= 0; i--) {
      for (const b of dialogs[i].querySelectorAll('[role="button"], button')) {
        if (isVisible(b)) buttons.push(b);
      }
    }
    return buttons;
  }
  async function clickDialogButton(predicate) {
    for (let attempt = 0; attempt < 30; attempt++) {
      const matches = getDialogButtons().filter(predicate);
      if (matches.length > 0) {
        // Facebook nests a real <button> inside a div[role="button"], so one visible button
        // matches twice. Click the innermost match — the wrapper often isn't what carries
        // the handler. (This is why the log showed each button listed twice.)
        const target =
          matches.find((b) => !matches.some((other) => other !== b && b.contains(other))) ||
          matches[0];
        target.click();
        return true;
      }
      await sleep(80);
    }
    return false;
  }
  async function waitForDialogToClose() {
    for (let i = 0; i < 30; i++) {
      if (getOpenDialogs().length === 0) return true;
      await sleep(80);
    }
    return false;
  }
  function pressEscape() {
    for (const target of [document.activeElement, document.body]) {
      if (!target) continue;
      target.dispatchEvent(
        new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true })
      );
    }
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

  const target = rows.find((r) => !isKept(titleOf(r)));
  if (!target) return { status: "kept-only", remaining: rows.length };

  const title = titleOf(target);
  target.click();
  await sleep(jitter(120, 220));

  let items = await waitForMenu();
  const menuTexts = items.map(textOf).filter(Boolean);
  const leaveItem = items.find(isLeave);

  if (leaveItem) {
    // Leaving is mandatory whenever the option is offered — if any step here fails, bail out
    // with an error instead of falling through to delete, otherwise the thread just vanishes
    // from your side while you're still in it.
    leaveItem.click();
    const confirmedLeave = await clickDialogButton(isLeave);
    if (!confirmedLeave) {
      const dialogTexts = getDialogButtons().map(textOf).filter(Boolean);
      pressEscape();
      return { status: "error", title, error: "could-not-confirm-leave", menuTexts, dialogTexts };
    }
    if (!(await waitForDialogToClose())) {
      pressEscape();
      return { status: "error", title, error: "leave-dialog-did-not-close", menuTexts };
    }
    await sleep(jitter(250, 400));

    // Re-find THIS row by its exact title. Never fall back to whatever happens to be on top
    // now: that row could be one you asked to keep, and deleting it is unrecoverable.
    const again = getRowButtons().find((r) => titleOf(r) === title);
    if (!again) {
      // Leaving removed it from the list outright — there's nothing left to delete.
      return { status: "left", title, menuTexts };
    }
    again.click();
    await sleep(jitter(120, 220));
    items = await waitForMenu();
  }

  const deleteItem = items.find(isDelete);
  if (!deleteItem) {
    pressEscape();
    return { status: "error", title, error: "delete-option-not-found", menuTexts };
  }
  deleteItem.click();
  const confirmedDelete = await clickDialogButton(isDelete);
  if (!confirmedDelete) {
    const dialogTexts = getDialogButtons().map(textOf).filter(Boolean);
    pressEscape();
    return { status: "error", title, error: "could-not-confirm-delete", menuTexts, dialogTexts };
  }
  await waitForDialogToClose();
  return { status: "deleted", title, left: !!leaveItem, menuTexts };
}
"""

LIST_ALL_JS = """
async () => {
  function sleep(ms) { return new Promise((r) => setTimeout(r, ms)); }
  function getRows() {
    return Array.from(document.querySelectorAll('[aria-label^="More options for"]'));
  }
  function titleOf(rowBtn) {
    return (rowBtn.getAttribute("aria-label") || "").replace("More options for", "").trim();
  }

  const seen = new Set();
  getRows().forEach((b) => seen.add(titleOf(b)));

  // A scrollable container only exists when the list overflows the visible area (i.e. there
  // are enough conversations to need scrolling) — with a short list there's nothing to scroll,
  // and the list above is already complete.
  const container = Array.from(document.querySelectorAll("div")).find((e) => {
    const s = getComputedStyle(e);
    return (s.overflowY === "auto" || s.overflowY === "scroll") && e.scrollHeight > e.clientHeight + 50;
  });
  if (container) {
    container.scrollTop = 0;
    await sleep(200);
    getRows().forEach((b) => seen.add(titleOf(b)));

    let lastScrollTop = -1, stableRounds = 0, iterations = 0;
    while (stableRounds < 4 && iterations < 500) {
      container.scrollTop += 400;
      await sleep(120);
      getRows().forEach((b) => seen.add(titleOf(b)));
      if (container.scrollTop === lastScrollTop) stableRounds++; else stableRounds = 0;
      lastScrollTop = container.scrollTop;
      iterations++;
    }
    container.scrollTop = 0;
    await sleep(200);
  }

  return Array.from(seen);
}
"""


def jitter(min_s, max_s):
    return random.uniform(min_s, max_s)


def digits_only(s):
    return re.sub(r"[^0-9]", "", s or "")


def is_kept(title, patterns, exact=()):
    """Mirror of isKept() in PROCESS_ONE_JS — keep the two in step."""
    if title in exact:
        return True
    lower = (title or "").lower()
    title_digits = digits_only(title)
    for raw in patterns:
        pattern = (raw or "").strip()
        if not pattern:
            continue
        if pattern.lower() in lower:
            return True
        pattern_digits = digits_only(pattern)
        if len(pattern_digits) > 10:
            pattern_digits = pattern_digits[-10:]
        if len(pattern_digits) >= MIN_PHONE_DIGITS and pattern_digits in title_digits:
            return True
    return False


def load_keep_patterns(cli_patterns, keep_file):
    """Patterns from --keep plus keep.txt (one per line; a line starting with # is a comment)."""
    patterns = [p for p in (cli_patterns or []) if p.strip()]
    path = Path(keep_file) if keep_file else KEEP_FILE_DEFAULT
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                patterns.append(line)
    elif keep_file:
        print(f"Keep file not found: {path}")
        sys.exit(1)
    return patterns


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


def list_conversations(page):
    return page.evaluate(LIST_ALL_JS)


def process_one_conversation(page, skip_patterns, skip_exact):
    return page.evaluate(PROCESS_ONE_JS, [skip_patterns, skip_exact, MIN_PHONE_DIGITS])


def parse_selection(raw, count):
    """'1 4', '1,4', '1-3 7' -> {1, 4} / {1, 2, 3, 7}. Raises ValueError on anything else."""
    chosen = set()
    for chunk in re.split(r"[\s,]+", raw.strip()):
        if not chunk:
            continue
        span = re.fullmatch(r"(\d+)\s*-\s*(\d+)", chunk)
        if span:
            low, high = sorted((int(span.group(1)), int(span.group(2))))
            numbers = range(low, high + 1)
        elif chunk.isdigit():
            numbers = [int(chunk)]
        else:
            raise ValueError(f"don't understand {chunk!r}")
        for n in numbers:
            if not 1 <= n <= count:
                raise ValueError(f"{n} is not in the list (pick between 1 and {count})")
            chosen.add(n)
    return chosen


def choose_keepers(titles, keep_patterns):
    """Show the inbox and let you mark chats to keep, before anything has been touched.

    This runs before the first click of the run — a chat you pick here is never opened,
    never left and never deleted."""
    print(f"\nFound {len(titles)} Marketplace conversations:\n")
    width = len(str(len(titles)))
    for i, title in enumerate(titles, 1):
        tag = "   [keep]" if is_kept(title, keep_patterns) else ""
        print(f"  {i:>{width}}. {title}{tag}")
    if any(is_kept(t, keep_patterns) for t in titles):
        print("\n  [keep] = already matched by keep.txt / --keep; those stay kept either way.")

    print("\nType the numbers of any other chats to KEEP (e.g. 1 4 7, or 2-5).")
    while True:
        try:
            raw = input("Numbers to keep (Enter for none): ")
        except EOFError:
            return []
        try:
            chosen = parse_selection(raw, len(titles))
        except ValueError as e:
            print(f"  {e} — try again.")
            continue
        return [titles[n - 1] for n in sorted(chosen)]


def remember_keepers(picked, keep_file):
    """Offer to write the picked titles to keep.txt, so a re-run keeps them without you
    picking again — worth it if a run gets interrupted partway through."""
    if not picked:
        return
    path = Path(keep_file) if keep_file else KEEP_FILE_DEFAULT
    answer = input(f"Also save these {len(picked)} to {path.name} for future runs? [y/N]: ")
    if answer.strip().lower() not in ("y", "yes"):
        return
    with path.open("a", encoding="utf-8") as f:
        f.write("\n")
        for title in picked:
            f.write(title + "\n")
    print(f"Saved to {path}. Saved lines match as substrings, so a near-identical title is kept too.")


def show_split(titles, kept, targets, keep_patterns):
    print(f"\nOf {len(titles)} conversations:")
    if kept:
        print(f"\nKEEPING these {len(kept)} — never opened, left or deleted:")
        for t in kept:
            print(f"  - {t}")
    else:
        print("\nNothing is being kept — no keep pattern matched and nothing was picked.")
    print(f"\nWill leave + delete these {len(targets)}:")
    for t in targets:
        print(f"  - {t}")
    print()


def plan(page, keep_patterns, interactive=True, keep_file=None):
    """Read the inbox, let you mark chats to keep, and split it into keep vs leave+delete.
    Nothing is clicked in here — all of this happens before the run starts."""
    print("Reading the conversation list, please wait...")
    titles = list_conversations(page)
    keep_exact = []
    if titles and interactive:
        keep_exact = choose_keepers(titles, keep_patterns)
        remember_keepers(keep_exact, keep_file)
    kept = [t for t in titles if is_kept(t, keep_patterns, keep_exact)]
    targets = [t for t in titles if not is_kept(t, keep_patterns, keep_exact)]
    show_split(titles, kept, targets, keep_patterns)
    return titles, kept, targets, keep_exact


def run_cleanup(page, keep_patterns, assume_yes=False, interactive=True, keep_file=None):
    titles, kept, targets, keep_exact = plan(page, keep_patterns, interactive, keep_file)
    if not targets:
        print("Nothing to do.")
        return

    if not assume_yes:
        answer = input(f"Leave and delete {len(targets)} conversations? Type yes to continue: ")
        if answer.strip().lower() not in ("y", "yes"):
            print("Cancelled. Nothing was changed.")
            return

    print("Starting cleanup...")
    deleted_titles = []
    left_only = []
    deleted_without_leaving = []
    skipped = []
    errors = []
    # Conversations that keep failing get added to the skip list sent into the page, so the
    # loop actually moves past them instead of re-picking the same top row forever.
    failed_titles = []
    last_title_seen = None
    same_title_repeats = 0
    stagnant_empty_rounds = 0
    total_iterations = 0
    menu_reported = False

    try:
        while total_iterations < MAX_ITERATIONS:
            total_iterations += 1

            try:
                result = process_one_conversation(
                    page, keep_patterns, keep_exact + failed_titles
                )
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

            if not menu_reported and result.get("menuTexts"):
                # Printed once so you can see Facebook's actual menu wording for yourself if
                # the leave step ever stops matching again.
                print(f"Menu options seen: {result['menuTexts']}")
                menu_reported = True

            if status == "kept-only":
                print(f"Only kept conversations remain ({result.get('remaining')}). Done.")
                break

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
                print(f'Skipping "{title}" after repeated failures — moving on.')
                skipped.append(title)
                if title:
                    failed_titles.append(title)
                same_title_repeats = 0
                last_title_seen = None
                time.sleep(0.5)
                continue

            if status == "deleted":
                deleted_titles.append(title)
                if not result.get("left"):
                    deleted_without_leaving.append(title)
                marker = "left + deleted" if result.get("left") else "deleted (no leave option)"
                print(f"{marker} ({len(deleted_titles)}): {title}")
            elif status == "left":
                left_only.append(title)
                print(f"left (row vanished, nothing left to delete): {title}")
            elif status == "error":
                print(f'"{title}": {result.get("error")}')
                if result.get("dialogTexts"):
                    print(f"  dialog buttons seen: {result['dialogTexts']}")
                errors.append({"title": title, "error": result.get("error")})
                # Clear any menu or dialog the failed attempt left hanging open, so the next
                # iteration starts from a clean page.
                try:
                    page.keyboard.press("Escape")
                except Exception:
                    pass

            time.sleep(jitter(0.25, 0.5))
    except KeyboardInterrupt:
        print("\nStopped by user (Ctrl+C).")

    if total_iterations >= MAX_ITERATIONS:
        print("Hit the safety iteration cap — stopping. Re-run the script to continue.")

    print("---- Marketplace cleanup summary ----")
    print(f"Found at start: {len(titles)}")
    print(f"Kept (never touched): {len(kept)}", kept if kept else "")
    print(f"Left + deleted: {len(deleted_titles) - len(deleted_without_leaving)}")
    if left_only:
        print(f"Left (row disappeared before delete): {len(left_only)}", left_only)
    if deleted_without_leaving:
        print(
            f"Deleted with no leave option offered: {len(deleted_without_leaving)}",
            deleted_without_leaving,
        )
    if skipped:
        print(f"Skipped (repeated failures): {len(skipped)}", skipped)
    if errors:
        print(f"Errors recovered from: {len(errors)}", errors)
    print("Deleted titles:", deleted_titles)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Leave and delete Messenger Marketplace conversations.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Keep patterns match a conversation title case-insensitively as a substring,\n"
            "or digits against digits for phone numbers, so '+1 (555) 555-0123' also\n"
            "matches '555 0123' and '+15555550123'."
        ),
    )
    parser.add_argument(
        "--keep",
        action="append",
        default=[],
        metavar="PATTERN",
        help="name, phone number or fragment to never leave/delete (repeatable)",
    )
    parser.add_argument(
        "--keep-file",
        metavar="PATH",
        help=f"file of keep patterns, one per line (default: {KEEP_FILE_DEFAULT.name} if present)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="list what would be kept and what would be deleted, then exit without changing anything",
    )
    parser.add_argument(
        "--no-pick",
        action="store_true",
        help="don't show the numbered pick-what-to-keep list; use keep.txt/--keep only",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="skip both the pick list and the confirmation prompt (non-interactive)",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    keep_patterns = load_keep_patterns(args.keep, args.keep_file)
    if keep_patterns:
        print(f"Keeping conversations matching: {keep_patterns}")
    else:
        print("No keep patterns set — every Marketplace conversation is fair game.")

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

        interactive = not (args.no_pick or args.yes)
        if args.dry_run:
            plan(page, keep_patterns, interactive, args.keep_file)
            print("Dry run — nothing was changed. Re-run without --dry-run to do it.")
        else:
            run_cleanup(
                page,
                keep_patterns,
                assume_yes=args.yes,
                interactive=interactive,
                keep_file=args.keep_file,
            )
        context.close()


if __name__ == "__main__":
    main()
