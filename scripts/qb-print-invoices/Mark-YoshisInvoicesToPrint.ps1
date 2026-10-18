<#
  Puts ONE location's (customer's) unpaid invoices in the QuickBooks Desktop print
  queue - marks them "Print Later" and un-marks every other invoice - so they can be
  printed together from File > Print Forms > Invoices.

  Only the Print Later flag is changed - amounts, items and dates are not touched.
  Run this on the PC where QuickBooks is open with the company file loaded.
#>
# customers whose name contains any of these words (same owner: Yum Yoshis + BBQ Central)
$Match = @('Yoshi', 'BBQ')

$ErrorActionPreference = 'Stop'
$AppName = 'Yoshis Invoice Printer'
$Inv = [Globalization.CultureInfo]::InvariantCulture

function X([string]$s) { [System.Security.SecurityElement]::Escape($s) }

function Send-Qb([string]$body) {
    $req = '<?xml version="1.0"?><?qbxml version="13.0"?><QBXML>' +
           '<QBXMLMsgsRq onError="continueOnError">' + $body + '</QBXMLMsgsRq></QBXML>'
    [xml]($script:rp.ProcessRequest($script:ticket, $req))
}

function Get-Locations {
    $q = ($Match | ForEach-Object {
            '<CustomerQueryRq><ActiveStatus>All</ActiveStatus><NameFilter>' +
            '<MatchCriterion>Contains</MatchCriterion><Name>' + (X $_) + '</Name></NameFilter>' +
            '<IncludeRetElement>ListID</IncludeRetElement><IncludeRetElement>FullName</IncludeRetElement>' +
            '<IncludeRetElement>TotalBalance</IncludeRetElement></CustomerQueryRq>' }) -join ''
    $byId = @{}
    (Send-Qb $q).SelectNodes('//CustomerRet') | ForEach-Object { $byId[$_.ListID] = $_ }
    if (-not $byId.Count) { throw "No customers found containing: $($Match -join ', ')" }
    $custs = @($byId.Values | Sort-Object { $_.FullName })

    # one invoice query per customer, sent together in a single request
    $body = ''
    for ($i = 0; $i -lt $custs.Count; $i++) {
        $body += "<InvoiceQueryRq requestID=`"$i`"><EntityFilter><ListID>$($custs[$i].ListID)</ListID></EntityFilter>" +
                 '<PaidStatus>NotPaidOnly</PaidStatus>' +
                 (('TxnID','EditSequence','RefNumber','TxnDate','DueDate','PONumber','Subtotal','BalanceRemaining','IsToBePrinted' |
                   ForEach-Object { "<IncludeRetElement>$_</IncludeRetElement>" }) -join '') +
                 '</InvoiceQueryRq>'
    }
    $doc = Send-Qb $body
    for ($i = 0; $i -lt $custs.Count; $i++) {
        $rs = $doc.SelectSingleNode("//InvoiceQueryRs[@requestID='$i']")
        $invs = @(if ($rs.statusCode -eq '0') { $rs.SelectNodes('InvoiceRet') | Sort-Object { $_.TxnDate }, { $_.RefNumber } })
        [pscustomobject]@{
            Name     = $custs[$i].FullName
            Balance  = [decimal]::Parse($custs[$i].TotalBalance, $Inv)
            Invoices = $invs
            OpenSum  = [decimal]($invs | ForEach-Object { [decimal]::Parse($_.BalanceRemaining, $Inv) } | Measure-Object -Sum).Sum
            Marked   = @($invs | Where-Object { $_.IsToBePrinted -eq 'true' }).Count
        }
    }
}

function Set-PrintFlag($invoices, [bool]$on) {
    $flag = if ($on) { 'true' } else { 'false' }
    $todo = @($invoices | Where-Object { $_.IsToBePrinted -ne $flag })
    $ok = 0; $failed = @()
    for ($start = 0; $start -lt $todo.Count; $start += 50) {
        $chunk = $todo[$start..([Math]::Min($start + 49, $todo.Count - 1))]
        $body = ''
        for ($i = 0; $i -lt $chunk.Count; $i++) {
            $body += "<InvoiceModRq requestID=`"$i`"><InvoiceMod><TxnID>$($chunk[$i].TxnID)</TxnID>" +
                     "<EditSequence>$($chunk[$i].EditSequence)</EditSequence>" +
                     "<IsToBePrinted>$flag</IsToBePrinted></InvoiceMod></InvoiceModRq>"
        }
        $doc = Send-Qb $body
        for ($i = 0; $i -lt $chunk.Count; $i++) {
            $rs = $doc.SelectSingleNode("//InvoiceModRs[@requestID='$i']")
            if ($rs.statusCode -eq '0') { $ok++ }
            else { $failed += "  Invoice $($chunk[$i].RefNumber): $($rs.statusMessage)" }
        }
        Write-Host "  ...$([Math]::Min($start + 50, $todo.Count)) of $($todo.Count)"
    }
    $script:LastFailed = $failed.Count
    Write-Host "Done: $ok invoice(s) updated." -ForegroundColor Green
    if ($failed) { Write-Host "Could not update $($failed.Count):" -ForegroundColor Red; $failed | Write-Host }
}

