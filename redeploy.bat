@echo off
chcp 65001 >nul
echo ==========================================
echo 股票监控系统 - Windows 完全重新部署脚本
echo ==========================================
echo.

:: 步骤1: 停止现有服务
echo === 步骤1: 停止现有 Python 进程 ===
taskkill /F /IM python.exe 2>nul
taskkill /F /IM pythonw.exe 2>nul
timeout /t 2 >nul

:: 步骤2: 删除旧代码
echo === 步骤2: 删除旧代码 ===
cd /d C:\
if exist "test" (
    rmdir /S /Q test 2>nul
    echo 已删除 C:\test
)

:: 步骤3: 创建新目录并克隆
echo === 步骤3: 重新克隆代码 ===
mkdir C:\test 2>nul
cd /d C:\test
git clone https://github.com/test-gongsheng/gs.git
cd gs\stock-monitor-v2\stock-monitor-v2

echo === 步骤4: 验证版本 ===
git log --oneline -1

echo === 步骤5: 创建数据目录 ===
if not exist "data" mkdir data

:: 创建默认数据文件
echo {"stocks": [], "portfolio": {"totalValue": 0, "totalCost": 0, "totalPnl": 0, "riskLevel": "normal"}, "lastUpdate": null} > data\stocks.json

echo === 步骤6: 创建每日报告批处理文件 ===
(
echo @echo off
echo chcp 65001 ^>nul
echo cd /d "C:\test\stock-monitor-v2\stock-monitor-v2"
echo call venv\Scripts\activate.bat
echo python update_portfolio_analysis.py ^>^> reports\cron_%%date:~0,4%%%%date:~5,2%%%%date:~8,2%%.log 2^>^&1
) > generate_daily_report.bat
echo 已创建 generate_daily_report.bat

echo === 步骤7: 配置 Windows 任务计划程序 ===
echo 正在创建每日自动报告任务...
schtasks /create /tn "StockDailyReport" /tr "C:\test\stock-monitor-v2\stock-monitor-v2\generate_daily_report.bat" /sc daily /st 16:35 /f >nul 2>&1
if %errorlevel% equ 0 (
    echo 任务计划创建成功：每天 16:35 自动执行
) else (
    echo 任务计划已存在或创建失败，请手动检查
)

echo === 步骤8: 启动服务 ===
start /B python app.py > server.log 2>&1
timeout /t 3 >nul

echo === 步骤9: 验证服务 ===
curl -s http://localhost:8888/api/stocks >nul 2>&1
if %errorlevel% equ 0 (
    echo 服务启动成功，API正常响应
) else (
    echo 服务可能正在启动中，请稍后手动验证
)

echo.
echo ==========================================
echo === 部署完成 ===
echo 访问: http://localhost:8888
echo.
echo 【自动报告配置】
echo - 执行时间: 每天 16:35
echo - 任务名称: StockDailyReport
echo - 批处理位置: C:\test\stock-monitor-v2\stock-monitor-v2\generate_daily_report.bat
echo - 查看任务: 运行 taskschd.msc
echo ==========================================
pause
