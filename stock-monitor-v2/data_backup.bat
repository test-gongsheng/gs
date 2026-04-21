@echo off
:: Data Backup Script for Windows
:: Place in stock-monitor-v2 directory

set "DATA_DIR=%USERPROFILE%\stock-monitor-data"
set "REPO_DIR=%CD%"

if not exist "%DATA_DIR%" mkdir "%DATA_DIR%"

if "%1"=="backup" goto backup
if "%1"=="restore" goto restore
if "%1"=="status" goto status

echo Usage: data_backup.bat {backup^|restore^|status}
echo.
echo   backup  - Save portfolio data
echo   restore - Restore portfolio data
echo   status  - Check backup status
goto end

:backup
echo [Backup] Saving data to %DATA_DIR%
set "BACKUP_COUNT=0"

if exist "%REPO_DIR%\data\stocks.json" (
    copy /Y "%REPO_DIR%\data\stocks.json" "%DATA_DIR%\stocks.json.bak" >nul
    echo [OK] stocks.json backed up
    set /a "BACKUP_COUNT+=1"
)

if exist "%REPO_DIR%\data\stocks.db" (
    copy /Y "%REPO_DIR%\data\stocks.db" "%DATA_DIR%\stocks.db.bak" >nul
    echo [OK] stocks.db backed up
    set /a "BACKUP_COUNT+=1"
)

if exist "%REPO_DIR%\reports\portfolio_analysis_latest.json" (
    copy /Y "%REPO_DIR%\reports\portfolio_analysis_latest.json" "%DATA_DIR%\report.json.bak" >nul
    echo [OK] report backed up
    set /a "BACKUP_COUNT+=1"
)

echo [Done] %BACKUP_COUNT% files backed up
goto end

:restore
echo [Restore] Restoring data from %DATA_DIR%
set "RESTORE_COUNT=0"

if exist "%DATA_DIR%\stocks.json.bak" (
    copy /Y "%DATA_DIR%\stocks.json.bak" "%REPO_DIR%\data\stocks.json" >nul
    echo [OK] stocks.json restored
    set /a "RESTORE_COUNT+=1"
) else (
    echo [WARN] stocks.json backup not found
)

if exist "%DATA_DIR%\stocks.db.bak" (
    copy /Y "%DATA_DIR%\stocks.db.bak" "%REPO_DIR%\data\stocks.db" >nul
    echo [OK] stocks.db restored
    set /a "RESTORE_COUNT+=1"
)

echo [Done] %RESTORE_COUNT% files restored
goto end

:status
echo === Backup Directory ===
dir "%DATA_DIR%"
echo.
echo === Current Data ===
dir "%REPO_DIR%\data"
goto end

:end
pause