# Every other invoice marked Print Later is un-marked for good, so only the chosen location is in
# the print queue. Their IDs are logged to this file, just as a record.
$RemovedLog = Join-Path $PSScriptRoot 'removed_print_marks.txt'
# After a full scan, the only marked invoices are the last location's, so the next round only needs
# invoices modified since then plus last round's (in case they weren't printed).
# Line 1 = scan time, other lines = last round's invoice TxnIDs.
$StateFile = Join-Path $PSScriptRoot 'last_scan.txt'

$MarkElems = ('TxnID', 'EditSequence', 'RefNumber', 'IsToBePrinted' | ForEach-Object { "<IncludeRetElement>$_</IncludeRetElement>" }) -join ''

function Get-MarkedInvoices([string]$since) {   # invoices marked Print Later (optionally only those modified since)
    $found = @(); $attr = 'iterator="Start"'; $seen = 0
    $filter = if ($since) { "<ModifiedDateRangeFilter><FromModifiedDate>$since</FromModifiedDate></ModifiedDateRangeFilter>" }
    do {
        $rs = (Send-Qb "<InvoiceQueryRq $attr><MaxReturned>1000</MaxReturned>$filter$MarkElems</InvoiceQueryRq>").SelectSingleNode('//InvoiceQueryRs')
        if ($rs.statusCode -notin '0', '1') { throw "Invoice scan failed: $($rs.statusMessage)" }
        $batch = @($rs.SelectNodes('InvoiceRet'))
        $seen += $batch.Count
        $found += @($batch | Where-Object { $_.IsToBePrinted -eq 'true' })
        Write-Host "  scanned $seen invoices, $($rs.iteratorRemainingCount) to go..."
        $attr = "iterator=`"Continue`" iteratorID=`"$($rs.iteratorID)`""
    } while ($rs.iteratorRemainingCount -and [int]$rs.iteratorRemainingCount -gt 0)
    $found
}

function Get-InvoicesById([string[]]$ids) {
    for ($s = 0; $s -lt $ids.Count; $s += 100) {
        $q = (($ids[$s..([Math]::Min($s + 99, $ids.Count - 1))] | ForEach-Object { "<TxnID>$_</TxnID>" }) -join '')
        (Send-Qb "<InvoiceQueryRq>$q$MarkElems</InvoiceQueryRq>").SelectNodes('//InvoiceRet')   # deleted ones are simply skipped
    }
}

function Invoke-Prepare($targets) {
    $mine = @($targets | ForEach-Object { $_.Invoices })
    $ids = New-Object 'System.Collections.Generic.HashSet[string]'
    $mine | ForEach-Object { [void]$ids.Add($_.TxnID) }
    $scanTime = (Get-Date).AddMinutes(-5).ToString('yyyy-MM-ddTHH:mm:ss')
    $state = @(if (Test-Path $StateFile) { Get-Content $StateFile | Where-Object { $_ } })
    if ($state) {
        Write-Host 'Quick check of invoices changed since the last round...' -ForegroundColor Cyan
        $marked = @(Get-MarkedInvoices $state[0]) + @(Get-InvoicesById @($state | Select-Object -Skip 1) | Where-Object { $_.IsToBePrinted -eq 'true' })
    } else {
        Write-Host 'Checking which other invoices are marked Print Later (full scan)...' -ForegroundColor Cyan
        $marked = @(Get-MarkedInvoices)
    }
    $seenIds = @{}
    $others = @($marked | Where-Object { -not $ids.Contains($_.TxnID) -and -not $seenIds.ContainsKey($_.TxnID) } |
                ForEach-Object { $seenIds[$_.TxnID] = 1; $_ })

    Write-Host ''
    if ($targets) {
        Write-Host "Location: $(($targets.Name) -join ', ')"
        Write-Host "  - mark its $($mine.Count) unpaid invoice(s) Print Later"
    }
    if ($others) { Write-Host "  - remove Print Later from $($others.Count) other invoice(s)" }
    if (-not $targets -and -not $others) { Write-Host 'Print queue is already empty.' -ForegroundColor Green; return }
    if ((Read-Host 'Go ahead? (Y/N)') -notmatch '^[Yy]') { return }

    $script:LastFailed = 0
    if ($others) {
        Add-Content $RemovedLog ($others | ForEach-Object { "$(Get-Date -Format s)`t$($_.TxnID)`t$($_.RefNumber)" })
        Write-Host 'Removing Print Later from other invoices:'; Set-PrintFlag $others $false
    }
    # an invoice that couldn't be un-marked stays marked without being modified, so only a full scan finds it again
    if ($script:LastFailed) { Remove-Item $StateFile -ErrorAction SilentlyContinue }
    else { Set-Content $StateFile (@($scanTime) + @($mine | ForEach-Object { $_.TxnID })) }
    if (-not $targets) { Write-Host 'Print queue is now empty.' -ForegroundColor Green; return }
    Write-Host 'Marking this location''s invoices:'; Set-PrintFlag $mine $true
    Write-Host ''
    Write-Host "Only these $($mine.Count) invoice(s) are in the print queue now." -ForegroundColor Green
    Write-Host 'In QuickBooks: File > Print Forms > Invoices - check the count at the top matches - Select All > OK > Print.' -ForegroundColor Cyan
    Write-Host 'When QuickBooks asks "Did form(s) print OK?" click OK. Then come back here for the next location.' -ForegroundColor Cyan
}

