@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

title FAWU Starter
set "PROJECT_ROOT=%CD%"
set "UV_CACHE_DIR=%PROJECT_ROOT%\.uv-cache"
set "FAWU_BOOTSTRAP_PASSWORD=admin123"

echo [1/5] Checking required tools...
set "UV_EXE="
for /f "delims=" %%I in ('where uv 2^>nul') do if not defined UV_EXE set "UV_EXE=%%I"
if not defined UV_EXE if exist "%LOCALAPPDATA%\Microsoft\WinGet\Links\uv.exe" set "UV_EXE=%LOCALAPPDATA%\Microsoft\WinGet\Links\uv.exe"
if not defined UV_EXE if exist "%USERPROFILE%\.local\bin\uv.exe" set "UV_EXE=%USERPROFILE%\.local\bin\uv.exe"
if not defined UV_EXE if exist "%USERPROFILE%\.cargo\bin\uv.exe" set "UV_EXE=%USERPROFILE%\.cargo\bin\uv.exe"
if not defined UV_EXE goto :missing_uv
for %%I in ("%UV_EXE%") do set "UV_DIR=%%~dpI"
set "PATH=%UV_DIR%;%PATH%"
where npm >nul 2>nul
if errorlevel 1 goto :missing_node

echo [2/5] Syncing Python dependencies...
call uv sync --extra dev --python 3.13
if errorlevel 1 goto :failed

echo [3/5] Installing frontend dependencies when needed...
if not exist "%PROJECT_ROOT%\frontend\node_modules" (
    call npm --prefix "%PROJECT_ROOT%\frontend" install
    if errorlevel 1 goto :failed
)

echo [4/5] Migrating database and preparing demo account...
call uv run python backend\manage.py migrate --noinput
if errorlevel 1 goto :failed
call uv run python backend\manage.py bootstrap_demo --username admin --allow-insecure-password
if errorlevel 1 goto :failed

if /i "%~1"=="--prepare-only" (
    echo FAWU preparation completed successfully.
    exit /b 0
)

echo [5/5] Starting FAWU services...
start "FAWU Backend" /D "%PROJECT_ROOT%" cmd.exe /k "set UV_CACHE_DIR=%PROJECT_ROOT%\.uv-cache&&uv run python backend\manage.py runserver 0.0.0.0:8000"
start "FAWU Document Service" /D "%PROJECT_ROOT%" cmd.exe /k "set UV_CACHE_DIR=%PROJECT_ROOT%\.uv-cache&&uv run uvicorn services.document_api.main:app --reload --port 8001"
start "FAWU Frontend" /D "%PROJECT_ROOT%\frontend" cmd.exe /k "npm run dev"

echo.
echo FAWU is starting. Three service windows have been opened.
echo Web:      http://localhost:5173
echo Admin:    http://localhost:8000/admin/
echo API docs: http://localhost:8001/docs
echo Login:    admin / admin123
echo.
echo Close the three service windows, or press Ctrl+C in each one, to stop FAWU.
timeout /t 4 /nobreak >nul
start "" "http://localhost:5173"
exit /b 0

:missing_uv
echo.
echo [ERROR] uv was not found. Install it first: https://docs.astral.sh/uv/
pause
exit /b 1

:missing_node
echo.
echo [ERROR] npm was not found. Install Node.js 20 or newer first: https://nodejs.org/
pause
exit /b 1

:failed
echo.
echo [ERROR] Startup preparation failed. Review the message above.
pause
exit /b 1
