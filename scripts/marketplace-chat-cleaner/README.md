# marketplace-chat-cleaner

Leaves and deletes every conversation in your Messenger Marketplace inbox automatically — no need to click through each chat one by one, and no need to re-run it manually as more chats load in.

Uses [Playwright](https://playwright.dev/python/) to drive a real, persistent Chromium profile: it logs you in the first time, then reuses that saved session on every run after, so most runs never touch the login form at all.

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
- A Chromium browser binary managed by Playwright (installed via the steps below — this is separate from any Chrome/Edge you already have).

## Setup (once)

```bash
pip install -r requirements.txt
playwright install chromium
```

## Credentials

The script never has your password written into it. On the first run (or if the saved session ever expires), it asks for your email and password:

- Set `FB_EMAIL` and `FB_PASSWORD` environment variables (or copy `.env.example` to `.env` and fill it in — `.env` is gitignored), **or**
- Just leave them unset — it'll prompt you interactively, with the password hidden as you type.

## Usage

```bash
python cleanup_marketplace_chats.py
```

- A real Chromium window opens (not headless) so you can watch it and step in if needed.
- **First run only:** if you're not already logged in, it navigates to the Facebook login page, fills in your credentials, and submits. If Facebook shows a security check, a code prompt, or a "save this browser" screen, handle it in the browser window, then press Enter at the prompt in your terminal to continue. Your session is then saved into a local `.browser-profile/` folder (gitignored) and reused on every future run — so this login flow typically only happens once.
- To stop early: press **Ctrl+C** in the terminal. It finishes whatever it's currently doing, then stops cleanly and prints the summary.

## Why automating login is reasonable here (but still not risk-free)

A Playwright script is a real, persistent program — it isn't destroyed by page navigation the way a DevTools console paste would be, so it can actually carry you through login and into the cleanup in one run. A few choices keep this from being reckless:

- **Credentials are never stored in a file.** They come from environment variables you control or a masked interactive prompt, never hardcoded.
- **It only logs in once.** After that, the saved browser profile keeps you signed in like a normal browser would, so subsequent runs don't touch the login form at all.
- **It's not headless.** You can see exactly what it's doing and step in for any 2FA/checkpoint yourself.

That said, Meta's login flow is the most heavily monitored part of the site for automated activity, more so than clicking around an inbox you're already signed into. Scripted logins can still occasionally trigger a security checkpoint even for the account owner. If that happens, just complete it in the visible browser window — the script waits for you to confirm before continuing.

## Notes

- This **permanently deletes** chat history — there's no undo once a conversation is deleted. Consider watching the first few go through before walking away.
- This automates actions on your own account by interacting with the page itself (it doesn't scrape or touch anyone else's data), but Meta's terms don't technically permit scripted interaction with their site. Run at a reasonable pace, it behaves like normal manual use, but there's always some chance of a temporary rate-limit or verification prompt.
- Facebook's page structure changes periodically. If it stops finding conversations or menu items, right-click → Inspect on a conversation row's "..." button and check its `aria-label` — that's usually the first thing to change.
- The saved session lives in `.browser-profile/` next to the script. Delete that folder to force a fresh login (e.g. if you want to switch accounts).
