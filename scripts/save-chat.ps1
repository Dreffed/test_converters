<#!
.SYNOPSIS
  Start/stop saving your Codex CLI session output to a file.

.DESCRIPTION
  Wraps PowerShell Start-Transcript/Stop-Transcript for convenience.

.PARAMETER Start
  Begin a transcript. If no -Path is supplied, a file will be created under planning/ with a timestamped name.

.PARAMETER Stop
  End an active transcript.

.PARAMETER Path
  Optional path to the transcript file. If relative, it is resolved against the current directory.

.EXAMPLE
  ./scripts/save-chat.ps1 -Start
  ./scripts/save-chat.ps1 -Stop
#>
param(
  [switch]$Start,
  [switch]$Stop,
  [string]$Path
)

function New-DefaultTranscriptPath {
  $ts = Get-Date -Format 'yyyyMMdd_HHmmss'
  $defaultDir = Join-Path -Path (Get-Location) -ChildPath 'planning'
  if (-not (Test-Path $defaultDir)) { New-Item -ItemType Directory -Path $defaultDir | Out-Null }
  return Join-Path $defaultDir "chat_${ts}.txt"
}

if (-not $Start -and -not $Stop) {
  Write-Host "Usage:" -ForegroundColor Yellow
  Write-Host "  ./scripts/save-chat.ps1 -Start [-Path planning/chat.txt]" -ForegroundColor Yellow
  Write-Host "  ./scripts/save-chat.ps1 -Stop" -ForegroundColor Yellow
  exit 1
}

if ($Start) {
  if (-not $Path -or [string]::IsNullOrWhiteSpace($Path)) { $Path = New-DefaultTranscriptPath }
  $full = Resolve-Path -Path $Path -ErrorAction SilentlyContinue
  if (-not $full) {
    # Create parent directory if needed
    $parent = Split-Path -Path $Path -Parent
    if ($parent -and -not (Test-Path $parent)) { New-Item -ItemType Directory -Path $parent | Out-Null }
    $full = Resolve-Path -Path $Path -ErrorAction SilentlyContinue
  }
  try {
    if ($full) { Start-Transcript -Path $full -Append | Out-Null }
    else { Start-Transcript -Path $Path -Append | Out-Null }
    Write-Host "Transcript started ->" -NoNewline; Write-Host " $Path" -ForegroundColor Cyan
  }
  catch {
    Write-Warning "Failed to start transcript. There may already be an active transcript. Try running -Stop first."
    throw
  }
}

if ($Stop) {
  try {
    $r = Stop-Transcript 2>$null
    if ($r) { Write-Host ($r | Out-String) }
    else { Write-Host "Transcript stopped." }
  }
  catch {
    Write-Warning "No active transcript to stop."
  }
}

