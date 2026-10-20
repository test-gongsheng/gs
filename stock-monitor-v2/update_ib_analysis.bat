@echo off
:: ============================================================
:: 国际投行观点报告生成 - 联网检索并生成 reports\ib_analysis_latest.md
:: 双击运行，约1-3分钟；详细日志见 logs\ib_analysis.log
:: ============================================================
setlocal
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

REM Python解释器：仓库venv优先（update.bat维护，依赖齐全），兜底py启动器
set "PYTHON_PATH=py"
if exist "%SCRIPT_DIR%venv\Scripts\python.exe" set "PYTHON_PATH=%SCRIPT_DIR%venv\Scripts\python.exe"
%PYTHON_PATH% --version >nul 2>&1
if errorlevel 1 (
    echo [错误] Python不可用：venv\Scripts\python.exe 和 py 启动器都没找到
    pause
    exit /b 1
)

echo 使用Python: %PYTHON_PATH%
%PYTHON_PATH% --version

if not exist "%SCRIPT_DIR%logs" mkdir "%SCRIPT_DIR%logs"

echo [%date% %time%] 开始生成国际投行观点报告... >> logs\ib_analysis.log
%PYTHON_PATH% update_ib_analysis.py >> logs\ib_analysis.log 2>&1
set "EXIT_CODE=%ERRORLEVEL%"
echo [%date% %time%] 执行结束，退出码 %EXIT_CODE% >> logs\ib_analysis.log

echo.
echo 执行完成，退出码 %EXIT_CODE%，详细日志见 logs\ib_analysis.log
echo 刷新页面即可在国际投行观点板块看到报告
pause
endlocal & exit /b %EXIT_CODE%