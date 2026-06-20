"""
端口检测工具 — 检查 Chrome 调试端口状态
=========================================

用法：
    python -m collector.check_port
"""

import os
import socket
import subprocess
import sys
import time
import urllib.request
import urllib.error


def check_port(port: int = 9222) -> dict:
    """检查端口状态，返回详细诊断信息"""
    result = {
        "port": port,
        "listening": False,
        "chrome_process": False,
        "debug_endpoint": False,
        "chrome_paths_found": [],
    }

    # 1. 检查端口是否在监听
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(2)
    try:
        sock.connect(("127.0.0.1", port))
        result["listening"] = True
    except (socket.timeout, ConnectionRefusedError):
        result["listening"] = False
    finally:
        sock.close()

    # 2. 检查浏览器进程是否存在
    try:
        if sys.platform == "win32":
            for exe in ["chrome.exe", "msedge.exe"]:
                output = subprocess.run(
                    ["tasklist", "/FI", f"IMAGENAME eq {exe}", "/FO", "CSV"],
                    capture_output=True, text=True, timeout=5,
                )
                if exe in output.stdout.lower():
                    result["browser_process"] = exe
                    break
            else:
                result["browser_process"] = None
        else:
            for name in ["chrome", "msedge", "chromium"]:
                output = subprocess.run(
                    ["pgrep", "-l", name],
                    capture_output=True, text=True, timeout=5,
                )
                if output.stdout.strip():
                    result["browser_process"] = name
                    break
            else:
                result["browser_process"] = None
    except Exception:
        result["browser_process"] = None

    # 3. 尝试访问调试端点
    if result["listening"]:
        try:
            resp = urllib.request.urlopen(
                f"http://127.0.0.1:{port}/json/version", timeout=3
            )
            result["debug_endpoint"] = resp.status == 200
        except Exception:
            result["debug_endpoint"] = False

    return result


def find_any_browser_windows() -> tuple[str, str]:
    """Windows 下查找 Edge 或 Chrome 路径"""
    import os
    pairs = [
        ("Edge", os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe")),
        ("Edge", os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe")),
        ("Edge", os.path.expandvars(r"%LocalAppData%\Microsoft\Edge\Application\msedge.exe")),
        ("Chrome", os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe")),
        ("Chrome", os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe")),
        ("Chrome", os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe")),
    ]
    for name, path in pairs:
        if os.path.isfile(path):
            return name, path

    for exe in ["msedge", "chrome"]:
        try:
            r = subprocess.run(["where", exe], capture_output=True, text=True, shell=True)
            if r.returncode == 0 and r.stdout.strip():
                path = r.stdout.strip().split("\n")[0]
                if os.path.isfile(path):
                    name = "Edge" if "edge" in exe.lower() else "Chrome"
                    return name, path
        except Exception:
            pass
    return "", ""


def print_manual_instructions():
    """输出手动启动浏览器的明确指令"""
    browser_name, browser_path = find_any_browser_windows()

    print()
    print("=" * 60)
    print(f"  手动启动浏览器（调试模式）")
    print("=" * 60)
    print()

    if browser_path:
        exe_name = os.path.basename(browser_path)
        print(f"  找到 {browser_name}: {browser_path}")
        print()
        print("  推荐的两种方式：")
        print()
        print("  方式 A：使用一键启动脚本（推荐）")
        print("  ───────────────────────────────")
        print(f"  python -m collector.chrome_launcher")
        print()
        print("  方式 B：手动操作")
        print("  ───────────────────────────────")
        print("  1. 打开任务管理器 → 结束所有 msedge.exe 和 chrome.exe")
        print(f"  2. 按 Win+R → 粘贴以下内容 → 回车：")
        print(f'     {exe_name} --remote-debugging-port=9222')
        print()
        print(f"  3. 浏览器右上角出现「{browser_name} 正由自动化测试软件控制」即为成功")
        print()

        # 生成 bat 脚本
        bat_path = r"D:\华为云盘\jdFilter\liepin-screener\start_browser_debug.bat"
        try:
            with open(bat_path, "w", encoding="utf-8") as f:
                f.write("@echo off\n")
                f.write("echo 正在关闭已有浏览器进程...\n")
                f.write("taskkill /F /IM msedge.exe >nul 2>&1\n")
                f.write("taskkill /F /IM chrome.exe >nul 2>&1\n")
                f.write("timeout /t 2 /nobreak >nul\n")
                f.write(f'start "" "{browser_path}" --remote-debugging-port=9222\n')
                f.write(f"echo.\n")
                f.write(f"echo {browser_name} 已启动（调试模式，端口 9222）\n")
                f.write(f"echo 浏览器右上角应有调试提示\n")
                f.write(f"echo 请登录猎聘后搜索候选人，然后运行：\n")
                f.write(f"echo   python main.py survey\n")
                f.write("pause\n")
            print(f"  ✅ 已生成一键启动脚本：")
            print(f"     双击 {bat_path} 即可启动")
            print()
        except Exception:
            pass
    else:
        print("  ⚠️  未找到 Edge 或 Chrome")
        print("  请先安装浏览器")
        print()


if __name__ == "__main__":
    print()
    print("=" * 60)
    print("  浏览器调试端口诊断工具")
    print("=" * 60)
    print()

    info = check_port()
    browser_name, _ = find_any_browser_windows()
    bname = browser_name or "浏览器"

    if info["debug_endpoint"]:
        print(f"✅ 状态正常：端口 9222 可正常连接")
        print(f"   可以直接运行: python main.py survey")
    elif info["listening"] and not info["debug_endpoint"]:
        print("⚠️  端口 9222 有服务在监听，但不是浏览器调试接口")
        print("   可能是其他程序占用了该端口，换个端口试试")
    elif not info["listening"] and info.get("browser_process"):
        bp = info["browser_process"]
        print(f"❌ {bname}({bp}) 正在运行，但没有以调试模式启动")
        print(f"   关闭所有浏览器窗口后，用以下命令启动：")
        print(f"   python -m collector.chrome_launcher")
    elif not info["listening"] and not info.get("browser_process"):
        print(f"❌ {bname} 没有运行，且端口 9222 未监听")
        print(f"   运行一键启动脚本：")
        print(f"   python -m collector.chrome_launcher")
