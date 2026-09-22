@echo off
REM ============================================================
REM ÿ�ճֲַ����������ɣ�Windows�棬�ȼ��� generate_daily_report.sh��
REM ���̣��������� �� �¼����� �� ��ȱ��棨��������+�¼����ݣ�
REM �ɼƻ�����"StockDailyReports"ÿ�� 16:35 �Զ����ã�Ҳ���ֶ�˫��ִ��
REM ============================================================

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

REM ���ػ���ȫ�����ڣ�yyyyMMdd��
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd"') do set "TODAY=%%i"
if not exist "%SCRIPT_DIR%reports" mkdir "%SCRIPT_DIR%reports"
set "LOG_FILE=%SCRIPT_DIR%reports\cron_%TODAY%.log"

REM Python�����ȱ��� venv�����ϵͳ PATH �е� python
set "PY=python"
if exist "%SCRIPT_DIR%venv\Scripts\python.exe" set "PY=%SCRIPT_DIR%venv\Scripts\python.exe"

echo [%date% %time%] ��ʼ���ɳֲַ������棨����-�¼�-��ȣ�... >> "%LOG_FILE%"

echo [%date% %time%] [1/3] �����г���������... >> "%LOG_FILE%"
%PY% emotion_engine.py >> "%LOG_FILE%" 2>&1

echo [%date% %time%] [2/3] �����¼���������... >> "%LOG_FILE%"
%PY% event_tracker.py >> "%LOG_FILE%" 2>&1

echo [%date% %time%] [3/3] ������ȷ�������... >> "%LOG_FILE%"
%PY% deep_analysis.py >> "%LOG_FILE%" 2>&1

if %errorlevel% equ 0 (
    echo [%date% %time%] �������ɳɹ� >> "%LOG_FILE%"
) else (
    echo [%date% %time%] ��������ʧ�ܣ�����Ϸ���־�� >> "%LOG_FILE%"
)
echo [%date% %time%] [4/4] LLM narrative enhancement (deep-thinking ~5min/stock; auto-skip if no KIMI_API_KEY)... >> "%LOG_FILE%"
%PY% tools\llm_narrative.py --think >> "%LOG_FILE%" 2>&1
echo --- >> "%LOG_FILE%"
echo ��ɡ���־��reports\cron_%TODAY%.log
