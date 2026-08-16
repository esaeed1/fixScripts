# marketplace-chat-cleaner

Leaves and deletes every conversation in your Messenger Marketplace inbox in one paste — no need to click through each chat one by one, and no need to re-run it manually as more chats load in.

## What it does

1. Finds the scrollable chat-list container on the page automatically (by checking which element actually scrolls), rather than depending on a specific CSS class name, which Facebook changes often.
2. Grabs the "More options" button for whichever conversation is currently at the top of the list.
3. Opens that conversation's menu. If a **Leave group** option exists, clicks it and confirms the follow-up dialog.
4. Re-opens the options menu for that same conversation and clicks **Delete chat**, confirming that dialog too.
5. Moves on to whatever is now the new top conversation and repeats — scrolling to force more chats to load in as the list empties out.
6. Keeps going until the inbox is confirmed empty (double-checked 3 times, in case of a temporary loading pause) or it hits a safety cap of 400 conversations processed in a single run.

## Built-in safety features

- **Stuck-conversation protection** — if the same conversation title comes up 4 times in a row (meaning delete/leave keeps failing on it), the script skips it and moves on instead of looping forever.
- **Randomized pacing** — waits a short, randomized amount of time between conversations (roughly a quarter to half a second) and between individual clicks, instead of firing actions back-to-back with no delay. This is fast — if you'd rather it look more like manual browsing, you can raise the numbers passed to `jitter(...)` throughout the script.
- **Manual stop switch** — run `window.__stopMarketplaceCleanup = true` in the console at any time; it finishes whatever it's currently doing and then stops cleanly.
- **Summary report** — prints a final count of how many chats were deleted, their titles, and anything it had to skip.

## Requirements

- Any Chromium-based browser (Chrome, Brave, Edge) — this runs through DevTools, not as an installed extension.
- You must be logged into Messenger and viewing `https://www.messenger.com/marketplace/` (the Marketplace inbox **list**, not a single open chat).

## Usage

1. Go to `https://www.messenger.com/marketplace/`.
2. Open DevTools (F12) → Console tab.
3. Paste the entire script and press Enter.
4. Watch the console log as it works through your inbox.
5. To stop early: type `window.__stopMarketplaceCleanup = true` and press Enter.

## Notes

- This **permanently deletes** chat history — there's no undo once a conversation is deleted. Consider watching the first few go through before walking away.
- This automates actions on your own account by interacting with the page itself (it doesn't scrape or touch anyone else's data), but Meta's terms don't technically permit scripted interaction with their site. Run at a reasonable pace, it behaves like normal manual use, but there's always some chance of a temporary rate-limit or verification prompt.
- Facebook's page structure changes periodically. If it stops finding conversations or menu items, right-click → Inspect on a conversation row's "..." button and check its `aria-label` — that's usually the first thing to change.
