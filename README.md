# fixScripts

A growing collection of small scripts that fix annoying, everyday problems — the kind of thing you Google, forget the fix for, and Google again three months later. Each fix lives in its own folder under `scripts/` with its own short README, so you can grab just the one you need.

Most of these are Windows utility scripts (PowerShell + Batch, no installs required). A few are browser scripts you paste into DevTools — those work on any OS, in any Chromium-based browser.

## Available scripts

| Script | What it does |
|---|---|
| [`usb-dongle-reset`](scripts/usb-dongle-reset) | Resets a USB wireless dongle (headset, mouse receiver, etc.) in software — no need to physically unplug it. Fixes issues like a wireless headset's audio quality dropping once the microphone is used. |
| [`window-finder`](scripts/window-finder) | Lists every open window — including minimized ones or ones parked off-screen — and jumps straight to the one you pick. Fixes "I have a ton of windows/monitors open and can't find the one I want." |
| [`marketplace-chat-cleaner`](scripts/marketplace-chat-cleaner) | A browser console script that leaves and deletes every conversation in your Messenger Marketplace inbox in one pass, instead of clicking through each one by hand. |

More scripts will be added over time — see [Contributing](#contributing) if you want to add your own.

## What each script actually does

**usb-dongle-reset** — Wireless dongles (headsets, mouse/keyboard receivers) sometimes get "stuck" in a degraded state — most commonly a headset's audio quality dropping once its mic becomes active, because the dongle's radio link has to squeeze in the mic signal too. The normal fix is unplugging and replugging the dongle so it redoes its wireless handshake. This script does that in software: it disables and re-enables the device through Windows' device manager APIs, so you don't need physical access to the port. It remembers multiple dongles by nickname and can reset one, several, or all of them from a menu.

**window-finder** — Enumerates every open window on the PC (via the Win32 API), including ones that are minimized or positioned off-screen (e.g. because a monitor got disconnected), and shows them as a searchable numbered list. Picking one restores it if minimized, forces it to the foreground even past Windows' normal "don't let background apps steal focus" block, nudges it back on-screen if it's parked somewhere invisible, and blinks its taskbar icon so it's easy to spot.

**marketplace-chat-cleaner** — Pasted into the browser console while viewing the Messenger Marketplace inbox, this walks the conversation list from the top: it opens each conversation's options menu, leaves it (if a "Leave group" option is offered), deletes it, confirms both actions, and moves to the next one — scrolling to force more conversations to load in as the list empties. It has a stuck-conversation safeguard (skips a conversation after repeated failures instead of looping forever), randomized human-like pacing between actions, a manual stop switch (`window.__stopMarketplaceCleanup = true`), and prints a summary of what was deleted when it finishes.

## Requirements

**Windows scripts** (`usb-dongle-reset`, `window-finder`):
- Windows 10 or 11
- PowerShell 5.1+ (included by default on Windows)
- Some require Administrator rights; those prompt for permission automatically when you run them.

**Browser scripts** (`marketplace-chat-cleaner`):
- Any Chromium-based browser (Chrome, Brave, Edge) — run via DevTools, works on Windows, Mac, or Linux.
- No installs — just paste into the Console tab.

## Usage

Each script folder has its own README with specific instructions, but the general pattern is:

- **Windows scripts**: download or clone this repo, open the script's folder under `scripts/`, and double-click the `.bat` file (it calls the matching PowerShell script for you).
- **Browser scripts**: open the relevant page in your browser, open DevTools (F12) → Console tab, paste the script's `.js` file contents, and press Enter.

```bash
git clone https://github.com/esaeed1/fixScripts.git
```

Or just download the ZIP from the green "Code" button on GitHub if you don't use git.

## Contributing

Pull requests welcome. If you'd like to add a script:

1. Create a new folder under `scripts/` named for what it fixes (kebab-case, e.g. `wifi-adapter-reset`).
2. Include the script(s) plus a short `README.md` in that folder explaining what it fixes, requirements, and how to run it.
3. Add a row for it in the table above, plus a short explanation under "What each script actually does."

See [CONTRIBUTING.md](CONTRIBUTING.md) for more detail.

## License

MIT — see [LICENSE](LICENSE). Use, modify, and share freely.
