# marketplace-chat-cleaner

Leaves and then deletes conversations in your Messenger Marketplace inbox automatically — minus any you list in `keep.txt` — no need to click through each chat one by one, and no need to re-run it manually as more chats load in.

Opens your **actual, already-installed Brave browser** using your **real profile** — same cookies, same saved logins as when you open Brave normally. In the common case you're already logged into Facebook from everyday use, so the script never sees or handles a password at all. If you're not logged in, it just pauses and lets you log in yourself in the window that opens.

## What it does

1. Reads your whole conversation list up front and shows it to you as a numbered list, so you can mark the chats to keep **before it touches anything** (see [Keeping chats](#keeping-chats) below). It then shows the resulting keep / delete split and asks you to confirm.
2. Finds every conversation row on the page (by its "More options" button). If there are enough conversations to overflow the visible list, it also finds the scrollable container so it can scroll to force more to load in — but it doesn't require one, since a short list that fits on screen without scrolling is normal and still has real conversations in it.
3. Grabs the "More options" button for the topmost conversation that **isn't** on your keep list.
4. Opens that conversation's menu and waits for it to finish rendering. If a **Leave** option exists (Facebook words it "Leave chat", "Leave group" or "Leave conversation" depending on the thread), it clicks it and confirms the follow-up dialog — **leaving always happens first**, because deleting on its own only hides the thread on your side, it doesn't remove you from it.
5. Re-opens the options menu for that same conversation and clicks **Delete chat**, confirming that dialog too.
6. Moves on to the next non-kept conversation and repeats — scrolling to force more chats to load in as the list empties out, if there's a scrollable container to begin with.
7. Keeps going until only kept conversations remain, the inbox is confirmed empty (double-checked 3 times, in case of a temporary loading pause), or it hits a safety cap of 400 conversations processed in a single run.

## Keeping chats

A kept chat is **never opened, never left and never deleted**.

### Pick them when you run it

By default the script shows your inbox as a numbered list before it touches anything, and waits for you to say which ones to keep:

```
Found 7 Marketplace conversations:

  1. Alexis · Free fridge
  2. Jr. · HP Touch Screen
  3. Farmer · Laundromat
  4. Karen · New – men's
  5. Dinas · NEW 2,000lb Mini Skid Steer no start
  6. Donald · Dewalt Flexvolt 9Ah
  7. Sam · Office chair

Type the numbers of any other chats to KEEP (e.g. 1 4 7, or 2-5).
Numbers to keep (Enter for none): 1 4
```

Accepts single numbers, ranges, spaces or commas — `1 4 7`, `1,4,7`, `2-5`, `1, 3-4, 7` all work. Press Enter on its own to keep nothing. Bad input is rejected and re-asked rather than guessed at. Picked titles are matched **exactly**, so keeping `Alexis · Free fridge` won't also keep `Alexis · Free fridge 2`.

It then offers to save your picks to `keep.txt` so you don't have to pick again if the run gets interrupted, and shows the final split for confirmation before the first click.

Use `--no-pick` to skip the list (keep.txt / `--keep` still apply), or `--yes` to skip the list *and* the confirmation for a fully non-interactive run.

### Or pre-set them

`keep.txt` next to the script, one per line (`#` starts a comment line):

```
+1 (555) 555-0123
Jane
```

…or on the command line, repeating `--keep` as many times as you need:

```bash
python cleanup_marketplace_chats.py --keep "555-0123" --keep "Jane"
```

All three sources combine — keep.txt, `--keep`, and whatever you pick from the list. Pre-set patterns show up tagged `[keep]` in the numbered list so you can see they're already covered. A pattern matches a conversation title two ways:

- **as text** — case-insensitive substring, so `Jane` keeps "Jane Doe".
- **as a phone number** — digits against digits, ignoring formatting and any country code, so `+1 (555) 555-0123` also keeps a chat titled `555-0123`, `+15555550123` or `(555) 555 0123 — Bike`. A pattern needs at least 7 digits before it's matched this way, so something like `2024` can't accidentally match a phone number.

The title a pattern matches against is whatever Messenger shows in the inbox row — usually the other person's name, and only their number if you don't have them saved as a contact. `--dry-run` shows you the exact titles, and the same numbered pick list, without changing anything:

```bash
python cleanup_marketplace_chats.py --dry-run
```

## Built-in safety features

- **Stuck-conversation protection** — if the same conversation title comes up 4 times in a row (meaning delete/leave keeps failing on it), the script adds it to the skip list for the rest of the run and moves on to the next one instead of looping on it forever.
- **Error recovery** — a DOM hiccup (Facebook re-rendering mid-click, a menu that's slow to open, a container reference going stale) is caught, logged, and the script moves on to the next conversation instead of the whole run dying silently.
- **Leave always comes first, and is never skipped silently** — if a conversation offers a Leave option, leaving is mandatory before delete is attempted. If clicking or confirming that step fails, the conversation is reported as an error instead of falling through to delete, so a chat never gets deleted locally while you're still in the thread. The script waits for Facebook's menu to finish rendering before deciding whether a Leave option exists, and matches on the leading word ("leave…") rather than exact phrases, because Facebook's wording drifts and the confirm button is usually shorter than the menu item that opened it. The summary counts how many chats were left + deleted versus deleted with no leave option offered, and the first run prints the actual menu wording it saw.
- **Kept chats are never a fallback target** — after leaving a chat, the script re-finds that exact row by title to delete it. If the row is already gone (leaving sometimes removes it outright), it reports "left" and moves on rather than falling back to whatever is now at the top of the list, which could be a chat you asked to keep.
- **Randomized pacing** — waits a short, randomized amount of time between conversations (roughly a quarter to half a second) and between individual clicks, instead of firing actions back-to-back with no delay.
- **Manual stop switch** — press Ctrl+C at any point; it finishes whatever it's currently doing and then stops cleanly.
- **You choose before anything is touched** — the numbered pick list and the keep / delete split are both shown before the first click, and the run waits for you to type `yes` (unless you pass `--yes`). `--dry-run` shows the same thing and then exits.
- **Picked titles match exactly** — a chat you keep by number is matched on its full title, not as a substring, so keeping one chat can't silently keep or skip a similarly-named one.
- **Summary report** — prints a final count of how many chats were left + deleted, how many were deleted with no leave option offered, what was kept, and anything it had to skip or error on.

## Requirements

- Python 3.9+
- Brave already installed at a normal location (or set `BRAVE_PATH`/`BRAVE_USER_DATA_DIR` — see below).
- **Brave must be fully closed before you run the script.** Chromium-based browsers only allow one process per profile, so the script launches its own Brave process against your real profile folder. The script checks for a running Brave process first and refuses to start with a clear message if it finds one — closing just the last window isn't always enough, since Brave can keep a background process alive after that; check the system tray and Task Manager for a lingering `brave.exe`/`Brave` process too.

## Setup (once)

```bash
pip install -r requirements.txt
```

No `playwright install` step needed — this points Playwright at your existing Brave install instead of downloading a separate managed browser.

## Usage

```bash
python cleanup_marketplace_chats.py --dry-run   # see what would happen
python cleanup_marketplace_chats.py             # pick what to keep, confirm, then run
python cleanup_marketplace_chats.py --no-pick   # skip the pick list, use keep.txt only
```

- Your real Brave opens with your real profile. If you're already logged into Facebook there (likely, from normal use), it goes straight into cleanup.
- If you're not logged in, the script pauses and tells you so — log in yourself in that window (2FA, checkpoints, saved passwords, whatever you'd normally do), then press Enter in the terminal to continue. The script itself never reads, stores, or types your password.
- Facebook's Messenger is a heavy, slow-loading SPA, and a freshly launched Brave process loading a full real profile makes that worse. On the very first navigation, the script waits a flat 20 seconds before checking anything, then polls for the actual page content (up to 45 more seconds) instead of guessing further. If it still doesn't recognize the page after that (for example, Facebook opened a specific conversation instead of the Marketplace inbox list), it tells you the current URL and pauses so you can navigate to the right place yourself, then continue with Enter.
- To stop early: press **Ctrl+C** in the terminal. It finishes whatever it's currently doing, then stops cleanly and prints the summary.

### If Brave isn't found automatically

It checks the standard install locations for your OS. If yours is somewhere else, set:

- `BRAVE_PATH` — full path to the Brave executable (`brave.exe` on Windows).
- `BRAVE_USER_DATA_DIR` — full path to Brave's profile folder (its "User Data" directory), if that's non-standard too.

## Why this design

- **Never handles credentials.** By using your real, already-logged-in Brave profile instead of a fresh browser, there's usually nothing to log into at all — and when there is, a human (you) does it by hand in a real, visible window. No password ever passes through the script in any form.
- **Not headless.** You can see exactly what it's doing at all times and step in for anything unexpected.
- Facebook's login flow is the most heavily monitored part of the site for automated activity — this design sidesteps scripting it entirely rather than trying to do it "safely."

## If it still seems to do nothing

Run the read-only diagnostic instead of the real script:

```bash
python diagnose.py
```

It opens Brave the same way, navigates to the Marketplace inbox, waits the same way — but never clicks Leave or Delete. It prints the final URL, whether it thinks you're logged in, how many conversation rows it can actually see, and saves a screenshot (`diagnose-screenshot.png`, gitignored) so you can compare what it sees against what you see. Safe to run any time.

(This is also how the "opened Brave but nothing happened" bug got found and fixed: with a short inbox — few enough conversations that the list doesn't need to scroll — there's no scrollable container on the page at all, and the script used to require finding one before it would even look for conversation rows. It now finds rows directly and only uses a scrollable container opportunistically, when one exists, to load in more.)

## Notes

- This **permanently deletes** chat history — there's no undo once a conversation is deleted. Run `--dry-run` first, and consider watching the first few go through before walking away.
- This automates actions on your own account by interacting with the page itself (it doesn't scrape or touch anyone else's data), but Meta's terms don't technically permit scripted interaction with their site. Run at a reasonable pace, it behaves like normal manual use, but there's always some chance of a temporary rate-limit or verification prompt.
- Facebook's page structure changes periodically. If it stops finding conversations or menu items, right-click → Inspect on a conversation row's "..." button and check its `aria-label` — that's usually the first thing to change.
- Since this runs your actual Brave against your actual profile, closing the script's Brave window mid-run is equivalent to closing your browser normally — nothing is lost beyond the run stopping.
