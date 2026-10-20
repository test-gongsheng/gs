@echo off
:: ============================================================
:: 国际投行观点报告生成 - 联网检索并生成 reports/ib_analysis_latest.md
:: 双击运行，约1-3分钟；详细日志见 logs\ib_analysis.log
:: ============================================================
setlocal
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

if not exist "%SCRIPT_DIR%logs" mkdir "%SCRIPT_DIR%logs"

echo [%date% %time%] 开始生成国际投行观点报告... >> logs\ib_analysis.log
python update_ib_analysis.py >> logs\ib_analysis.log 2>&1
set "EXIT_CODE=%ERRORLEVEL%"
echo [%date% %time%] 执行结束，退出码 %EXIT_CODE% >> logs\ib_analysis.log

echo.
echo 执行完成，退出码 %EXIT_CODE%，详细日志见 logs\ib_analysis.log
echo 刷新页面即可在国际投行观点板块看到报告
pause
endlocal & exit /b %EXIT_CODE%
