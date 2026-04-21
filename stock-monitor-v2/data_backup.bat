@echo off
chcp 65001 >nul
:: Windows 数据备份脚本
:: 放在 stock-monitor-v2 目录下使用

set "DATA_DIR=%USERPROFILE%\stock-monitor-data"
set "REPO_DIR=%CD%"

if not exist "%DATA_DIR%" mkdir "%DATA_DIR%"

if "%1"=="backup" goto backup
if "%1"=="restore" goto restore
if "%1"=="status" goto status

echo 用法: data_backup.bat {backup^|restore^|status}
echo.
echo   backup  - 备份持仓数据
echo   restore - 恢复持仓数据
echo   status  - 查看状态
goto end

:backup
echo [备份] 保存数据到 %DATA_DIR%
if exist "%REPO_DIR%\data\stocks.json" (
    copy /Y "%REPO_DIR%\data\stocks.json" "%DATA_DIR%\stocks.json.bak"
    echo [备份] stocks.json 已备份
)
if exist "%REPO_DIR%\data\stocks.db" (
    copy /Y "%REPO_DIR%\data\stocks.db" "%DATA_DIR%\stocks.db.bak"
    echo [备份] stocks.db 已备份
)
echo [备份] 完成
goto end

:restore
echo [恢复] 从 %DATA_DIR% 恢复数据
if exist "%DATA_DIR%\stocks.json.bak" (
    copy /Y "%DATA_DIR%\stocks.json.bak" "%REPO_DIR%\data\stocks.json"
    echo [恢复] stocks.json 已恢复
) else (
    echo [恢复] 警告：找不到备份
)
if exist "%DATA_DIR%\stocks.db.bak" (
    copy /Y "%DATA_DIR%\stocks.db.bak" "%REPO_DIR%\data\stocks.db"
    echo [恢复] stocks.db 已恢复
)
echo [恢复] 完成
goto end

:status
echo === 备份目录 ===
dir "%DATA_DIR%"
echo.
echo === 当前数据 ===
dir "%REPO_DIR%\data"
goto end

:end
pause
