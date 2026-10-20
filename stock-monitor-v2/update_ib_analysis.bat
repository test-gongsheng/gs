@echo off
:: ============================================================
:: 国际投行观点报告生成 - 联网检索并生成 reports\ib_analysis_latest.md
:: 双击运行，约1-3分钟；详细日志见 logs\ib_analysis.log
:: ============================================================
setlocal
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

REM 探测Python：PATH(python3/python/py启动器) → 常见安装目录
set "PYTHON_PATH="
for %%P in (python3 python py) do (
    if not defined PYTHON_PATH (
        %%P --version >nul 2>&1
        if not errorlevel 1 set "PYTHON_PATH=%%P"
    )
)
if not defined PYTHON_PATH (
    for %%D in ("%LOCALAPPDATA%\Programs\Python\Python312" "%LOCALAPPDATA%\Programs\Python\Python311" "%LOCALAPPDATA%\Programs\Python\Python310" "%USERPROFILE%\anaconda3" "%USERPROFILE%\miniconda3" "C:\ProgramData\anaconda3" "C:\ProgramData\miniconda3") do (
        if not defined PYTHON_PATH (
            if exist "%%~D\python.exe" set "PYTHON_PATH=%%~D\python.exe"
        )
    )
)
if not defined PYTHON_PATH (
    echo [错误] 双击环境找不到Python。
    echo.
    echo 最快的办法：打开你平时启动股票系统的那个命令行窗口
    echo （比如 Anaconda Prompt / 开始菜单里的Python命令行），
    echo 输入以下命令后回车：
    echo.
    echo     python update_ib_analysis.py
    echo.
    echo 或者：把本bat拖进那个窗口里回车执行。
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