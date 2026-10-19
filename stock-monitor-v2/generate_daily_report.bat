@echo off
REM ============================================================
REM 每日持仓分析报告生成（Windows版，优先用 generate_daily_report.sh）
REM 流程：情绪引擎 -> 事件追踪 -> 深度分析（含新闻+事件数据）
REM 计划任务"StockDailyReports"每日 16:35 自动运行，也可手动双击执行
REM ============================================================

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

REM 获取当前完整日期（yyyyMMdd）
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd"') do set "TODAY=%%i"
if not exist "%SCRIPT_DIR%reports" mkdir "%SCRIPT_DIR%reports"
set "LOG_FILE=%SCRIPT_DIR%reports\cron_%TODAY%.log"

REM Python优先用 venv，其次系统 PATH 中的 python
set "PY=python"
if exist "%SCRIPT_DIR%venv\Scripts\python.exe" set "PY=%SCRIPT_DIR%venv\Scripts\python.exe"

echo [%date% %time%] 开始生成持仓分析报告（情绪-事件-深度）... >> "%LOG_FILE%"

echo [%date% %time%] [1/3] 运行情绪引擎... >> "%LOG_FILE%"
%PY% emotion_engine.py >> "%LOG_FILE%" 2>&1

echo [%date% %time%] [2/3] 运行事件追踪... >> "%LOG_FILE%"
%PY% event_tracker.py >> "%LOG_FILE%" 2>&1

echo [%date% %time%] [3/3] 生成深度分析... >> "%LOG_FILE%"
%PY% deep_analysis.py >> "%LOG_FILE%" 2>&1

if %errorlevel% equ 0 (
    echo [%date% %time%] 深度分析成功 >> "%LOG_FILE%"
) else (
    echo [%date% %time%] 深度分析失败，详情见上方日志 >> "%LOG_FILE%"
)
echo [%date% %time%] [4/4] LLM narrative enhancement (deep-thinking ~5min/stock; auto-skip if no KIMI_API_KEY)... >> "%LOG_FILE%"
%PY% tools\llm_narrative.py --think >> "%LOG_FILE%" 2>&1

echo [%date% %time%] [5/5] Market regime signal engine (ETF flow, auto-collect + graceful degrade)... >> "%LOG_FILE%"
%PY% utils\etf_flow_signal.py >> "%LOG_FILE%" 2>&1
if %errorlevel% neq 0 echo [%date% %time%] WARN: market regime engine failed (non-blocking) >> "%LOG_FILE%"
echo --- >> "%LOG_FILE%"
echo 完成，日志：reports\cron_%TODAY%.log
