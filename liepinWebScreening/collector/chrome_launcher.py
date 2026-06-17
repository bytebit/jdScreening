"""
浏览器一键启动器 — 以调试模式启动 Edge/Chrome
================================================

用法：
    python -m collector.chrome_launcher

说明：
    优先使用 Edge（Windows 自带，没有后台进程残留问题）。
    如果找不到 Edge 则回退到 Chrome。

效果：
    自动关掉已有浏览器进程 → 以 --remote-debugging-port=9222 重新启动
"""

import argparse
import os
import platform
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional


# ── 进程名映射 ──
BROWSER_NAMES = {
    "edge": {
        "exe": "msedge.exe",
        "process": "msedge.exe",
        "display": "Edge",
    },
    "chrome": {
        "exe": "chrome.exe",
        "process": "chrome.exe",
        "display": "Chrome",
    },
}


def find_browser(prefer: str = "edge") -> tuple[str, str]:
    """
    查找浏览器可执行文件路径

    Returns:
        (完整路径, 浏览器名称)
    """
    system = platform.system()

    if system == "Windows":
        edge_paths = [
            os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
            os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
            os.path.expandvars(r"%LocalAppData%\Microsoft\Edge\Application\msedge.exe"),
        ]
        chrome_paths = [
            os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
        ]

        if prefer == "edge":
            check_list = [("edge", edge_paths), ("chrome", chrome_paths)]
        else:
            check_list = [("chrome", chrome_paths), ("edge", edge_paths)]

        for browser_name, paths in check_list:
            for path in paths:
                if os.path.isfile(path):
                    return path, BROWSER_NAMES[browser_name]["display"]

        # PATH 查找
        for browser_name, _ in check_list:
            info = BROWSER_NAMES[browser_name]
            try:
                result = subprocess.run(
                    ["where", info["exe"]],
                    capture_output=True, text=True, shell=True,
                )
                if result.returncode == 0 and result.stdout.strip():
                    path = result.stdout.strip().split("\n")[0]
                    if os.path.isfile(path):
                        return path, info["display"]
            except Exception:
                continue

    elif system == "Darwin":
        paths = [
            ("edge", "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
            ("chrome", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        ]
        for name, path in paths:
            if os.path.isfile(path):
                return path, BROWSER_NAMES[name]["display"]

    elif system == "Linux":
        paths = [
            ("chrome", "/usr/bin/google-chrome"),
            ("chrome", "/usr/bin/google-chrome-stable"),
            ("chrome", "/usr/bin/chromium"),
            ("chrome", "/usr/bin/chromium-browser"),
        ]
        for name, path in paths:
            if os.path.isfile(path):
                return path, BROWSER_NAMES[name]["display"]

    return "", ""


def is_debug_port_open(port: int = 9222) -> bool:
    """检测调试端口是否可用"""
    import urllib.request
    try:
        resp = urllib.request.urlopen(
            f"http://127.0.0.1:{port}/json/version", timeout=2
        )
        return resp.status == 200
    except Exception:
        return False


def launch_debug_browser(
    port: int = 9222,
    open_liepin: bool = False,
    prefer: str = "edge",
) -> bool:
    """
    以调试模式启动浏览器

    Args:
        port: 调试端口
        open_liepin: 启动后是否打开猎聘
        prefer: 优先使用 edge 还是 chrome

    Returns:
        是否成功启动
    """
    browser_path, browser_name = find_browser(prefer)

    if not browser_path:
        print(f"❌ 未找到 Edge 或 Chrome 浏览器")
        print(f"   请手动安装后重试")
        return False

    print(f"🔍 找到浏览器: {browser_name} → {browser_path}")

    # 检查端口是否已被占用
    if is_debug_port_open(port):
        print(f"✅ 端口 {port} 已有浏览器在监听，可以直接使用")
        return True

    # 构建参数
    args = [
        browser_path,
        f"--remote-debugging-port={port}",
        "--no-first-run",
        "--no-default-browser-check",
    ]

    if open_liepin:
        args.append("https://lpt.liepin.com")

    # 关掉已有的浏览器进程（确保新实例能绑定端口）
    if platform.system() == "Windows":
        browser_info = BROWSER_NAMES.get(prefer, BROWSER_NAMES["edge"])
        if prefer == "edge":
            # 杀 Edge 和 Chrome 都杀掉
            kill_targets = ["msedge.exe", "chrome.exe"]
        else:
            kill_targets = ["chrome.exe", "msedge.exe"]

        print(f"\n⚠️  正在关闭已有浏览器进程...")
        for target in kill_targets:
            try:
                subprocess.run(
                    ["taskkill", "/F", "/IM", target],
                    capture_output=True, timeout=5,
                )
            except Exception:
                pass

        # 等进程完全退出
        time.sleep(3)

        # 用 Win+R 方式启动（最可靠）
        cmd = f'start "" "{browser_path}" --remote-debugging-port={port}'
        if open_liepin:
            cmd += " https://lpt.liepin.com"

        print(f"\n🚀 正在启动 {browser_name} 调试模式...")
        subprocess.Popen(
            ["cmd", "/c", cmd],
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # 等待启动
        print("   等待浏览器启动", end="", flush=True)
        for i in range(20):
            time.sleep(1)
            if is_debug_port_open(port):
                print(f"\n✅ {browser_name} 已启动，调试端口 {port} 正常")
                print("\n   🟢 窗口右上角显示「Edge 正由自动化测试软件控制」即为成功")
                print()
                print("   下一步：")
                print("   1. 在这个 Edge 中打开 https://lpt.liepin.com → 登录猎聘")
                print("   2. 搜索候选人 → 看到结果页")
                print("   3. 新开命令行窗口运行:")
                print("      python main.py survey")
                return True
            print(".", end="", flush=True)

        print("\n⚠️  等超时了，但浏览器可能已经打开")
        print(f"   请查看 {browser_name} 右上角是否有调试提示")
        return True
    else:
        # macOS / Linux
        subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True


# ──────────────────────────────────────────────
# CLI 入口
# ──────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="一键启动浏览器调试模式")
    parser.add_argument("--port", type=int, default=9222, help="调试端口")
    parser.add_argument("--open-liepin", action="store_true", help="启动后打开猎聘")
    parser.add_argument("--browser", choices=["edge", "chrome"], default="edge",
                        help="使用哪个浏览器（默认 Edge）")

    args = parser.parse_args()

    print("=" * 60)
    print("  浏览器调试模式启动器")
    print("=" * 60)
    print()

    # 先检测端口
    if is_debug_port_open(args.port):
        print(f"✅ 端口 {args.port} 已有浏览器在监听，无需重新启动")
        print()
        print("   直接运行：")
        print("   python main.py survey")
        sys.exit(0)

    success = launch_debug_browser(
        port=args.port,
        open_liepin=args.open_liepin,
        prefer=args.browser,
    )

    if not success:
        sys.exit(1)

    # 保持窗口打开
    print()
    print("💡 这个窗口可以最小化，不要关闭")
    try:
        while True:
            time.sleep(10)
    except KeyboardInterrupt:
        print("\n再见")
