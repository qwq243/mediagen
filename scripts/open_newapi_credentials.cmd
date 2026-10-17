@echo off
title NewAPI Image Credentials
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0configure_newapi_credentials.ps1"
set "result=%errorlevel%"
if not "%result%"=="0" (
  echo.
  echo Configuration failed. The error is shown above.
  pause
)
exit /b %result%
