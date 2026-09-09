#Requires -Version 5.1
<#
.SYNOPSIS
  One-time setup: downloads jsPDF and generates extension icons.
  Run this before loading the extension in Chrome.

.EXAMPLE
  cd chrome-extension
  .\setup.ps1
#>

$ErrorActionPreference = 'Stop'
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host ""
Write-Host " VS to PDF Saver — Extension Setup " -ForegroundColor Cyan -BackgroundColor DarkBlue
Write-Host ""

# ── Create directories ────────────────────────────────────────────────────────
New-Item -ItemType Directory -Force -Path "$dir\lib"   | Out-Null
New-Item -ItemType Directory -Force -Path "$dir\icons" | Out-Null

# ── Download jsPDF 2.5.1 ──────────────────────────────────────────────────────
$jspdfDest = "$dir\lib\jspdf.umd.min.js"
$jspdfUrl  = "https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js"

if (Test-Path $jspdfDest) {
  $kb = [math]::Round((Get-Item $jspdfDest).Length / 1KB, 0)
  Write-Host "  [SKIP] jsPDF already present ($kb KB)" -ForegroundColor Yellow
} else {
  Write-Host "  [DOWNLOAD] jsPDF 2.5.1 from cdnjs..." -ForegroundColor Cyan
  Invoke-WebRequest -Uri $jspdfUrl -OutFile $jspdfDest -UseBasicParsing
  $kb = [math]::Round((Get-Item $jspdfDest).Length / 1KB, 0)
  Write-Host "  [OK] jsPDF saved ($kb KB)" -ForegroundColor Green
}

# ── Generate PNG icons using System.Drawing ───────────────────────────────────
Add-Type -AssemblyName System.Drawing

function New-Icon {
  param ([int]$Size, [string]$OutPath)

  $bmp = New-Object System.Drawing.Bitmap($Size, $Size)
  $g   = [System.Drawing.Graphics]::FromImage($bmp)
  $g.SmoothingMode    = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
  $g.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::AntiAlias

  # Navy background
  $navy = [System.Drawing.Color]::FromArgb(15, 76, 138)
  $g.FillRectangle((New-Object System.Drawing.SolidBrush($navy)), 0, 0, $Size, $Size)

  # Orange accent bar at top (25% height)
  $orange = [System.Drawing.Color]::FromArgb(255, 107, 53)
  $barH   = [int]($Size * 0.25)
  $g.FillRectangle((New-Object System.Drawing.SolidBrush($orange)), 0, 0, $Size, $barH)

  # "VS" text centred in lower 75%
  $fontSize = [float]($Size * 0.34)
  $font     = New-Object System.Drawing.Font("Arial", $fontSize, [System.Drawing.FontStyle]::Bold)
  $white    = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::White)
  $fmt      = New-Object System.Drawing.StringFormat
  $fmt.Alignment     = [System.Drawing.StringAlignment]::Center
  $fmt.LineAlignment = [System.Drawing.StringAlignment]::Center
  $textRect = New-Object System.Drawing.RectangleF(0, ([float]$barH), [float]$Size, ([float]($Size - $barH)))
  $g.DrawString("VS", $font, $white, $textRect, $fmt)

  $bmp.Save($OutPath, [System.Drawing.Imaging.ImageFormat]::Png)

  $g.Dispose(); $bmp.Dispose(); $font.Dispose()
}

foreach ($size in @(16, 48, 128)) {
  $dest = "$dir\icons\icon${size}.png"
  if (Test-Path $dest) {
    Write-Host "  [SKIP] icon${size}.png already exists" -ForegroundColor Yellow
  } else {
    New-Icon -Size $size -OutPath $dest
    Write-Host "  [OK] icon${size}.png created" -ForegroundColor Green
  }
}

# ── Done ──────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "  Setup complete! Now load the extension in Chrome:" -ForegroundColor Cyan
Write-Host ""
Write-Host "    1. Go to  chrome://extensions/" -ForegroundColor White
Write-Host "    2. Enable 'Developer mode'  (toggle, top right)" -ForegroundColor White
Write-Host "    3. Click  'Load unpacked'" -ForegroundColor White
Write-Host "    4. Select this folder:" -ForegroundColor White
Write-Host "       $dir" -ForegroundColor Yellow
Write-Host ""
