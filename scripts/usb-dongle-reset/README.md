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
5. **First run only:** you'll see a numbered list of connected devices. Pick the number matching your wireless dongle (usually something audio- or USB-related). Your choice is saved to a local `headset-device.txt` file next to the scripts, so future runs skip straight to the reset.
6. Wait a few seconds for the device to reconnect, then check your audio.

To make it pick a different device later (e.g. you got a new headset), delete `headset-device.txt` and run the script again — it'll ask you to pick from the list once more.

## Notes

- This isn't specific to headsets — it works for any USB device you'd normally fix by unplugging and replugging (mouse/keyboard dongles included), as long as you pick the right one from the list.
- `headset-device.txt` is machine- and device-specific, so it's excluded from git via `.gitignore` — don't worry if you don't see it after cloning.
