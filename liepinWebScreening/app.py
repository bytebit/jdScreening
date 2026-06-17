"""
猎聘简历筛选系统 - 桌面 GUI
基于 PyWebView，以原生桌面窗口运行。
"""

import json
import os
import subprocess
import threading
import time
from collections import deque
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
os.chdir(BASE_DIR)

_logs = deque(maxlen=500)
_log_lock = threading.Lock()

def _log(msg, type="info"):
    with _log_lock:
        _logs.append({"msg": msg, "type": type})

def _run_in_thread(target, args=(), kwargs=None):
    t = threading.Thread(target=target, args=args, kwargs=kwargs or {}, daemon=True)
    t.start()
    return t


class API:

    def get_status(self):
        resume_dir = str(BASE_DIR / "data" / "resumes" / "liepin")
        exists = os.path.isdir(resume_dir)
        count = 0
        if exists:
            try:
                count = len([f for f in os.listdir(resume_dir) if f.endswith(".json")])
            except:
                pass
        return {
            "browser": self._check_debug_port(),
            "resume_count": count,
            "app_dir": str(BASE_DIR),
            "report_count": len(self._list_reports()),
            "reports": self._list_reports()[:10],
        }

    def get_jd_files(self):
        result = []
        try:
            for f in os.listdir(str(BASE_DIR)):
                if f.endswith(".txt") and f.lower() != "requirements.txt":
                    result.append(f)
        except:
            pass
        return sorted(result)

    def get_reports(self):
        return self._list_reports()

    def get_logs(self):
        with _log_lock:
            result = list(_logs)
            _logs.clear()
        return result

    def start_browser(self):
        _log("正在查找浏览器...", "info")
        edge_path = self._find_browser()
        if not edge_path:
            _log("未找到 Edge 或 Chrome", "error")
            return "error"
        if self._check_debug_port():
            _log("浏览器已在调试模式运行", "success")
            return "ok"
        _log("正在关闭旧浏览器进程...", "info")
        for exe in ["msedge.exe", "chrome.exe"]:
            try:
                subprocess.run(["taskkill", "/F", "/IM", exe], capture_output=True, timeout=5)
            except:
                pass
        time.sleep(3)
        _log("正在启动浏览器调试模式...", "info")
        subprocess.Popen(
            [edge_path, "--remote-debugging-port=9222", "--no-first-run", "--no-default-browser-check"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        for i in range(15):
            time.sleep(1)
            if self._check_debug_port():
                _log("浏览器启动成功！", "success")
                return "ok"
        _log("浏览器已启动（请检查调试提示）", "warn")
        return "timeout"

    def collect_resumes(self, max_count=30, deep=True):
        _log("开始采集（上限 " + str(max_count) + " 份）...", "info")
        args = ["python", str(BASE_DIR / "main.py"), "collect", "--connect", "--max", str(max_count)]
        if deep:
            args.append("--deep")
        self._run_subprocess(args, "采集完成！")

    def analyze_resumes(self, jd_file):
        resume_dir = str(BASE_DIR / "data" / "resumes" / "liepin")
        _log("开始筛选...", "info")
        args = ["python", str(BASE_DIR / "main.py"), "analyze", "--jd-file", jd_file, "--resume-dir", resume_dir]
        self._run_subprocess(args, "筛选完成！")
        return "ok"

    def open_report(self, filename):
        path = BASE_DIR / "data" / "reports" / filename
        if path.exists():
            os.startfile(str(path))
            _log("已打开: " + filename, "success")
        else:
            _log("文件不存在: " + str(path), "error")

    def pick_jd_file(self):
        try:
            import webview
            file_types = ("文本文件 (*.txt;*.md)", "所有文件 (*.*)")
            result = webview.windows[0].create_file_dialog(
                webview.OPEN_DIALOG, allow_multiple=False, file_types=file_types
            )
            if result:
                return {"path": result[0], "name": os.path.basename(result[0])}
            return None
        except Exception as e:
            _log("选择文件失败: " + str(e), "error")
            return None

    def _check_debug_port(self):
        import urllib.request
        try:
            resp = urllib.request.urlopen("http://127.0.0.1:9222/json/version", timeout=2)
            return resp.status == 200
        except:
            return False

    def _find_browser(self):
        candidates = [
            os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
            os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
            os.path.expandvars(r"%LocalAppData%\Microsoft\Edge\Application\msedge.exe"),
            os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
        ]
        for p in candidates:
            if os.path.isfile(p):
                return p
        for exe in ["msedge.exe", "chrome.exe"]:
            try:
                r = subprocess.run(["where", exe], capture_output=True, text=True, timeout=3)
                if r.returncode == 0 and r.stdout.strip():
                    return r.stdout.strip().split("\n")[0]
            except:
                pass
        return ""

    def _list_reports(self):
        report_dir = BASE_DIR / "data" / "reports"
        if not report_dir.exists():
            return []
        return sorted([f.name for f in report_dir.glob("*.xlsx")], reverse=True)

    def _run_subprocess(self, args, success_msg):
        def _run():
            try:
                env = os.environ.copy()
                env["PYTHONIOENCODING"] = "utf-8"
                process = subprocess.Popen(
                    args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, encoding="utf-8", errors="replace", bufsize=1, env=env,
                )
                for line in iter(process.stdout.readline, ""):
                    if line.rstrip():
                        _log(line.rstrip(), "info")
                process.wait()
                if process.returncode == 0:
                    _log(success_msg, "success")
                else:
                    _log("进程退出码: " + str(process.returncode), "error")
            except Exception as e:
                _log("运行出错: " + str(e), "error")
        _run_in_thread(_run)


def main():
    try:
        import webview
    except ImportError:
        print("需要安装 pywebview: pip install pywebview --break-system-packages")
        input("按回车退出...")
        return

    api = API()
    window = webview.create_window(
        title="猎聘简历筛选系统",
        url=str(BASE_DIR / "ui" / "index.html"),
        width=1000, height=700, min_size=(800, 600),
        resizable=True, js_api=api, text_select=True,
    )
    webview.start(debug=False)


if __name__ == "__main__":
    main()
