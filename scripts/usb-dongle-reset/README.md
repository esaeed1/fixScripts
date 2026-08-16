# usb-dongle-reset

Resets a USB wireless dongle (headset receiver, mouse/keyboard receiver, etc.) in software, without having to physically unplug and replug it.

## The problem this fixes

Wireless devices that use a USB dongle (rather than Bluetooth) send data over a proprietary 2.4GHz radio link with limited bandwidth. A common symptom on wireless headsets: audio sounds great while just listening, but degrades noticeably once the microphone becomes active (a call, voice chat, an unmuted app) — because the dongle's firmware has to squeeze in the mic's upstream signal and drops audio quality to make room. USB port interference (especially from nearby USB 3.0 ports/cables) can make it worse.

The normal fix is unplugging the dongle and plugging it back in, which forces it to redo its wireless handshake. This script does the software equivalent — disabling and re-enabling the device in Windows — so you don't need physical access to the port.

## Requirements

- Windows 10 or 11
- Administrator rights (the `.bat` launcher will prompt for these automatically)

## Files

- `RestartHeadset.bat` — double-click this. Requests admin permission, then runs the PowerShell script.
- `restart-headset.ps1` — does the actual work of finding and toggling the device.

## Usage

1. Download this folder (or the whole repo).
2. Keep both files together in the same folder.
3. Double-click `RestartHeadset.bat`.
4. Click **Yes** on the permission prompt.
5. **First run only:** you'll see a numbered list of connected devices. Pick the number matching your dongle (usually something audio- or USB-related), then give it a short nickname (e.g. "Headset"). It's saved so future runs skip straight to a menu.
6. Wait a few seconds for the device to reconnect, then check it.

On later runs, you'll see a menu like:

```
[0] Reset ALL saved devices
[1] Headset
[2] Mouse dongle
[3] Add a new device
```

Pick `0` to reset everything you've saved at once, a specific number to reset just that one, or the "Add a new device" option to save another dongle (e.g. a mouse or webcam receiver) alongside the ones you already have. There's no limit to how many you can save.

## Notes

- This isn't specific to headsets — it works for any USB device you'd normally fix by unplugging and replugging (mouse/keyboard dongles included), as long as you pick the right one from the list.
- Saved devices live in `saved-devices.json` next to the scripts, which is machine-specific and excluded from git via `.gitignore` — don't worry if you don't see it after cloning.
- If a saved device is no longer plugged in, it's automatically dropped from the menu next time you run the script (no need to clean it up yourself).
- Upgrading from an older version of this script? Your previously saved device (from `headset-device.txt`) is picked up automatically and migrated into the new format the first time you run it.
