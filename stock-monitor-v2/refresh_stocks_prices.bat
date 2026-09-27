@echo off
:: ============================================================
:: 持仓价格手动刷新 - 把真实行情写回 data\stocks.json
:: 每日16:05的分析任务已内置自动写回，本脚本用于随时手动修复
:: 支持参数: --dry-run 只预览不写文件
:: ============================================================
setlocal
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

if not exist "%SCRIPT_DIR%logs" mkdir "%SCRIPT_DIR%logs"

echo [%date% %time%] 开始刷新持仓价格... >> logs\price_refresh.log
python refresh_stocks_prices.py %* >> logs\price_refresh.log 2>&1
set "EXIT_CODE=%ERRORLEVEL%"
echo [%date% %time%] 结束，退出码 %EXIT_CODE% >> logs\price_refresh.log

type logs\price_refresh.log | more +0 >nul 2>nul
echo 结果已写入 logs\price_refresh.log，退出码 %EXIT_CODE%
endlocal & exit /b %EXIT_CODE%
