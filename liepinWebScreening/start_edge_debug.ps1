# 以调试模式启动 Edge
# 右键 -> 使用 PowerShell 运行

Write-Host "正在关闭已有 Edge/Chrome 进程..." -ForegroundColor Yellow
taskkill /F /IM msedge.exe 2>$null
taskkill /F /IM chrome.exe 2>$null
Start-Sleep -Seconds 3

Write-Host "正在启动 Edge（调试模式）..." -ForegroundColor Green
Start-Process msedge -ArgumentList "--remote-debugging-port=9222"

Write-Host ""
Write-Host "Edge 已启动。确认右上角有「正由自动化测试软件控制」的提示" -ForegroundColor Green
Write-Host "然后登录猎聘 -> 搜索候选人 -> 运行: python main.py survey" -ForegroundColor Cyan
pause
