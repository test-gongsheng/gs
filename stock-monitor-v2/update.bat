@echo off
:: ============================================================
:: Stock Monitor - Auto Update Script
:: One-click: backup, download, restore, restart
:: ============================================================

setlocal EnableDelayedExpansion

echo ========================================
echo Stock Monitor - Auto Update
echo ========================================
echo.

set "REPO_DIR=%CD%"
set "DATA_DIR=%USERPROFILE%\stock-monitor-data"
set "TEMP_DIR=%TEMP%\stock-monitor-update"
set "GITHUB_URL=https://github.com/test-gongsheng/gs/archive/refs/heads/master.zip"
set "MIRROR_URL=https://ghproxy.com/https://github.com/test-gongsheng/gs/archive/refs/heads/master.zip"

:: Check directory
if not exist "%REPO_DIR%\app.py" (
    echo [ERROR] Not in stock-monitor-v2 directory!
    pause
    exit /b 1
)

echo Current: %REPO_DIR%
echo Backup:  %DATA_DIR%
echo.

:: ============================================================
:: Step 1: Backup Data
:: ============================================================
echo [Step 1/6] Backup data...

if not exist "%DATA_DIR%" mkdir "%DATA_DIR%"

set "BACKUP_COUNT=0"

if exist "%REPO_DIR%\data\stocks.json" (
    copy /Y "%REPO_DIR%\data\stocks.json" "%DATA_DIR%\stocks.json.bak" >nul
    echo [OK] stocks.json saved
    set /a "BACKUP_COUNT+=1"
)

if exist "%REPO_DIR%\data\stocks.db" (
    copy /Y "%REPO_DIR%\data\stocks.db" "%DATA_DIR%\stocks.db.bak" >nul
    echo [OK] stocks.db saved
    set /a "BACKUP_COUNT+=1"
)

if exist "%REPO_DIR%\reports\portfolio_analysis_latest.json" (
    copy /Y "%REPO_DIR%\reports\portfolio_analysis_latest.json" "%DATA_DIR%\report.json.bak" >nul
    echo [OK] report saved
    set /a "BACKUP_COUNT+=1"
)

echo [Info] %BACKUP_COUNT% files backed up
echo.

:: ============================================================
:: Step 2: Stop Service
:: ============================================================
echo [Step 2/6] Stop service...

taskkill /F /IM python.exe 2>nul

for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8888') do (
    taskkill /F /PID %%a 2>nul
)

echo [OK] Service stopped
echo.

:: ============================================================
:: Step 3: Download Latest Code
:: ============================================================
echo [Step 3/6] Download latest code...

if exist "%TEMP_DIR%" rmdir /S /Q "%TEMP_DIR%"
mkdir "%TEMP_DIR%"

set "DL_OK=0"

:: Try mirror first
echo [Info] Downloading (mirror)...
powershell -Command "try { Invoke-WebRequest -Uri '%MIRROR_URL%' -OutFile '%TEMP_DIR%\master.zip' -TimeoutSec 60; exit 0 } catch { exit 1 }" 2>nul

if exist "%TEMP_DIR%\master.zip" (
    for %%F in ("%TEMP_DIR%\master.zip") do (
        if %%~zF GTR 1000 (
            echo [OK] Downloaded from mirror
            set "DL_OK=1"
        )
    )
)

:: Fallback to direct
if "%DL_OK%"=="0" (
    echo [Info] Mirror failed, trying direct...
    powershell -Command "try { Invoke-WebRequest -Uri '%GITHUB_URL%' -OutFile '%TEMP_DIR%\master.zip' -TimeoutSec 120; exit 0 } catch { exit 1 }" 2>nul
    
    if exist "%TEMP_DIR%\master.zip" (
        for %%F in ("%TEMP_DIR%\master.zip") do (
            if %%~zF GTR 1000 (
                echo [OK] Downloaded from GitHub
                set "DL_OK=1"
            )
        )
    )
)

if "%DL_OK%"=="0" (
    echo [ERROR] Download failed!
    echo [ERROR] Please check network or download manually.
    pause
    exit /b 1
)

