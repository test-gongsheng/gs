@echo off
chcp 65001 >nul
title 股票分析报告定时任务设置
cls
echo ============================================
echo   股票监控系统 - 自动定时任务设置
echo ============================================
echo.

REM 获取当前脚本所在目录
set "SCRIPT_DIR=%~dp0"
set "PYTHON_PATH=python3"

REM 检查Python是否可用
%PYTHON_PATH% --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 python3，尝试使用 python...
    set "PYTHON_PATH=python"
    %PYTHON_PATH% --version >nul 2>&1
    if errorlevel 1 (
        echo [错误] 未找到Python，请确保Python已安装并添加到PATH
        pause
        exit /b 1
    )
)

echo [✓] Python路径: %PYTHON_PATH%
echo [✓] 脚本目录: %SCRIPT_DIR%
echo.

REM 创建日志目录
if not exist "%SCRIPT_DIR%logs" mkdir "%SCRIPT_DIR%logs"

REM 删除旧任务（如果存在）
schtasks /delete /tn "StockPortfolioAnalysis" /f >nul 2>&1

REM 创建定时任务 - 每天16:05（港股收盘后5分钟）
echo [1/2] 正在创建定时任务（每日16:05执行）...
schtasks /create /tn "StockPortfolioAnalysis" ^
    /tr "cmd /c cd /d \"%SCRIPT_DIR%\" ^&^& %PYTHON_PATH% update_portfolio_analysis.py ^>^> logs\\analysis_cron.log 2^>^&1" ^
    /sc daily ^
    /st 16:05 ^
    /np ^
    /rl HIGHEST >nul 2>&1

if errorlevel 1 (
    echo [✗] 创建失败，尝试使用管理员权限...
    echo 请以管理员身份运行此脚本
    pause
    exit /b 1
)

echo [✓] 定时任务创建成功！
echo.

REM 创建立即执行脚本
echo [2/2] 创建桌面快捷方式...
set "DESKTOP=%USERPROFILE%\Desktop"
(
echo @echo off
chcp 65001 >nul
cd /d "%SCRIPT_DIR%"
echo 正在生成持仓分析报告...
%PYTHON_PATH% update_portfolio_analysis.py
echo.
echo 按任意键关闭...
pause >nul
) > "%DESKTOP%\生成股票分析报告.bat"

echo [✓] 桌面快捷方式已创建：生成股票分析报告.bat
echo.
echo ============================================
echo   设置完成！
echo ============================================
echo.
echo [定时任务]
echo   名称: StockPortfolioAnalysis
echo   时间: 每日 16:05（港股收盘后5分钟）
echo   操作: 自动生成持仓分析报告
echo.
echo [手动执行]
echo   双击桌面"生成股票分析报告.bat"
echo.
echo [查看日志]
echo   %SCRIPT_DIR%logs\analysis_cron.log
echo.
pause
