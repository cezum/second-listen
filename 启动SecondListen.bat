@echo off
setlocal EnableExtensions

rem Double-click this file to start the local demo and open the browser.
set "APP_DIR=%~dp0app"
set "URL=http://localhost:3000"

if not exist "%APP_DIR%\deployment\browser\server.py" (
  echo [ERROR] Cannot find the app folder:
  echo         %APP_DIR%
  pause
  exit /b 1
)

where python >nul 2>&1
if not errorlevel 1 (
  python "%APP_DIR%\start_local.py"
) else (
  where py >nul 2>&1
  if not errorlevel 1 (
    py -3 "%APP_DIR%\start_local.py"
  ) else (
    echo [ERROR] Python was not found. Please install Python 3 and try again.
    goto :failure
  )
)

if not errorlevel 1 (
  exit /b 0
)

:failure
echo [ERROR] The server did not become ready within 30 seconds.
echo Check the Second Listen server window for the error message.
pause
exit /b 1