echo.

:: ============================================================
:: Step 4: Extract and Replace
:: ============================================================
echo [Step 4/6] Extract and replace...

powershell -Command "Expand-Archive -Path '%TEMP_DIR%\master.zip' -DestinationPath '%TEMP_DIR%\extracted' -Force" 2>nul

if not exist "%TEMP_DIR%\extracted\gs-master" (
    echo [ERROR] Extract failed!
    pause
    exit /b 1
)

:: Save data temporarily
if exist "%REPO_DIR%\data" (
    xcopy /E /I /Y "%REPO_DIR%\data" "%TEMP_DIR%\data_save" >nul 2>nul
)

:: Remove old code (keep venv)
for /d %%D in ("%REPO_DIR%\*") do (
    if /I not "%%~nxD"=="data" (
        if /I not "%%~nxD"=="venv" (
            if /I not "%%~nxD"=="__pycache__" (
                rmdir /S /Q "%%D" 2>nul
            )
        )
    )
)

for %%F in ("%REPO_DIR%\*") do (
    if /I not "%%~nxF"=="data_backup.bat" (
        if /I not "%%~nxF"=="update.bat" (
            del /F /Q "%%F" 2>nul
        )
    )
)

:: Copy new code
xcopy /E /I /Y "%TEMP_DIR%\extracted\gs-master\stock-monitor-v2\*" "%REPO_DIR%\" >nul 2>nul

:: Restore data if accidentally removed
if exist "%TEMP_DIR%\data_save" (
    xcopy /E /I /Y "%TEMP_DIR%\data_save\*" "%REPO_DIR%\data\" >nul 2>nul
    rmdir /S /Q "%TEMP_DIR%\data_save" 2>nul
)

echo [OK] Code updated
echo.

:: ============================================================
:: Step 5: Restore Data
:: ============================================================
echo [Step 5/6] Restore data...

set "RESTORE_COUNT=0"

if exist "%DATA_DIR%\stocks.json.bak" (
    copy /Y "%DATA_DIR%\stocks.json.bak" "%REPO_DIR%\data\stocks.json" >nul
    echo [OK] stocks.json restored
    set /a "RESTORE_COUNT+=1"
) else (
    echo [WARN] No stocks.json backup found
)

if exist "%DATA_DIR%\stocks.db.bak" (
    copy /Y "%DATA_DIR%\stocks.db.bak" "%REPO_DIR%\data\stocks.db" >nul
    echo [OK] stocks.db restored
    set /a "RESTORE_COUNT+=1"
)

echo [Info] %RESTORE_COUNT% files restored
echo.

:: ============================================================
:: Step 6: Start Service
:: ============================================================
echo [Step 6/6] Start service...

if exist "%REPO_DIR%\venv\Scripts\python.exe" (
    start /B "" "%REPO_DIR%\venv\Scripts\python.exe" "%REPO_DIR%\app.py" > "%REPO_DIR%\app.log" 2>&1
) else (
    start /B "" python "%REPO_DIR%\app.py" > "%REPO_DIR%\app.log" 2>&1
)

timeout /t 3 /nobreak >nul

curl -s http://localhost:8888/api/stocks >nul 2>nul
if %ERRORLEVEL%==0 (
    echo [OK] Service started at http://localhost:8888
) else (
    echo [WARN] Service may still be starting...
)

echo.

:: Cleanup
rmdir /S /Q "%TEMP_DIR%" 2>nul

:: ============================================================
:: Done
:: ============================================================
echo ========================================
echo [DONE] Update complete!
echo ========================================
echo.

echo Data status:
if exist "%REPO_DIR%\data\stocks.json" (
    for %%F in ("%REPO_DIR%\data\stocks.json") do (
        if %%~zF GTR 1000 (
            echo   [OK] stocks.json exists (%%~zF bytes)
        ) else (
            echo   [WARN] stocks.json is empty - need to import!
        )
    )
)
echo.
echo Open browser: http://localhost:8888
echo.
pause
