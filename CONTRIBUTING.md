# Contributing

Thanks for wanting to add a fix! This repo stays useful by keeping every script small, self-contained, and documented well enough that someone with zero context can run it safely.

## Adding a new script

1. **Create a folder** under `scripts/` named after the problem it solves, using kebab-case (e.g. `scripts/bluetooth-reset/`, not `scripts/BluetoothFix/`).
2. **Keep it self-contained.** If it's a PowerShell script meant to be double-clicked, pair it with a small `.bat` launcher (see `scripts/usb-dongle-reset/RestartHeadset.bat` for the pattern) so users don't have to fight PowerShell's execution policy or right-click menus.
3. **Request the minimum permissions needed.** Only prompt for Administrator rights (UAC) if the script actually requires them.
4. **Write a folder-level `README.md`** covering:
   - What problem this fixes and why it happens
   - Requirements (OS version, anything it depends on)
   - Step-by-step usage
   - Any known limitations
5. **Don't hardcode machine-specific values.** If a script needs to remember something about the user's setup (like a specific device ID), have it discover and save that on first run rather than requiring manual editing.
6. **Add a row to the root `README.md`** table pointing to your new folder.
7. Ignore any files your script generates at runtime (config files, logs) by adding a pattern to `.gitignore` rather than committing them.

## Style

- Prefer PowerShell over raw batch for any logic beyond "launch this file."
- Comment the non-obvious parts — assume the next reader has never seen the underlying Windows API/quirk before.
- Fail loudly and clearly. If something goes wrong, print a plain-English explanation, not just a stack trace.

## Pull requests

Small, focused PRs are easiest to review — one script or one fix per PR. Open an issue first if you're not sure whether a script fits the scope of this repo.
