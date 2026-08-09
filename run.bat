@echo off
REM Aurati Studio launcher — wraps run.ps1 so double-clicking works.
REM Pass-through flags: run.bat -Setup | -DryRun | -BackendOnly
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run.ps1" %*
if errorlevel 1 (
  echo.
  echo Startup failed. See the message above.
  pause
)