function Save-Csv($locs) {
    $path = Join-Path $PSScriptRoot ('open_invoices_' + (Get-Date -Format 'yyyy-MM-dd') + '.csv')
    $locs | ForEach-Object { $l = $_; $l.Invoices | ForEach-Object {
        [pscustomobject]@{ Location = $l.Name; Invoice = $_.RefNumber; Date = $_.TxnDate; DueDate = $_.DueDate
                           PO = $_.PONumber; Amount = $_.Subtotal; OpenBalance = $_.BalanceRemaining } } } |
        Export-Csv $path -NoTypeInformation
    $path
}

function Show-Menu($locs) {
    Write-Host ''
    Write-Host ('  #  {0,-32} {1,9} {2,14} {3,14} {4,8}' -f 'Location', 'Unpaid', 'Unpaid total', 'QB balance', 'Marked')
    for ($i = 0; $i -lt $locs.Count; $i++) {
        $l = $locs[$i]
        $c = if ($l.OpenSum -ne $l.Balance) { 'Yellow' } else { 'Gray' }
        Write-Host ('{0,3}  {1,-32} {2,9} {3,14:N2} {4,14:N2} {5,8}' -f ($i + 1), $l.Name, $l.Invoices.Count, $l.OpenSum, $l.Balance, $l.Marked) -ForegroundColor $c
    }
    Write-Host '  (yellow = unpaid invoices do not add up to the QB balance, e.g. journal entries or unapplied payments)' -ForegroundColor DarkGray
}

Add-Type @'
using System; using System.Runtime.InteropServices;
public static class Tok {
  [DllImport("kernel32.dll")] static extern IntPtr OpenProcess(uint a, bool b, int pid);
  [DllImport("advapi32.dll")] static extern bool OpenProcessToken(IntPtr h, uint acc, out IntPtr t);
  [DllImport("advapi32.dll")] static extern bool GetTokenInformation(IntPtr t, int c, out int v, int l, out int r);
  [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr h);
  // true = elevated, or a normal process can't read it (which also means elevated)
  public static bool IsElevated(int pid) {
    IntPtr p = OpenProcess(0x1000, false, pid), t;
    if (p == IntPtr.Zero) return true;
    if (!OpenProcessToken(p, 8, out t)) { CloseHandle(p); return true; }
    int v, r; GetTokenInformation(t, 20, out v, 4, out r);
    CloseHandle(t); CloseHandle(p);
    return v != 0;
  }
}
'@

# The connector can only reach QuickBooks if both run at the same level (both normal or both administrator).
function Assert-SameLevelAsQuickBooks {
    $qb = Get-Process -Name qbw, qbw32 -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $qb) { throw 'QuickBooks is not running. Open QuickBooks and the company file, then run this again.' }
    $meAdmin = [Tok]::IsElevated($PID)
    $qbAdmin = [Tok]::IsElevated($qb.Id)
    if ($meAdmin -and -not $qbAdmin) {
        $flag = Join-Path $env:TEMP 'yoshis-relaunch.flag'
        if (-not (Test-Path $flag) -or ((Get-Date) - (Get-Item $flag).LastWriteTime).TotalSeconds -gt 60) {
            Set-Content $flag ''
            Write-Host 'This window is administrator but QuickBooks is not - reopening as a normal window...' -ForegroundColor Cyan
            Start-Process explorer.exe -ArgumentList ('"' + (Join-Path $PSScriptRoot 'RUN-ME.bat') + '"')
            exit 9   # RUN-ME.bat closes this window on 9
        }
        throw ('Could not reopen as a normal window. Instead: close QuickBooks, right-click the QuickBooks icon > ' +
               'Run as administrator, open the company file, then run RUN-ME.bat again.')
    }
    if ($qbAdmin -and -not $meAdmin) {
        throw 'QuickBooks is running as administrator. Right-click RUN-ME.bat > Run as administrator.'
    }
}

