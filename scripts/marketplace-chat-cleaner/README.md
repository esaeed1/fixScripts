# marketplace-chat-cleaner

Leaves and deletes every conversation in your Messenger Marketplace inbox automatically — no need to click through each chat one by one, and no need to re-run it manually as more chats load in.

Opens your **actual, already-installed Brave browser** using your **real profile** — same cookies, same saved logins as when you open Brave normally. In the common case you're already logged into Facebook from everyday use, so the script never sees or handles a password at all. If you're not logged in, it just pauses and lets you log in yourself in the window that opens.

## What it does

1. Finds the scrollable chat-list container on the page automatically (by checking which element actually scrolls), rather than depending on a specific CSS class name, which Facebook changes often.
2. Grabs the "More options" button for whichever conversation is currently at the top of the list.
3. Opens that conversation's menu. If a **Leave group** option exists, clicks it and confirms the follow-up dialog.
4. Re-opens the options menu for that same conversation and clicks **Delete chat**, confirming that dialog too.
5. Moves on to whatever is now the new top conversation and repeats — scrolling to force more chats to load in as the list empties out.
6. Keeps going until the inbox is confirmed empty (double-checked 3 times, in case of a temporary loading pause) or it hits a safety cap of 400 conversations processed in a single run.

## Built-in safety features

- **Stuck-conversation protection** — if the same conversation title comes up 4 times in a row (meaning delete/leave keeps failing on it), the script skips it and moves on instead of looping forever.
- **Error recovery** — a DOM hiccup (Facebook re-rendering mid-click, a menu that's slow to open, a container reference going stale) is caught, logged, and the script moves on to the next conversation instead of the whole run dying silently.
- **Randomized pacing** — waits a short, randomized amount of time between conversations (roughly a quarter to half a second) and between individual clicks, instead of firing actions back-to-back with no delay.
- **Manual stop switch** — press Ctrl+C at any point; it finishes whatever it's currently doing and then stops cleanly.
- **Summary report** — prints a final count of how many chats were deleted, their titles, and anything it had to skip or error on.

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
python cleanup_marketplace_chats.py
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

## Notes

- This **permanently deletes** chat history — there's no undo once a conversation is deleted. Consider watching the first few go through before walking away.
- This automates actions on your own account by interacting with the page itself (it doesn't scrape or touch anyone else's data), but Meta's terms don't technically permit scripted interaction with their site. Run at a reasonable pace, it behaves like normal manual use, but there's always some chance of a temporary rate-limit or verification prompt.
- Facebook's page structure changes periodically. If it stops finding conversations or menu items, right-click → Inspect on a conversation row's "..." button and check its `aria-label` — that's usually the first thing to change.
- Since this runs your actual Brave against your actual profile, closing the script's Brave window mid-run is equivalent to closing your browser normally — nothing is lost beyond the run stopping.
