# Environment Setup

The user must set a key locally. Do not ask them to paste secrets into chat.

## Key source preference

Prefer the Windows user-level `NEWAPI_API_KEY` so a newly entered key is available without restarting Codex; fall back to the current process and then `OPENAI_API_KEY` only when already set by the user.

## Recommended interactive Windows setup

```powershell
C:/Users/USER/.codex/skills/mediagen/scripts/open_newapi_credentials.cmd
```

The launcher opens a hidden-input prompt, keeps parser/runtime errors visible instead of flashing closed, writes `NEWAPI_BASE_URL` and `NEWAPI_API_KEY` to the current Windows user environment, validates only the format and never displays the key. The underlying PowerShell script must remain UTF-8 with BOM for Windows PowerShell 5.1 compatibility.

## PowerShell session-only example

```powershell
$env:NEWAPI_BASE_URL = "https://netcup-1.toapi.xyz/v1"
$env:NEWAPI_API_KEY = "<set locally; do not paste in chat>"
```

## Persistent user environment example

```powershell
[Environment]::SetEnvironmentVariable("NEWAPI_BASE_URL", "https://netcup-1.toapi.xyz/v1", "User")
[Environment]::SetEnvironmentVariable("NEWAPI_API_KEY", "<set locally; do not paste in chat>", "User")
```
