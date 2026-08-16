# window-finder

Lists every open window on your PC - including ones that are minimized, buried behind other windows, or parked off-screen after a monitor got unplugged/reconfigured - and lets you jump straight to the one you want.

## The problem this fixes

When you're juggling a lot of windows across multiple monitors (or a laptop that used to be docked to more screens), it's easy to lose track of one: it might be minimized, sitting behind another maximized window, or literally positioned at coordinates that no longer correspond to a connected monitor. Alt-Tab only shows you a small preview and can be hard to scan through when there are many windows open, and Windows sometimes blocks a background window from properly taking focus even after you click it.

This script gives you a plain numbered, searchable list of every open window and forcibly activates the one you pick - restoring it if minimized, pulling it back on-screen if it's off in nowhere, and flashing its taskbar icon so it's easy to spot.

## Requirements

- Windows 10 or 11
- No admin rights needed for normal (non-elevated) target windows.
- If the window you want belongs to an app running **as Administrator**, you'll need to run this script as Administrator too (right-click `FindWindow.bat` → "Run as administrator"). Windows blocks lower-privilege processes from handing focus to elevated ones, so there's no way around this short of elevating.

## Files

- `FindWindow.bat` — double-click this to run it.
- `find-window.ps1` — does the actual work.

## Usage

1. Double-click `FindWindow.bat`.
2. When prompted, type part of the window's title or the app's name (e.g. `chrome`, `discord`, `invoice`) to narrow the list, or just press Enter to see everything open.
3. Pick the number next to the window you want.
4. The script restores it if minimized, brings it to the front, nudges it back on-screen if it was off in nowhere, and blinks its taskbar icon a few times.

## Notes

- The search box matches against both the window title and the process/app name, so you can search by either.
- If a window closes between when you list it and when you pick it, the script will tell you to just run it again.
