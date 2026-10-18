<#  Collects what is needed to fix "Could not start QuickBooks". Changes nothing.
    Results are shown on screen and saved to diagnose.txt next to this script. #>
param([switch]$ConnTestOnly)

function Log($s) { Write-Host $s; Add-Content -Path $script:LogFile -Value $s }
$script:LogFile = Join-Path $PSScriptRoot 'diagnose.txt'

function Test-Connection-QB {
    $bits = if ([Environment]::Is64BitProcess) { '64-bit' } else { '32-bit' }
    Log "--- Connection test ($bits) ---"
    try { $rp = New-Object -ComObject QBXMLRP2.RequestProcessor; Log 'Connector created: OK' }
    catch { Log "Connector create FAILED: $($_.Exception.Message)"; return }
    try { $rp.OpenConnection2('', 'Yoshis Invoice Printer', 1); Log 'OpenConnection: OK' }
    catch { Log ('OpenConnection FAILED: 0x{0:X8} {1}' -f $_.Exception.HResult, $_.Exception.Message); return }
    try {
        $t = $rp.BeginSession('', 2); Log 'BeginSession: OK  <-- connection works'
        Log "Company file: $($rp.GetCurrentCompanyFileName($t))"
        $rp.EndSession($t)
    } catch {
        $e = if ($_.Exception.InnerException) { $_.Exception.InnerException } else { $_.Exception }
        Log ('BeginSession FAILED: 0x{0:X8} {1}' -f $e.HResult, $e.Message)
    }
    $rp.CloseConnection()
}

if ($ConnTestOnly) { Test-Connection-QB; return }

Set-Content -Path $LogFile -Value "QuickBooks connection diagnostic  $(Get-Date)"
Add-Type @'
using System; using System.Runtime.InteropServices;
public static class Tok {
  [DllImport("kernel32.dll")] static extern IntPtr OpenProcess(uint a, bool b, int pid);
  [DllImport("advapi32.dll")] static extern bool OpenProcessToken(IntPtr h, uint acc, out IntPtr t);
  [DllImport("advapi32.dll")] static extern bool GetTokenInformation(IntPtr t, int c, out int v, int l, out int r);
  [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr h);
  public static string Elevated(int pid) {
    IntPtr p = OpenProcess(0x1000, false, pid), t;
    if (p == IntPtr.Zero) return "unknown (no access - probably ADMINISTRATOR)";
    if (!OpenProcessToken(p, 8, out t)) { CloseHandle(p); return "unknown (no access - probably ADMINISTRATOR)"; }
    int v, r; bool ok = GetTokenInformation(t, 20, out v, 4, out r);
    CloseHandle(t); CloseHandle(p);
    return !ok ? "unknown" : (v != 0 ? "ADMINISTRATOR" : "normal");
  }
}
'@

$id = [Security.Principal.WindowsIdentity]::GetCurrent()
$elev = (New-Object Security.Principal.WindowsPrincipal $id).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
Log "This window : $(if ($elev) {'ADMINISTRATOR'} else {'normal'}), $(if ([Environment]::Is64BitProcess) {'64-bit'} else {'32-bit'}), user $($id.Name), session $((Get-Process -Id $PID).SessionId)"
Log "UAC (EnableLUA): $((Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System' -ErrorAction SilentlyContinue).EnableLUA)"

Log '--- Running QuickBooks processes ---'
$qb = @(Get-Process | Where-Object { $_.ProcessName -match '^QBW' })
if (-not $qb) { Log 'NONE - QuickBooks is not running!' }
foreach ($p in $qb) { Log "$($p.ProcessName)  pid $($p.Id)  session $($p.SessionId)  runs as: $([Tok]::Elevated($p.Id))  $($p.Path)" }

Log '--- Connector (QBXMLRP2) registration ---'
foreach ($v in @(@{n = '64-bit'; k = 'HKLM:\SOFTWARE\Classes'}, @{n = '32-bit'; k = 'HKLM:\SOFTWARE\WOW6432Node\Classes'})) {
    $clsid = (Get-ItemProperty "$($v.k)\QBXMLRP2.RequestProcessor\CLSID" -ErrorAction SilentlyContinue).'(default)'
    if (-not $clsid) { Log "$($v.n): not registered"; continue }
    foreach ($s in 'InprocServer32', 'LocalServer32') {
        $path = (Get-ItemProperty "$($v.k)\CLSID\$clsid\$s" -ErrorAction SilentlyContinue).'(default)'
        if ($path) {
            $file = $path.Trim('"').Split('"')[0]
            $ver = if (Test-Path $file) { (Get-Item $file).VersionInfo.FileVersion } else { 'FILE MISSING' }
            Log "$($v.n): $clsid $s = $path  (version $ver)"
        }
    }
}

Log '--- QuickBooks versions in registry ---'
foreach ($k in 'HKLM:\SOFTWARE\Intuit\QuickBooks', 'HKLM:\SOFTWARE\WOW6432Node\Intuit\QuickBooks') {
    Get-ChildItem $k -ErrorAction SilentlyContinue | ForEach-Object { Log "$k\$($_.PSChildName)" }
}

Write-Host ''
Write-Host 'Testing the connection. If a QuickBooks LOGIN box pops up, click Cancel.' -ForegroundColor Yellow
Write-Host 'If an "Application Certificate" box pops up, choose "Yes, whenever this company file is open".' -ForegroundColor Yellow
Test-Connection-QB
if ([Environment]::Is64BitProcess) {
    & "$env:WINDIR\SysWOW64\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File $PSCommandPath -ConnTestOnly
}
Write-Host ''
Write-Host "Saved to $LogFile - send a screenshot of this window." -ForegroundColor Cyan
