# ============================================
# ZenClip Video Clipper - PowerShell Script
# ============================================
# Usage: .\clip_video.ps1 -VideoPath "path\to\video.mp4" -NumClips 3
# ============================================

param(
    [Parameter(Mandatory=$true)]
    [string]$VideoPath,

    [int]$NumClips = 3,
    [int]$MinDuration = 30,
    [string]$AspectRatio = "9:16",
    [bool]$AddSubtitles = $true,
    [bool]$AddHook = $false,
    [string]$SubtitleStyle = "shadow",
    [string]$BackendPort = "9478"
)

# Configuration
$BackendUrl = "http://127.0.0.1:$BackendPort"
$PythonExe = "D:\Extend_C\Program\zenclip\resources\backend_sidecar\python\python.exe"
$BackendDir = "D:\Extend_C\Program\zenclip\audit\recovery-workspace\backend"
$OutputDir = "D:\Extend_C\Program\zenclip\audit\recovery-workspace\static\clips"

# Colors
function Write-Header {
    param([string]$Text)
    Write-Host ""
    Write-Host "=" * 50 -ForegroundColor Cyan
    Write-Host "  $Text" -ForegroundColor Cyan
    Write-Host "=" * 50 -ForegroundColor Cyan
}

function Write-Success {
    param([string]$Text)
    Write-Host "✓ $Text" -ForegroundColor Green
}

function Write-Error-Custom {
    param([string]$Text)
    Write-Host "✗ $Text" -ForegroundColor Red
}

function Write-Info {
    param([string]$Text)
    Write-Host "  $Text" -ForegroundColor Gray
}

# Start
Write-Header "ZenClip Video Clipper"

# Validate video
if (-not (Test-Path $VideoPath)) {
    Write-Error-Custom "Video not found: $VideoPath"
    exit 1
}

$VideoInfo = Get-Item $VideoPath
Write-Info "Video: $($VideoInfo.Name)"
Write-Info "Size: $([math]::Round($VideoInfo.Length / 1MB, 1)) MB"
Write-Info "Clips: $NumClips"
Write-Info "Min Duration: ${MinDuration}s"
Write-Info "Aspect: $AspectRatio"

# Check backend
Write-Host ""
Write-Host "Checking backend..." -NoNewline
try {
    $Health = Invoke-RestMethod -Uri "$BackendUrl/health" -TimeoutSec 5
    Write-Success "Backend running"
} catch {
    Write-Host " Starting..." -NoNewline
    Start-Process -FilePath $PythonExe -ArgumentList "$BackendDir\run_backend.py" -WindowStyle Hidden
    Start-Sleep -Seconds 8

    try {
        $Health = Invoke-RestMethod -Uri "$BackendUrl/health" -TimeoutSec 5
        Write-Success "Backend started"
    } catch {
        Write-Error-Custom "Failed to start backend"
        exit 1
    }
}

# Submit job
Write-Host ""
Write-Host "Submitting video..." -NoNewline

$Form = @{
    video = Get-Item -Path $VideoPath
    num_clips = $NumClips
    min_duration = $MinDuration
    add_subtitles = $AddSubtitles.ToString().ToLower()
    add_viral_hook = $AddHook.ToString().ToLower()
    aspect_ratio = $AspectRatio
    subtitle_style = $SubtitleStyle
}

$Boundary = [System.Guid]::NewGuid().ToString()
$LF = "`r`n"
$BodyLines = @()

foreach ($Key in $Form.Keys) {
    if ($Key -eq "video") {
        $File = $Form[$Key]
        $BodyLines += "--$Boundary"
        $BodyLines += "Content-Disposition: form-data; name=`"$Key`"; filename=`"$($File.Name)`""
        $BodyLines += "Content-Type: video/mp4$LF"
        $BodyLines += [System.IO.File]::ReadAllBytes($File.FullName)
    } else {
        $BodyLines += "--$Boundary"
        $BodyLines += "Content-Disposition: form-data; name=`"$Key`"$LF"
        $BodyLines += $Form[$Key]
    }
}
$BodyLines += "--$Boundary--$LF"

try {
    $Response = Invoke-RestMethod -Uri "$BackendUrl/process" -Method Post -ContentType "multipart/form-data; boundary=$Boundary" -Body ($BodyLines -join $LF)
    $JobId = $Response.job_id
    Write-Success "Job submitted"
    Write-Info "Job ID: $JobId"
} catch {
    Write-Error-Custom "Failed to submit job"
    Write-Host $_.Exception.Message
    exit 1
}

# Monitor progress
Write-Host ""
Write-Host "Processing..." -NoNewline

$Status = "processing"
$Progress = 0
$Dots = 0

while ($Status -eq "processing" -or $Status -eq "queued") {
    Start-Sleep -Seconds 5

    try {
        $StatusResponse = Invoke-RestMethod -Uri "$BackendUrl/status/$JobId" -TimeoutSec 10
        $Status = $StatusResponse.status
        $Progress = $StatusResponse.progress

        $Dots++
        if ($Dots -gt 3) { $Dots = 1 }

        Write-Host "`rProcessing" -NoNewline
        Write-Host ("." * $Dots) -NoNewline
        Write-Host " $Progress%" -NoNewline -ForegroundColor Yellow
    } catch {
        Write-Host "`rProcessing..." -NoNewline
    }
}

Write-Host ""

if ($Status -eq "complete") {
    Write-Header "SUCCESS!"
    Write-Success "Clips created successfully!"
    Write-Host ""
    Write-Host "Output folder:" -ForegroundColor White
    Write-Host "  $OutputDir\$JobId\" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Clips:" -ForegroundColor White

    $Clips = Get-ChildItem -Path "$OutputDir\$JobId\*.mp4" -ErrorAction SilentlyContinue
    foreach ($Clip in $Clips) {
        $SizeMB = [math]::Round($Clip.Length / 1MB, 1)
        Write-Host "  ✓ $($Clip.Name) ($SizeMB MB)" -ForegroundColor Green
    }

    Write-Host ""
    Write-Host "Open output folder? (Y/N)" -NoNewline
    $Open = Read-Host
    if ($Open -eq "Y" -or $Open -eq "y") {
        explorer "$OutputDir\$JobId"
    }
} else {
    Write-Header "ERROR"
    Write-Error-Custom "Processing failed"
    Write-Info "Status: $Status"
}
