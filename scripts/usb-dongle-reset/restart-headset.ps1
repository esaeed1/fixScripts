# restart-headset.ps1
# One-click "reset" for USB wireless dongles (headset, mouse receiver, etc.)
# by disabling and re-enabling them in Windows, without physically unplugging
# them. Remembers multiple devices by nickname, and can reset one, several,
# or all of them at once.

$ErrorActionPreference = 'Stop'
$configPath = Join-Path $PSScriptRoot 'saved-devices.json'
$legacyConfigPath = Join-Path $PSScriptRoot 'headset-device.txt'

function Load-SavedDevices {
    if (Test-Path $configPath) {
        try {
            $json = Get-Content $configPath -Raw | ConvertFrom-Json
            if ($json -isnot [System.Array]) { $json = @($json) }
            return @($json)
        } catch {
            return @()
        }
    }

    # Migrate from the old single-device format used by earlier versions of this script
    if (Test-Path $legacyConfigPath) {
        $id = (Get-Content $legacyConfigPath -Raw).Trim()
        if ($id) {
            $migrated = @([PSCustomObject]@{ Name = "Saved Device"; InstanceId = $id })
            Save-SavedDevices $migrated
            Remove-Item $legacyConfigPath -ErrorAction SilentlyContinue
            return $migrated
        }
    }

    return @()
}

function Save-SavedDevices($devices) {
    ConvertTo-Json @($devices) | Out-File -FilePath $configPath -Encoding UTF8
}

function Pick-NewDevice {
    Write-Host ""
    Write-Host "=== Select a device from the list below ===" -ForegroundColor Cyan
    Write-Host "(Look for the name that matches your dongle/receiver.)"
    Write-Host ""

    $devices = Get-PnpDevice -PresentOnly | Where-Object {
        $_.Status -eq 'OK' -and
        ($_.Class -in @('USB','HIDClass','Media','AudioEndpoint','SoundVideoAndGameControllers','MEDIA'))
    } | Sort-Object Class, FriendlyName

    if (-not $devices) {
        Write-Host "No candidate devices found. Make sure it's plugged in." -ForegroundColor Red
        return $null
    }

    $i = 1
    $indexed = @{}
    foreach ($d in $devices) {
        Write-Host ("[{0}] {1}  -  ({2})" -f $i, $d.FriendlyName, $d.Class)
        $indexed[$i] = $d
        $i++
    }

    Write-Host ""
    $choice = Read-Host "Enter the number for the device"
    if (-not $indexed.ContainsKey([int]$choice)) {
        Write-Host "Invalid selection." -ForegroundColor Red
        return $null
    }

    $selected = $indexed[[int]$choice]
    $nickname = Read-Host "Give it a short nickname (e.g. 'Headset', 'Mouse dongle') - Enter to use its default name"
    if ([string]::IsNullOrWhiteSpace($nickname)) { $nickname = $selected.FriendlyName }

    return [PSCustomObject]@{ Name = $nickname; InstanceId = $selected.InstanceId }
}

function Reset-Device($device) {
    Write-Host ("Resetting '{0}'..." -f $device.Name) -ForegroundColor Cyan
    try {
        Disable-PnpDevice -InstanceId $device.InstanceId -Confirm:$false
        Start-Sleep -Seconds 2
        Enable-PnpDevice -InstanceId $device.InstanceId -Confirm:$false
        Write-Host ("Done: {0}" -f $device.Name) -ForegroundColor Green
    } catch {
        Write-Host ("Failed to reset '{0}': {1}" -f $device.Name, $_) -ForegroundColor Red
        Write-Host "Make sure you're running this as Administrator." -ForegroundColor Red
    }
}

# ---- Main ----
$saved = Load-SavedDevices

# Drop any saved devices that no longer exist on this PC (unplugged, swapped, etc.)
$saved = @($saved | Where-Object { $_.InstanceId -and (Get-PnpDevice -InstanceId $_.InstanceId -ErrorAction SilentlyContinue) })

if ($saved.Count -eq 0) {
    Write-Host "No saved devices yet - let's add one." -ForegroundColor Yellow
    $new = Pick-NewDevice
    if ($new) {
        $saved = @($new)
        Save-SavedDevices $saved
        Write-Host ""
        Reset-Device $new
    }
} else {
    Write-Host ""
    Write-Host "=== What would you like to reset? ===" -ForegroundColor Cyan
    Write-Host "[0] Reset ALL saved devices"

    $i = 1
    $indexed = @{}
    foreach ($d in $saved) {
        Write-Host ("[{0}] {1}" -f $i, $d.Name)
        $indexed[$i] = $d
        $i++
    }
    $addOption = $i
    Write-Host ("[{0}] Add a new device" -f $addOption)

    Write-Host ""
    $choice = Read-Host "Enter your choice"
    $choiceInt = 0

    if ([int]::TryParse($choice, [ref]$choiceInt)) {
        Write-Host ""
        if ($choiceInt -eq 0) {
            foreach ($d in $saved) { Reset-Device $d }
        } elseif ($choiceInt -eq $addOption) {
            $new = Pick-NewDevice
            if ($new) {
                $saved = @($saved) + $new
                Save-SavedDevices $saved
                Write-Host ""
                Reset-Device $new
            }
        } elseif ($indexed.ContainsKey($choiceInt)) {
            Reset-Device $indexed[$choiceInt]
        } else {
            Write-Host "Invalid selection." -ForegroundColor Red
        }
    } else {
        Write-Host "Invalid selection." -ForegroundColor Red
    }
}

Write-Host ""
Read-Host "Press Enter to close"
