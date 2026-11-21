@echo off
setlocal
title Pygenesis Unreal - Setup
cd /d "%~dp0"

powershell.exe -NoProfile -ExecutionPolicy Bypass -STA -File "%~dp0setup_window.ps1"
set EXITCODE=%ERRORLEVEL%
if %EXITCODE% neq 0 (
  echo.
  echo  La ventana de instalacion no pudo abrirse (codigo %EXITCODE%).
  pause
)
exit /b %EXITCODE%
