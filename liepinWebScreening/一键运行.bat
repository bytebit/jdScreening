@echo off
chcp 65001 >nul
title 猎聘简历筛选 - 一键运行

REM ==========================================
REM  猎聘智能简历筛选系统 - 一键运行
REM  双击运行，自动采集+分析+生成报告
REM ==========================================

echo ╔══════════════════════════════════════════════╗
echo ║     猎聘简历筛选系统 - 一键运行              ║
echo ╚══════════════════════════════════════════════╝
echo.

REM ── 检查 Python ──
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ 未安装 Python，请先双击「install.bat」
    pause
    exit /b 1
)

REM ── 检查浏览器调试端口 ──
echo 🔗 正在检查浏览器调试连接...
powershell -Command "try{$r=Invoke-WebRequest -Uri 'http://127.0.0.1:9222/json/version' -TimeoutSec 2; if($r.StatusCode -eq 200){exit 0}else{exit 1}}catch{exit 1}" >nul 2>&1
if errorlevel 1 (
    echo ⚠️  未检测到调试模式下的浏览器
    echo.
    echo   请先关闭这个窗口，然后：
    echo   1. 双击「启动浏览器.bat」
    echo   2. 在打开的 Edge 中登录猎聘并搜索候选人
    echo   3. 再重新双击「一键运行.bat」
    echo.
    pause
    exit /b 1
)
echo    ✅ 浏览器连接正常
echo.

REM ── 选择 JD 文件 ──
echo 📋 请选择岗位描述（JD）文件
echo.
echo 项目目录中已有的 JD 文件：
echo.
set "JD_FILE="
set "IDX=0"
for %%f in (*.txt *.md) do (
    if /I not "%%f"=="requirements.txt" (
        set /a IDX+=1
        set "FILE_!IDX!=%%f"
        echo    [!IDX!] %%f
    )
)

if %IDX%==0 (
    echo    （未找到 .txt 文件）
) else (
    echo.
    echo    [0] 手动输入 JD 描述
)
echo.
set /p "JD_CHOICE=请输入编号 (0-%IDX%): "

if "%JD_CHOICE%"=="0" (
    echo.
    echo 📝 请粘贴岗位描述（JD），粘贴完成后按 Enter：
    echo    （如果有多行，粘贴完按 Ctrl+Z 再按 Enter）
    echo.
    python -c "import sys; text=sys.stdin.read().strip(); open('_jd_temp.txt','w',encoding='utf-8').write(text); print('✅ JD 已保存')"
    set "JD_FILE=_jd_temp.txt"
) else if "%JD_CHOICE%"=="" (
    echo   未选择，使用默认
    set "JD_FILE="
) else (
    call set "JD_FILE=%%FILE_%JD_CHOICE%%%"
)

REM ── 采集数量 ──
echo.
set /p "MAX_COUNT=采集多少份简历？(直接回车默认 30 份): "
if "%MAX_COUNT%"=="" set "MAX_COUNT=30"

REM ── 是否深度采集 ──
echo.
set /p "DO_DEEP=是否逐条获取完整简历详情？(y/n，默认 n): "

REM ── 开始运行 ──
echo.
echo ═══════════════════════════════════════════════
echo   🚀 开始运行！
echo   采集上限: %MAX_COUNT% 份
echo   深度采集: %DO_DEEP%
echo ═══════════════════════════════════════════════
echo.
echo   ⏳ 正在运行，请耐心等待...
echo   采集过程中会自动保存进度
echo   分析完成后会自动打开 Excel 报告
echo.

if "%DO_DEEP%"=="y" (
    if not "%JD_FILE%"=="" (
        python main.py run --connect --jd-file "%JD_FILE%" --max %MAX_COUNT% --deep
    ) else (
        python main.py run --connect --max %MAX_COUNT% --deep
    )
) else (
    if not "%JD_FILE%"=="" (
        python main.py run --connect --jd-file "%JD_FILE%" --max %MAX_COUNT%
    ) else (
        python main.py run --connect --max %MAX_COUNT%
    )
)

REM ── 清理临时文件 ──
if exist "_jd_temp.txt" del "_jd_temp.txt"

REM ── 完成 ──
echo.
echo ═══════════════════════════════════════════════
echo   ✅ 运行完成！
echo   报告保存在 data\reports\ 目录下
echo ═══════════════════════════════════════════════
echo.
pause