function Main {
    Assert-SameLevelAsQuickBooks
    try { $script:rp = New-Object -ComObject QBXMLRP2.RequestProcessor }
    catch {
        if ([Environment]::Is64BitProcess -and -not $env:QB_RELAUNCHED) {   # retry as 32-bit
            $env:QB_RELAUNCHED = '1'
            & "$env:WINDIR\SysWOW64\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File $PSCommandPath
            return
        }
        throw 'QuickBooks connector (QBXMLRP2) not found. Run this on the PC where QuickBooks Desktop is installed.'
    }

    Write-Host 'Connecting to QuickBooks... (first time: switch to QuickBooks and click "Yes, always" to allow access)' -ForegroundColor Cyan
    $script:rp.OpenConnection2('', $AppName, 1)
    $script:ticket = $script:rp.BeginSession('', 2)
    try {
        while ($true) {
            $locs = @(Get-Locations)
            Show-Menu $locs
            Write-Host "List of all unpaid invoices saved to: $(Save-Csv $locs)" -ForegroundColor DarkGray
            Write-Host ''
            Write-Host '  3     = print queue gets ONLY location 3''s unpaid invoices (everything else is un-marked)'
            Write-Host '  3/50  = same, but in parts of 50 invoices (for big locations)'
            Write-Host '  C     = clear the whole print queue (un-mark every invoice)'
            Write-Host '  Q     = quit'
            $ans = (Read-Host 'Choice').Trim().ToUpper()
            if ($ans -eq 'Q' -or $ans -eq '') { break }
            if ($ans -eq 'C') { Invoke-Prepare @(); continue }
            if ($ans -match '^(\d+)\s*/\s*(\d+)$') {
                $n = [int]$Matches[1]; $size = [int]$Matches[2]
                if ($n -lt 1 -or $n -gt $locs.Count -or $size -lt 1 -or -not $locs[$n - 1].Invoices) { Write-Host 'Not a valid choice.' -ForegroundColor Red; continue }
                $l = $locs[$n - 1]; $all = @($l.Invoices); $parts = [int][Math]::Ceiling($all.Count / $size)
                for ($p = 1; $p -le $parts; $p++) {
                    $c = @($all[(($p - 1) * $size)..([Math]::Min($p * $size, $all.Count) - 1)])
                    Write-Host ('  part {0}: {1} invoices, #{2} ({3}) to #{4} ({5})' -f $p, $c.Count, $c[0].RefNumber, $c[0].TxnDate, $c[-1].RefNumber, $c[-1].TxnDate)
                }
                $p = Read-Host "Which part (1-$parts)?"
                if ($p -notmatch '^\d+$' -or [int]$p -lt 1 -or [int]$p -gt $parts) { Write-Host 'Not a valid part.' -ForegroundColor Red; continue }
                $p = [int]$p
                $chunk = @($all[(($p - 1) * $size)..([Math]::Min($p * $size, $all.Count) - 1)])
                Invoke-Prepare @([pscustomobject]@{ Name = "$($l.Name) - part $p of $parts"; Invoices = $chunk })
                continue
            }
            if ($ans -match '^\d+$' -and [int]$ans -ge 1 -and [int]$ans -le $locs.Count) { Invoke-Prepare @($locs[[int]$ans - 1]); continue }
            Write-Host 'Not a valid choice.' -ForegroundColor Red
        }
    }
    finally {
        $script:rp.EndSession($script:ticket)
        $script:rp.CloseConnection()
    }
}

if ($MyInvocation.InvocationName -ne '.') {
    try { Main } catch {
        Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
        if ($_.Exception.Message -match 'Could not start QuickBooks') {
            Write-Host 'Fix: 1) QuickBooks must be open WITH the company file loaded (not the "No Company Open" screen).' -ForegroundColor Yellow
            Write-Host '     2) Run RUN-ME.bat by double-clicking it, NOT "Run as administrator" (QuickBooks and this' -ForegroundColor Yellow
            Write-Host '        window must both be normal, or both be administrator).' -ForegroundColor Yellow
            Write-Host '     3) Close any open pop-up or dialog box inside QuickBooks, then try again.' -ForegroundColor Yellow
        }
    }
}
