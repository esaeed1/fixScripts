# find-window.ps1
# Lists your open windows - including minimized ones, and ones parked
# off-screen or buried behind others - and lets you jump straight to one.

Add-Type @"
using System;
using System.Text;
using System.Runtime.InteropServices;

public class WinFinder {
    public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);

    [DllImport("user32.dll")]
    public static extern bool EnumWindows(EnumWindowsProc enumProc, IntPtr lParam);

    [DllImport("user32.dll", CharSet = CharSet.Auto)]
    public static extern int GetWindowText(IntPtr hWnd, StringBuilder lpString, int nMaxCount);

    [DllImport("user32.dll")]
    public static extern int GetWindowTextLength(IntPtr hWnd);

    [DllImport("user32.dll")]
    public static extern bool IsWindowVisible(IntPtr hWnd);

    [DllImport("user32.dll")]
    public static extern bool IsIconic(IntPtr hWnd);

    [DllImport("user32.dll")]
    public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint lpdwProcessId);

    [DllImport("user32.dll")]
    public static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);

    [DllImport("user32.dll")]
    public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);

    [DllImport("user32.dll")]
    public static extern bool SetForegroundWindow(IntPtr hWnd);

    [DllImport("user32.dll")]
    public static extern IntPtr GetForegroundWindow();

    [DllImport("user32.dll")]
    public static extern bool AttachThreadInput(uint idAttach, uint idAttachTo, bool fAttach);

    [DllImport("user32.dll")]
    public static extern bool MoveWindow(IntPtr hWnd, int X, int Y, int nWidth, int nHeight, bool bRepaint);

    [DllImport("user32.dll")]
    public static extern bool FlashWindow(IntPtr hWnd, bool bInvert);

    [DllImport("kernel32.dll")]
    public static extern uint GetCurrentThreadId();

    public struct RECT { public int Left; public int Top; public int Right; public int Bottom; }
}
"@

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

function Get-OpenWindows {
    $collected = New-Object System.Collections.Generic.List[Object]

    $callback = {
        param($hWnd, $lParam)
        if ([WinFinder]::IsWindowVisible($hWnd)) {
            $len = [WinFinder]::GetWindowTextLength($hWnd)
            if ($len -gt 0) {
                $sb = New-Object System.Text.StringBuilder ($len + 1)
                [WinFinder]::GetWindowText($hWnd, $sb, $sb.Capacity) | Out-Null
                $title = $sb.ToString()
                if ($title.Trim().Length -gt 0) {
                    [uint32]$procId = 0
                    [WinFinder]::GetWindowThreadProcessId($hWnd, [ref]$procId) | Out-Null
                    if ($procId -ne $PID) {
                        $procName = "unknown"
                        try { $procName = (Get-Process -Id $procId -ErrorAction Stop).ProcessName } catch {}
                        $script:collected.Add([PSCustomObject]@{
                            Handle    = $hWnd
                            Title     = $title
                            Process   = $procName
                            Minimized = [WinFinder]::IsIconic($hWnd)
                        })
                    }
                }
            }
        }
        return $true
    }

    $script:collected = $collected
    [WinFinder]::EnumWindows($callback, [IntPtr]::Zero) | Out-Null
    return $collected
}

Write-Host ""
Write-Host "=== Window Finder ===" -ForegroundColor Cyan
$search = Read-Host "Type part of the window title or app name to search (Enter = show all)"

$all = Get-OpenWindows
if ($search) {
    $filtered = $all | Where-Object { $_.Title -like "*$search*" -or $_.Process -like "*$search*" }
} else {
    $filtered = $all
}

if (-not $filtered -or $filtered.Count -eq 0) {
    Write-Host "No matching windows found." -ForegroundColor Red
    Read-Host "Press Enter to close"
    exit 1
}

Write-Host ""
$i = 1
$indexed = @{}
foreach ($w in $filtered) {
    $tag = if ($w.Minimized) { " (minimized)" } else { "" }
    Write-Host ("[{0}] {1}  -  {2}{3}" -f $i, $w.Title, $w.Process, $tag)
    $indexed[$i] = $w
    $i++
}

Write-Host ""
$choice = Read-Host "Enter the number of the window to jump to"
if (-not $indexed.ContainsKey([int]$choice)) {
    Write-Host "Invalid selection." -ForegroundColor Red
    Read-Host "Press Enter to close"
    exit 1
}

$target = $indexed[[int]$choice]
$hWnd = $target.Handle

if (-not [WinFinder]::IsWindowVisible($hWnd)) {
    Write-Host "That window closed before it could be activated. Run the script again." -ForegroundColor Red
    Read-Host "Press Enter to close"
    exit 1
}

# Restore it if it's minimized
if ([WinFinder]::IsIconic($hWnd)) {
    [WinFinder]::ShowWindow($hWnd, 9) | Out-Null  # SW_RESTORE
}

# Bring it to the foreground, bypassing Windows' "don't let background apps
# steal focus" restriction, by briefly attaching input threads.
[uint32]$dummy = 0
$foreThread = [WinFinder]::GetWindowThreadProcessId([WinFinder]::GetForegroundWindow(), [ref]$dummy)
$targetThread = [WinFinder]::GetWindowThreadProcessId($hWnd, [ref]$dummy)
$currentThread = [WinFinder]::GetCurrentThreadId()

[WinFinder]::AttachThreadInput($currentThread, $foreThread, $true) | Out-Null
[WinFinder]::AttachThreadInput($currentThread, $targetThread, $true) | Out-Null
[WinFinder]::SetForegroundWindow($hWnd) | Out-Null
[WinFinder]::AttachThreadInput($currentThread, $foreThread, $false) | Out-Null
[WinFinder]::AttachThreadInput($currentThread, $targetThread, $false) | Out-Null

# If the window is sitting completely off every visible monitor
# (e.g. it remembers a monitor that's now disconnected), pull it back on-screen.
$rect = New-Object "WinFinder+RECT"
[WinFinder]::GetWindowRect($hWnd, [ref]$rect) | Out-Null
$winBounds = New-Object System.Drawing.Rectangle($rect.Left, $rect.Top, ($rect.Right - $rect.Left), ($rect.Bottom - $rect.Top))

$onScreen = $false
foreach ($screen in [System.Windows.Forms.Screen]::AllScreens) {
    if ($screen.Bounds.IntersectsWith($winBounds)) { $onScreen = $true; break }
}
if (-not $onScreen) {
    Write-Host "That window was positioned off-screen - moving it back into view." -ForegroundColor Yellow
    [WinFinder]::MoveWindow($hWnd, 100, 100, 1000, 700, $true) | Out-Null
}

# Blink the taskbar icon a couple times so it's easy to spot among many windows
for ($n = 0; $n -lt 4; $n++) {
    [WinFinder]::FlashWindow($hWnd, $true) | Out-Null
    Start-Sleep -Milliseconds 250
}

Write-Host ""
Write-Host ("Brought '{0}' to the front." -f $target.Title) -ForegroundColor Green
Write-Host ""
Read-Host "Press Enter to close"
