"""
邮件简历自动筛选系统 - 桌面 GUI
基于 PyWebView。
"""

import json, os, subprocess, threading, time
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
    _current_process = None
    _process_lock = threading.Lock()

    def get_config(self):
        import yaml
        dft = {"imap_server": "imap.qq.com", "imap_port": 993, "account": "3766416595@qq.com", "deepseek_key_set": False}
        try:
            with open("config.yaml", "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f)
            email = cfg.get("email", {}) or {}
            return {
                "imap_server": email.get("imap_server") or dft["imap_server"],
                "imap_port": email.get("imap_port") or dft["imap_port"],
                "account": email.get("account") or dft["account"],
                "deepseek_key_set": (cfg.get("deepseek", {}) or {}).get("api_key", "") != "${DEEPSEEK_API_KEY}",
            }
        except:
            return dft

    def save_config(self, imap_server, imap_port, account, password, deepseek_key):
        import yaml
        try:
            with open("config.yaml", "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f)
        except:
            _log("无法读取 config.yaml", "error")
            return "error"
        cfg.setdefault("email", {})["imap_server"] = imap_server
        cfg["email"]["imap_port"] = int(imap_port)
        cfg["email"]["account"] = account
        if password:
            cfg["email"]["password"] = password
        if deepseek_key:
            cfg.setdefault("deepseek", {})["api_key"] = deepseek_key
        with open("config.yaml", "w", encoding="utf-8") as f:
            yaml.dump(cfg, f, allow_unicode=True, default_flow_style=False)
        _log("配置已保存", "success")
        return "ok"

    def get_jd_config(self):
        """获取 JD 配置信息"""
        import yaml
        try:
            with open("config.yaml", "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f)
        except:
            return {"error": "无法读取配置"}
        
        rules = cfg.get("jobs", {}).get("subject_rules", [])
        default_jd = ""  # 不再使用默认 JD，标题不匹配关键词则跳过
        jd_dir = Path(BASE_DIR / (cfg.get("jobs", {}).get("jd_dir", "./jds/")))
        
        jd_files = []
        if jd_dir.exists():
            jd_files = sorted([f.name for f in jd_dir.glob("*.txt")])
        
        # 读取每个 JD 文件的前几行作为描述
        jd_previews = {}
        for fname in jd_files:
            try:
                content = open(jd_dir / fname, "r", encoding="utf-8").read()
                lines = [l.strip() for l in content.split("\n") if l.strip()]
                preview = "\n".join(lines[:5])[:200]
                jd_previews[fname] = preview
            except:
                jd_previews[fname] = "(无法读取)"
        
        return {
            "rules": rules,
            "default_jd": default_jd,
            "jd_files": jd_files,
            "jd_previews": jd_previews,
        }
    
    def pick_jd_file(self):
        """打开系统文件选择器选 JD 文件"""
        try:
            import webview
            result = webview.windows[0].create_file_dialog(
                webview.OPEN_DIALOG, allow_multiple=False,
                file_types=("文本文件 (*.txt)", "所有文件 (*.*)")
            )
            if result:
                path = result[0]
                import shutil
                dest = str(BASE_DIR / "jds" / os.path.basename(path))
                shutil.copy2(path, dest)
                _log(f"已导入 JD 文件: {os.path.basename(path)}", "success")
                return {"path": dest, "name": os.path.basename(path)}
            return None
        except Exception as e:
            _log(f"选择文件失败: {e}", "error")
            return None

    def get_jd_content(self, filename):
        """读取 JD 文件内容"""
        jd_dir = Path(BASE_DIR / "jds")
        path = jd_dir / filename
        if path.exists():
            return {"name": filename, "content": open(path, "r", encoding="utf-8").read()}
        return {"error": "文件不存在"}

    def save_jd_rules(self, rules_json, default_jd):
        """保存 JD 匹配规则"""
        import yaml, json
        try:
            with open("config.yaml", "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f)
        except:
            return {"error": "无法读取配置"}
        cfg.setdefault("jobs", {})["subject_rules"] = json.loads(rules_json)
        cfg["jobs"]["default_jd"] = default_jd
        with open("config.yaml", "w", encoding="utf-8") as f:
            yaml.dump(cfg, f, allow_unicode=True, default_flow_style=False)
        _log("JD 规则已保存", "success")
        return {"ok": True}
    
    def save_jd_file(self, filename, content):
        """保存 JD 文件内容"""
        jd_dir = Path(BASE_DIR / "jds")
        jd_dir.mkdir(exist_ok=True)
        with open(jd_dir / filename, "w", encoding="utf-8") as f:
            f.write(content)
        _log(f"JD 文件已保存: {filename}", "success")
        return {"ok": True}
    
    def check_dirs(self):
        """检查必需目录是否存在"""
        dirs = [
            ("logs", "日志目录"),
            ("reports", "报表目录"),
            ("temp", "临时文件目录"),
            ("jds", "JD 文件目录"),
        ]
        missing = []
        for d, name in dirs:
            p = BASE_DIR / d
            if not p.exists():
                missing.append({"path": str(p), "name": name})
        return {"missing": missing, "count": len(missing)}

    def create_dirs(self):
        """创建所有缺失的目录"""
        result = self.check_dirs()
        created = 0
        for d in result["missing"]:
            try:
                os.makedirs(d["path"], exist_ok=True)
                _log(f"已创建目录: {d['name']}", "success")
                created += 1
            except Exception as e:
                _log(f"创建目录失败 {d['name']}: {e}", "error")
        return {"created": created}

    def check_email_folders(self):
        """检查邮箱中必需的文件夹是否存在"""
        import yaml
        try:
            with open("config.yaml", "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f)
        except:
            return {"error": "无法读取配置"}
        
        email_cfg = cfg.get("email", {})
        server = email_cfg.get("imap_server", "")
        account = email_cfg.get("account", "")
        password = email_cfg.get("password", "")
        if not server or not account or not password:
            return {"error": "请先保存邮箱配置"}
        
        # 需要检查的文件夹（只检查实际使用的3个分类文件夹）
        folders = [
            email_cfg.get("folders", {}).get("pass", "JD-Pass"),
            email_cfg.get("folders", {}).get("pending", "JD-Pending"),
            email_cfg.get("folders", {}).get("fail", "JD-Fail"),
        ]
        
        import imaplib
        try:
            imap = imaplib.IMAP4_SSL(server, email_cfg.get("imap_port", 993))
            imap._encoding = 'utf-8'
            imap.login(account, password)
            result = []
            for f in folders:
                try:
                    status, _ = imap.status(f, '(MESSAGES)')
                    result.append({"name": f, "exists": status == 'OK'})
                except:
                    result.append({"name": f, "exists": False})
            imap.logout()
            return {"folders": result, "count": len(result)}
        except Exception as e:
            return {"error": f"连接邮箱失败: {e}"}
    
    def create_email_folders(self):
        """创建邮箱中缺失的文件夹"""
        import yaml
        try:
            with open("config.yaml", "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f)
        except:
            return {"error": "无法读取配置"}
        
        email_cfg = cfg.get("email", {})
        server = email_cfg.get("imap_server", "")
        account = email_cfg.get("account", "")
        password = email_cfg.get("password", "")
        
        folders = [
            email_cfg.get("folders", {}).get("pass", "JD-Pass"),
            email_cfg.get("folders", {}).get("pending", "JD-Pending"),
            email_cfg.get("folders", {}).get("fail", "JD-Fail"),
        ]
        
        import imaplib
        try:
            imap = imaplib.IMAP4_SSL(server, email_cfg.get("imap_port", 993))
            imap._encoding = 'utf-8'
            imap.login(account, password)
            created = 0
            for f in folders:
                try:
                    status, _ = imap.status(f, '(MESSAGES)')
                except:
                    status = ('NO',)
                if status[0] != 'OK':
                    try:
                        imap.create(f)
                        _log(f"已创建邮箱文件夹: {f}", "success")
                        created += 1
                    except Exception as e:
                        _log(f"创建文件夹失败 {f}: {e}", "error")
            imap.logout()
            return {"created": created}
        except Exception as e:
            return {"error": f"连接邮箱失败: {e}"}
    
    def run_screening(self):
        self._kill_previous()
        # 检查本地目录
        dirs = self.check_dirs()
        if dirs["count"] > 0:
            for d in dirs["missing"]:
                _log(f"缺少本地目录: {d['name']}", "warn")
            _log("正在自动创建缺失目录...", "info")
            self.create_dirs()
        # 检查并自动创建邮箱文件夹
        _log("检查邮箱文件夹...", "info")
        try:
            folders = self.check_email_folders()
            if "error" not in folders:
                missing = [f for f in folders.get("folders", []) if not f.get("exists")]
                for f in missing:
                    _log(f"缺少邮箱文件夹: {f['name']}", "warn")
                if missing:
                    _log("正在自动创建邮箱文件夹...", "info")
                    self.create_email_folders()
        except Exception:
            pass
        _log("开始筛选...", "info")
        args = ["python", "-B", str(BASE_DIR / "main.py")]
        self._run_subprocess(args, "筛选完成！")
        return "ok"

    def get_logs(self):
        with _log_lock:
            r = list(_logs)
            _logs.clear()
        return r

    def _kill_previous(self):
        with self._process_lock:
            if self._current_process:
                self._current_process.terminate()
                self._current_process = None

    def _run_subprocess(self, args, success_msg):
        def _run():
            try:
                env = os.environ.copy()
                env["PYTHONIOENCODING"] = "utf-8"
                env["PYTHONUNBUFFERED"] = "1"
                process = subprocess.Popen(
                    args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, encoding="utf-8", errors="replace", bufsize=1, env=env,
                )
                with self._process_lock:
                    self._current_process = process
                for line in iter(process.stdout.readline, ""):
                    if line.rstrip():
                        _log(line.rstrip(), "info")
                process.wait()
                with self._process_lock:
                    self._current_process = None
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
        title="邮件简历筛选系统",
        url=str(BASE_DIR / "ui" / "index.html"),
        width=1170, height=650, min_size=(910, 500),
        resizable=True, js_api=api, text_select=True,
    )
    webview.start(debug=False)

if __name__ == "__main__":
    main()
