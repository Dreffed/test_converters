# Saving Your Codex CLI Session

This project includes a helper script to record your terminal/chat output to a file using PowerShell transcripts.

## Quick Start
- Start recording:
  - `./scripts/save-chat.ps1 -Start`
- Stop recording:
  - `./scripts/save-chat.ps1 -Stop`

By default, transcripts are saved to `planning/chat_YYYYMMDD_HHMMSS.txt`.

## Custom Destination
- Start with a custom path (relative or absolute):
  - `./scripts/save-chat.ps1 -Start -Path planning/my_chat.txt`

## Tips
- If a transcript is already running, `-Start` will warn you. Run `-Stop` first to end the current transcript.
- You can keep a single rolling file by always using the same `-Path` with `-Start`; content is appended.

## Optional: Add a Convenient Alias
Add this to your PowerShell profile (`$PROFILE`):

```powershell
Set-Alias scstart  (Resolve-Path ./scripts/save-chat.ps1)
Set-Alias scstop   (Resolve-Path ./scripts/save-chat.ps1)
Function Start-Chat { & scstart -Start }
Function Stop-Chat  { & scstop -Stop }
```

Then use:
- `Start-Chat` to begin
- `Stop-Chat` to end

## Alternatives
- Manual transcript: `Start-Transcript -Path planning\chat.txt -Append` / `Stop-Transcript`
- Pipe/tee: `your-command 2>&1 | Tee-Object -FilePath planning\chat.log -Append`

> Note: The script is Windows PowerShell/PowerShell 7 friendly. On macOS/Linux, use `script` or `tee` equivalents.

