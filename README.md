# fixScripts

A growing collection of small Windows scripts that fix annoying, everyday PC problems — the kind of thing you Google, forget the fix for, and Google again three months later. Each fix lives in its own folder under `scripts/` with its own short README, so you can grab just the one you need.

No installs, no dependencies beyond what Windows already ships with (PowerShell + Batch). Double-click and go.

## Available scripts

| Script | What it does |
|---|---|
| [`usb-dongle-reset`](scripts/usb-dongle-reset) | Resets a USB wireless dongle (headset, mouse receiver, etc.) in software — no need to physically unplug it. Fixes issues like a wireless headset's audio quality dropping once the microphone is used. |
| [`window-finder`](scripts/window-finder) | Lists every open window — including minimized ones or ones parked off-screen — and jumps straight to the one you pick. Fixes "I have a ton of windows/monitors open and can't find the one I want." |

More scripts will be added over time — see [Contributing](#contributing) if you want to add your own.

## Requirements

- Windows 10 or 11
- PowerShell 5.1+ (included by default on Windows)
- Some scripts require Administrator rights; those will prompt for permission automatically when you run them.

## Usage

Each script folder has its own README with specific instructions, but the general pattern is:

1. Download or clone this repository.
2. Open the folder for the script you want under `scripts/`.
3. Double-click the `.bat` file to run it (it will call the matching PowerShell script for you).

```bash
git clone https://github.com/esaeed1/fixScripts.git
```

Or just download the ZIP from the green "Code" button on GitHub if you don't use git.

## Contributing

Pull requests welcome. If you'd like to add a script:

1. Create a new folder under `scripts/` named for what it fixes (kebab-case, e.g. `wifi-adapter-reset`).
2. Include the script(s) plus a short `README.md` in that folder explaining what it fixes, requirements, and how to run it.
3. Add a row for it in the table above.

See [CONTRIBUTING.md](CONTRIBUTING.md) for more detail.

## License

MIT — see [LICENSE](LICENSE). Use, modify, and share freely.
