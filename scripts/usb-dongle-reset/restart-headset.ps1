# restart-headset.ps1
# One-click "reset" for a USB wireless dongle (headset, mouse receiver, etc.)
# by disabling and re-enabling it in Windows, without physically unplugging it.

$ErrorActionPreference = 'Stop'
$configPath = Join-Path $PSScriptRoot 'headset-device.txt'

function Show-Menu {
    Write-Host ""
    Write-Host "=== Select your headset dongle from the list below ===" -ForegroundColor Cyan
    Write-Host "(Look for the name that matches your wireless headset/dongle.)"
    Write-Host ""

    $devices = Get-PnpDevice -PresentOnly | Where-Object {
        $_.Status -eq 'OK' -and
        ($_.Class -in @('USB','HIDClass','Media','AudioEndpoint','SoundVideoAndGameControllers','MEDIA'))
    } | Sort-Object Class, FriendlyName

    if (-not $devices) {
        Write-Host "No candidate devices found. Make sure the dongle is plugged in." -ForegroundColor Red
        Read-Host "Press Enter to close"
        exit 1
    }

    $i = 1
    $indexed = @{}
    foreach ($d in $devices) {
        Write-Host ("[{0}] {1}  -  ({2})" -f $i, $d.FriendlyName, $d.Class)
        $indexed[$i] = $d
        $i++
    }

    Write-Host ""
    $choice = Read-Host "Enter the number for your headset dongle"
    if (-not $indexed.ContainsKey([int]$choice)) {
        Write-Host "Invalid selection." -ForegroundColor Red
        Read-Host "Press Enter to close"
        exit 1
    }

    $selected = $indexed[[int]$choice]
    $selected.InstanceId | Out-File -FilePath $configPath -Encoding UTF8
    Write-Host ""
    Write-Host ("Saved: {0}" -f $selected.FriendlyName) -ForegroundColor Green
    Write-Host "Next time you run this script, it'll skip straight to the reset."
    return $selected.InstanceId
}

# Load saved device, or ask the user to pick one
if (Test-Path $configPath) {
    $instanceId = (Get-Content $configPath -Raw).Trim()
    $exists = Get-PnpDevice -InstanceId $instanceId -ErrorAction SilentlyContinue
    if (-not $exists) {
        Write-Host "Saved device not found (maybe unplugged or moved to a different port). Let's pick it again." -ForegroundColor Yellow
        $instanceId = Show-Menu
    }
} else {
    $instanceId = Show-Menu
}

Write-Host ""
Write-Host "Resetting device..." -ForegroundColor Cyan
try {
    Disable-PnpDevice -InstanceId $instanceId -Confirm:$false
    Start-Sleep -Seconds 2
    Enable-PnpDevice -InstanceId $instanceId -Confirm:$false
    Write-Host ""
    Write-Host "Done. Give it a few seconds to reconnect, then check your audio." -ForegroundColor Green
} catch {
    Write-Host ""
    Write-Host "Something went wrong: $_" -ForegroundColor Red
    Write-Host "Make sure you're running this as Administrator (the .bat launcher should do this automatically)." -ForegroundColor Red
}

Write-Host ""
Read-Host "Press Enter to close"
