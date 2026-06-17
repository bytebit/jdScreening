@echo off
chcp 65001 >nul
title 猎聘简历筛选 - 一键启动 Edge 调试模式

REM ==========================================
REM  猎聘智能简历筛选系统
REM  一键启动 Edge 调试模式（双击运行）
REM  不需要安装 Python，不需要敲命令
REM ==========================================

echo ╔══════════════════════════════════════════════╗
echo ║     猎聘简历筛选 - 启动 Edge 调试模式        ║
echo ╚══════════════════════════════════════════════╝
echo.

REM ── 第1步：查找 Edge / Chrome 安装路径 ──
echo [1/4] 正在查找浏览器安装路径...

set "EDGE_PATH="
set "CHROME_PATH="

REM 检查 Edge 标准路径
if exist "%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe" set "EDGE_PATH=%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"
if exist "%ProgramFiles%\Microsoft\Edge\Application\msedge.exe" set "EDGE_PATH=%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"
if exist "%LocalAppData%\Microsoft\Edge\Application\msedge.exe" set "EDGE_PATH=%LocalAppData%\Microsoft\Edge\Application\msedge.exe"

REM 检查 Chrome 标准路径
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" set "CHROME_PATH=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" set "CHROME_PATH=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
if exist "%LocalAppData%\Google\Chrome\Application\chrome.exe" set "CHROME_PATH=%LocalAppData%\Google\Chrome\Application\chrome.exe"

REM 如果 PATH 里能找到（便携版/绿色版）
if "%EDGE_PATH%"=="" (
    where msedge.exe >nul 2>&1
    if not errorlevel 1 set "EDGE_PATH=msedge.exe"
)
if "%CHROME_PATH%"=="" (
    where chrome.exe >nul 2>&1
    if not errorlevel 1 set "CHROME_PATH=chrome.exe"
)

REM 确定使用的浏览器（优先 Edge）
set "BROWSER_PATH=%EDGE_PATH%"
set "BROWSER_NAME=Edge"
if "%BROWSER_PATH%"=="" (
    set "BROWSER_PATH=%CHROME_PATH%"
    set "BROWSER_NAME=Chrome"
)

if "%BROWSER_PATH%"=="" (
    echo ❌ 未找到 Edge 或 Chrome 浏览器
    echo    请先安装 Microsoft Edge 后重试
    echo.
    echo     下载地址: https://www.microsoft.com/edge
    echo.
    pause
    exit /b 1
)
echo    ✅ 找到 %BROWSER_NAME%: %BROWSER_PATH%
echo.

REM ── 第2步：检查是否已有调试模式在运行 ──
echo [2/4] 检查调试端口 9222 是否已被占用...

REM 用 PowerShell 快速检查端口
powershell -Command "try{$r=Invoke-WebRequest -Uri 'http://127.0.0.1:9222/json/version' -TimeoutSec 2; if($r.StatusCode -eq 200){exit 0}else{exit 1}}catch{exit 1}" >nul 2>&1
if not errorlevel 1 (
    echo    ✅ 浏览器已在调试模式运行，无需重复启动
    echo.
    echo ═══════════════════════════════════════════════
    echo   下一步操作：
    echo     1. 在已打开的 %BROWSER_NAME% 中登录猎聘
    echo     2. 搜索候选人，看到结果页
    echo     3. 双击「一键运行.bat」开始筛选
    echo ═══════════════════════════════════════════════
    echo.
    pause
    exit /b 0
)
echo    ℹ️  端口 9222 空闲，需要启动浏览器
echo.

REM ── 第3步：关闭已有浏览器进程 ──
echo [3/4] 正在关闭已有浏览器进程（避免端口冲突）...
taskkill /F /IM msedge.exe >nul 2>&1
taskkill /F /IM chrome.exe >nul 2>&1
ping 127.0.0.1 -n 4 >nul
echo    ✅ 已关闭旧进程
echo.

REM ── 第4步：启动调试模式 ──
echo [4/4] 正在启动 %BROWSER_NAME%（调试模式，端口 9222）...
start "" "%BROWSER_PATH%" --remote-debugging-port=9222 --no-first-run --no-default-browser-check

REM 等待浏览器启动（最多等 20 秒）
set "WAIT_COUNT=0"
:WAIT_LOOP
powershell -Command "try{$r=Invoke-WebRequest -Uri 'http://127.0.0.1:9222/json/version' -TimeoutSec 1; if($r.StatusCode -eq 200){exit 0}else{exit 1}}catch{exit 1}" >nul 2>&1
if not errorlevel 1 goto LAUNCH_OK
ping 127.0.0.1 -n 2 >nul
set /a WAIT_COUNT+=1
if %WAIT_COUNT% lss 20 goto WAIT_LOOP

echo.
echo ⚠️  启动超时，但浏览器可能已经打开
echo    请检查 %BROWSER_NAME% 窗口右上角是否有"正由自动化测试软件控制"
echo.
goto NEXT_STEPS

:LAUNCH_OK
echo    ✅ %BROWSER_NAME% 已启动（调试模式，端口 9222）
echo    🟢 窗口右上角应显示「正由自动化测试软件控制」

:NEXT_STEPS
echo.
echo ═══════════════════════════════════════════════
echo   启动成功！接下来请按顺序操作：
echo.
echo   第 1 步 👉 在打开的 %BROWSER_NAME% 中访问：
echo              https://lpt.liepin.com
echo              扫码登录猎聘 HR 后台
echo.
echo   第 2 步 👉 设置筛选条件，点「搜索」
echo              看到候选人列表
echo.
echo   第 3 步 👉 双击项目目录中的「一键运行.bat」
echo              或打开 PowerShell 运行：
echo              python main.py run --jd-file jd.txt
echo.
echo   💡 这个窗口可以关闭，不影响浏览器
echo ═══════════════════════════════════════════════
echo.
pause
