@echo off
chcp 65001 >nul
title 猎聘简历筛选 - 一键安装

REM ==========================================
REM  猎聘智能简历筛选系统 - 一键安装
REM  双击运行，自动安装所有依赖
REM ==========================================

echo ╔══════════════════════════════════════════════╗
echo ║     猎聘简历筛选系统 - 一键安装              ║
echo ╚══════════════════════════════════════════════╝
echo.

REM ── 第1步：检查 Python ──
echo [1/5] 检查 Python 环境...
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ 未安装 Python！
    echo    请先安装 Python 3.10 或更高版本
    echo.
    echo     下载地址: https://www.python.org/downloads/
    echo.
    echo   安装时记得勾选「Add Python to PATH」
    echo.
    pause
    exit /b 1
)
for /f "tokens=2" %%i in ('python --version 2^>^&1') do set "PY_VER=%%i"
echo    ✅ Python %PY_VER%
echo.

REM ── 第2步：安装 Python 依赖 ──
echo [2/5] 安装 Python 依赖包（可能需要几分钟）...
echo    ⏳ 请耐心等待，不要关闭窗口...
pip install -r requirements.txt --break-system-packages >nul 2>&1
if errorlevel 1 (
    pip install -r requirements.txt >nul 2>&1
)
if errorlevel 1 (
    echo ⚠️  pip 安装失败，尝试另一种方式...
    python -m pip install -r requirements.txt >nul 2>&1
)
echo    ✅ 依赖包安装完成
echo.

REM ── 第3步：安装 Playwright 浏览器 ──
echo [3/5] 安装 Playwright Chromium 浏览器引擎...
python -m playwright install chromium >nul 2>&1
if errorlevel 1 (
    playwright install chromium >nul 2>&1
)
echo    ✅ Playwright 安装完成
echo.

REM ── 第4步：创建数据目录 ──
echo [4/5] 创建数据目录结构...
if not exist "data\cookies" mkdir "data\cookies"
if not exist "data\resumes" mkdir "data\resumes"
if not exist "data\results" mkdir "data\results"
if not exist "data\reports" mkdir "data\reports"
if not exist "data\logs"   mkdir "data\logs"
echo    ✅ 目录已创建
echo.

REM ── 第5步：配置 API Key ──
echo [5/5] 配置 DeepSeek API Key...
if not exist ".env" (
    copy .env.example .env >nul
    echo.
    echo ⚠️  请先配置 API Key！
    echo    1. 打开 .env 文件（用记事本）
    echo    2. 将 sk-your-key-here 替换为你的 Key
    echo    3. 保存文件
    echo.
    echo    💡 如果没有 API Key，请访问：
    echo       https://platform.deepseek.com/api_keys
    echo.
) else (
    echo    ✅ .env 已存在，跳过
)
echo.

echo ═══════════════════════════════════════════════
echo   ✅ 安装完成！
echo ═══════════════════════════════════════════════
echo.
echo   首次使用步骤：
echo.
echo   第 1 步 👉 打开 .env 文件，填入 DeepSeek API Key
echo              （如果没有 Key，先访问 platform.deepseek.com 获取）
echo.
echo   第 2 步 👉 双击「启动浏览器.bat」
echo              自动打开 Edge（调试模式）
echo.
echo   第 3 步 👉 在 Edge 中登录猎聘，搜索候选人
echo.
echo   第 4 步 👉 双击「一键运行.bat」
echo              按照提示选择 JD 文件，开始筛选
echo.
echo   💡 以后每次使用只需要做第 2~4 步
echo.
pause
