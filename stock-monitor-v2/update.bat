@echo off
chcp 65001 >nul
:: ============================================================
:: 股票监控系统 - 自动更新脚本
:: 功能：一键备份数据、下载最新代码、恢复数据、重启服务
:: 作者：Kimi Claw
:: ============================================================

setlocal EnableDelayedExpansion

:: 配置项
echo [INFO] ========================================
echo [INFO] 股票监控系统 - 自动更新
echo [INFO] ========================================
echo.

:: 检测当前目录
set "REPO_DIR=%CD%"
set "DATA_DIR=%USERPROFILE%\stock-monitor-data"
set "TEMP_DIR=%TEMP%\stock-monitor-update"
set "GITHUB_URL=https://github.com/test-gongsheng/gs/archive/refs/heads/master.zip"
set "MIRROR_URL=https://ghproxy.com/https://github.com/test-gongsheng/gs/archive/refs/heads/master.zip"

:: 检查是否在正确的目录
if not exist "%REPO_DIR%\app.py" (
    echo [ERROR] 当前目录不是 stock-monitor-v2！
    echo [ERROR] 请 cd 到 stock-monitor-v2 目录后再运行此脚本
    pause
    exit /b 1
)

echo [INFO] 当前目录: %REPO_DIR%
echo [INFO] 备份目录: %DATA_DIR%
echo.

:: ============================================================
:: 第 1 步：备份现有数据
:: ============================================================
echo [STEP 1/6] 备份现有数据...

if not exist "%DATA_DIR%" mkdir "%DATA_DIR%"

set "BACKUP_FILES=0"

if exist "%REPO_DIR%\data\stocks.json" (
    copy /Y "%REPO_DIR%\data\stocks.json" "%DATA_DIR%\stocks.json.bak" >nul
    echo [OK] stocks.json 已备份 (%DATA_DIR%)
    set /a "BACKUP_FILES+=1"
) else (
    echo [WARN] 未找到 stocks.json
)

if exist "%REPO_DIR%\data\stocks.db" (
    copy /Y "%REPO_DIR%\data\stocks.db" "%DATA_DIR%\stocks.db.bak" >nul
    echo [OK] stocks.db 已备份
    set /a "BACKUP_FILES+=1"
)

if exist "%REPO_DIR%\reports\portfolio_analysis_latest.json" (
    copy /Y "%REPO_DIR%\reports\portfolio_analysis_latest.json" "%DATA_DIR%\portfolio_analysis_latest.json.bak" >nul
    echo [OK] 分析报告已备份
    set /a "BACKUP_FILES+=1"
)

echo [INFO] 已备份 %BACKUP_FILES% 个数据文件
echo.

:: ============================================================
:: 第 2 步：关闭现有服务
:: ============================================================
echo [STEP 2/6] 关闭现有服务...

:: 查找并关闭 Python 进程（flask 服务）
taskkill /F /IM python.exe /FI "WINDOWTITLE eq *flask*" 2>nul
taskkill /F /IM python.exe 2>nul

:: 检查端口 8888 是否被占用
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8888') do (
    echo [INFO] 关闭占用 8888 端口的进程 PID: %%a
    taskkill /F /PID %%a 2>nul
)

echo [OK] 服务已关闭
echo.

:: ============================================================
:: 第 3 步：下载最新代码
:: ============================================================
echo [STEP 3/6] 下载最新代码...

:: 清理临时目录
if exist "%TEMP_DIR%" rmdir /S /Q "%TEMP_DIR%"
mkdir "%TEMP_DIR%"

:: 尝试下载（先走镜像，失败再试直连）
echo [INFO] 正在下载最新代码...
set "DOWNLOAD_SUCCESS=0"

:: 尝试镜像下载
echo [INFO] 尝试镜像下载 (ghproxy.com)...
powershell -Command "try { Invoke-WebRequest -Uri '%MIRROR_URL%' -OutFile '%TEMP_DIR%\master.zip' -TimeoutSec 60; exit 0 } catch { exit 1 }" 2>nul

if exist "%TEMP_DIR%\master.zip" (
    for %%F in ("%TEMP_DIR%\master.zip") do (
        if %%~zF GTR 1000 (
            echo [OK] 镜像下载成功
            set "DOWNLOAD_SUCCESS=1"
        )
    )
)

:: 如果镜像失败，尝试直连
if "%DOWNLOAD_SUCCESS%"=="0" (
    echo [INFO] 镜像下载失败，尝试直连 GitHub...
    powershell -Command "try { Invoke-WebRequest -Uri '%GITHUB_URL%' -OutFile '%TEMP_DIR%\master.zip' -TimeoutSec 120; exit 0 } catch { exit 1 }" 2>nul
    
    if exist "%TEMP_DIR%\master.zip" (
        for %%F in ("%TEMP_DIR%\master.zip") do (
            if %%~zF GTR 1000 (
                echo [OK] 直连下载成功
                set "DOWNLOAD_SUCCESS=1"
            )
        )
    )
)

if "%DOWNLOAD_SUCCESS%"=="0" (
    echo [ERROR] 下载失败！网络问题或 GitHub 无法访问
    echo [ERROR] 建议：
    echo [ERROR]   1. 检查网络连接
    echo [ERROR]   2. 手动从浏览器下载 https://github.com/test-gongsheng/gs
    echo [ERROR]   3. 或者使用 VPN 后重试
    pause
    exit /b 1
)

