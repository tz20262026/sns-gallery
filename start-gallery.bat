@echo off
title SNS Gallery Server
echo.
echo =========================================
echo   SNS Gallery - Multilingual Stock Photos
echo =========================================
echo.

:: Change to script directory
cd /d "%~dp0"

:: Check if node_modules/express exists
if not exist "node_modules\express" (
  echo [!] First time setup: installing packages...
  npm install
  echo.
)

:: Kill any existing server on port 3000
for /f "tokens=5" %%a in ('netstat -aon ^| find ":3000" ^| find "LISTENING" 2^>nul') do (
  echo [i] Stopping existing server on port 3000 (PID: %%a)
  taskkill /PID %%a /F >nul 2>&1
)

echo [i] Starting server...
echo.
echo  Gallery:    http://localhost:3000/gallery.html
echo  Terms:      http://localhost:3000/terms.html
echo  API:        http://localhost:3000/api/categories
echo.
echo  Press Ctrl+C to stop the server.
echo.

node server.js

pause