echo.

:: ============================================================
:: 第 4 步：解压并替换代码
:: ============================================================
echo [STEP 4/6] 解压并替换代码...

:: 解压
powershell -Command "Expand-Archive -Path '%TEMP_DIR%\master.zip' -DestinationPath '%TEMP_DIR%\extracted' -Force" 2>nul

if not exist "%TEMP_DIR%\extracted\gs-master" (
    echo [ERROR] 解压失败！
    pause
    exit /b 1
)

:: 保存 data 目录（额外保险）
if exist "%REPO_DIR%\data" (
    xcopy /E /I /Y "%REPO_DIR%\data" "%TEMP_DIR%\data_backup_temp" >nul 2>nul
)

:: 删除旧代码文件（保留 data 目录）
echo [INFO] 清理旧代码...
for /d %%D in ("%REPO_DIR%\*") do (
    if /I not "%%~nxD"=="data" (
        if /I not "%%~nxD"=="venv" (
            if /I not "%%~nxD"=="__pycache__" (
                rmdir /S /Q "%%D" 2>nul
            )
        )
    )
)

for %%F in ("%REPO_DIR%\*") do (
    if /I not "%%~nxF"=="data_backup.bat" (
        if /I not "%%~nxF"=="update.bat" (
            del /F /Q "%%F" 2>nul
        )
    )
)

:: 复制新代码
echo [INFO] 复制新代码...
xcopy /E /I /Y "%TEMP_DIR%\extracted\gs-master\stock-monitor-v2\*" "%REPO_DIR%\" >nul 2>nul

:: 恢复 data 目录（如果刚才被误删）
if exist "%TEMP_DIR%\data_backup_temp" (
    xcopy /E /I /Y "%TEMP_DIR%\data_backup_temp\*" "%REPO_DIR%\data\" >nul 2>nul
    rmdir /S /Q "%TEMP_DIR%\data_backup_temp" 2>nul
)

echo [OK] 代码更新完成
echo.

:: ============================================================
:: 第 5 步：恢复数据
:: ============================================================
echo [STEP 5/6] 恢复用户数据...

set "RESTORE_FILES=0"

if exist "%DATA_DIR%\stocks.json.bak" (
    copy /Y "%DATA_DIR%\stocks.json.bak" "%REPO_DIR%\data\stocks.json" >nul
    echo [OK] stocks.json 已恢复
    set /a "RESTORE_FILES+=1"
) else (
    echo [WARN] 未找到 stocks.json 备份，需要重新导入持仓
)

if exist "%DATA_DIR%\stocks.db.bak" (
    copy /Y "%DATA_DIR%\stocks.db.bak" "%REPO_DIR%\data\stocks.db" >nul
    echo [OK] stocks.db 已恢复
    set /a "RESTORE_FILES+=1"
)

if exist "%DATA_DIR%\portfolio_analysis_latest.json.bak" (
    copy /Y "%DATA_DIR%\portfolio_analysis_latest.json.bak" "%REPO_DIR%\reports\portfolio_analysis_latest.json" >nul
    echo [OK] 分析报告已恢复
    set /a "RESTORE_FILES+=1"
)

echo [INFO] 已恢复 %RESTORE_FILES% 个数据文件
echo.

:: ============================================================
:: 第 6 步：启动服务
:: ============================================================
echo [STEP 6/6] 启动服务...

:: 检查 venv 是否存在
if not exist "%REPO_DIR%\venv\Scripts\python.exe" (
    echo [WARN] 未找到虚拟环境，尝试使用系统 Python...
    set "PYTHON_CMD=python"
) else (
    set "PYTHON_CMD=%REPO_DIR%\venv\Scripts\python.exe"
)

:: 启动服务（后台运行）
echo [INFO] 正在启动 Flask 服务...
start /B "" "%PYTHON_CMD%" "%REPO_DIR%\app.py" > "%REPO_DIR%\app.log" 2>&1

:: 等待服务启动
timeout /t 3 /nobreak >nul

:: 检查服务是否启动成功
curl -s http://localhost:8888/api/stocks >nul 2>nul
if %ERRORLEVEL%==0 (
    echo [OK] 服务启动成功！http://localhost:8888
) else (
    echo [WARN] 服务可能还在启动中，请稍等 5 秒后刷新浏览器
)

echo.

:: ============================================================
:: 清理
:: ============================================================
rmdir /S /Q "%TEMP_DIR%" 2>nul

:: ============================================================
:: 完成
:: ============================================================
echo ========================================
echo [DONE] 更新完成！
echo ========================================
echo.
echo 数据状态：
if exist "%REPO_DIR%\data\stocks.json" (
    for %%F in ("%REPO_DIR%\data\stocks.json") do (
        if %%~zF GTR 1000 (
            echo   [OK] stocks.json 存在 (%%~zF bytes)
        ) else (
            echo   [WARN] stocks.json 为空，需要导入持仓！
        )
    )
)
echo.
echo 浏览器访问：http://localhost:8888
echo.
pause
