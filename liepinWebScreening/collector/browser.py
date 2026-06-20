"""
Playwright 浏览器模块 — 仅用于登录获取 Token
================================================
原则：Playwright 的职责缩到最小——只处理登录环节。
登录成功后导出 Cookie/Token，后续数据采集全部走 HTTP API。
"""

import json
import os
import sys
from pathlib import Path
from typing import Optional

# 确保能找到项目根目录
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config as cfg


class LiepinLogin:
    """
    猎聘 HR 后台登录管理器

    使用方式:
        login = LiepinLogin()
        token, cookies = login.interactive_login()   # 首次登录
        login.load_session()                          # 后续复用
    """

    def __init__(self):
        self.cookie_file = Path(cfg.COOKIE_FILE)
        self.cookie_file.parent.mkdir(parents=True, exist_ok=True)

    # ────────────────────────────────────────────────
    # 交互式登录（首次使用）
    # ────────────────────────────────────────────────
    def interactive_login(self) -> tuple[Optional[str], list[dict]]:
        """
        打开浏览器让用户扫码登录，登录后导出 Token 和 Cookie

        Returns:
            (token, cookies_list)
            token 可能是特定的 Header 值或 None（取决于平台）
        """
        from playwright.sync_api import sync_playwright

        token = None
        cookies = []

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=cfg.PLAYWRIGHT_HEADLESS,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                ],
            )

            context = browser.new_context(
                viewport=cfg.PLAYWRIGHT_VIEWPORT,
                locale=cfg.PLAYWRIGHT_LOCALE,
                timezone_id=cfg.PLAYWRIGHT_TIMEZONE,
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0.0.0 Safari/537.36"
                ),
            )

            page = context.new_page()

            # ── 监听网络请求，截获认证 Token ──
            token_header_name = cfg.LIEPIN["token_header"]

            def intercept_request(request):
                nonlocal token
                if token_header_name in request.headers:
                    token = request.headers[token_header_name]

            page.on("request", intercept_request)

            # ── 打开登录页 ──
            print(f"\n{'='*60}")
            print("  请在弹出的浏览器窗口中扫码登录猎聘 HR 后台")
            print(f"  登录页面: {cfg.LIEPIN['login_url']}")
            print(f"{'='*60}\n")

            page.goto(cfg.LIEPIN["login_url"], wait_until="networkidle")

            # ── 等待用户完成登录（检测页面跳转） ──
            try:
                page.wait_for_url(
                    lambda url: "hr.liepin.com" in url and "login" not in url.lower(),
                    timeout=120_000,  # 2 分钟超时
                )
                print("✅ 登录成功！")
            except Exception:
                print("⚠️  登录超时或未检测到跳转，请检查是否已完成登录")
                manual_confirm = input("如已手动登录，按 Enter 继续，输入 q 退出: ")
                if manual_confirm.lower() == "q":
                    browser.close()
                    return None, []

            # ── 等页面稳定后获取 Cookie ──
            page.wait_for_timeout(2000)
            cookies = context.cookies()

            # ── 如果没捕获到 Token，尝试从 localStorage 或 Cookie 获取 ──
            if not token:
                token = self._try_extract_token(page, token_header_name)

            browser.close()

        # ── 保存到本地 ──
        self._save_session(token, cookies)
        return token, cookies

    # ────────────────────────────────────────────────
    # 从浏览器上下文中提取 Token（兜底策略）
    # ────────────────────────────────────────────────
    def _try_extract_token(self, page, token_header_name: str) -> Optional[str]:
        """尝试从 localStorage / Cookie / 页面变量提取 Token"""
        token = None

        # 尝试 localStorage
        try:
            token = page.evaluate(f"localStorage.getItem('{token_header_name}')")
        except Exception:
            pass

        # 尝试从 Cookie 中提取
        if not token:
            for cookie in page.context.cookies():
                if token_header_name in cookie["name"].lower():
                    token = cookie["value"]
                    break

        # 尝试从页面全局变量
        if not token:
            try:
                token = page.evaluate("window.__TOKEN__ || window.token || ''")
            except Exception:
                pass

        return token

    # ────────────────────────────────────────────────
    # 会话持久化
    # ────────────────────────────────────────────────
    def _save_session(self, token: Optional[str], cookies: list[dict]):
        """保存登录凭证到本地"""
        session = {
            "token": token or "",
            "cookies": cookies,
            "saved_at": str(__import__("datetime").datetime.now()),
            "platform": "liepin",
        }
        with open(self.cookie_file, "w", encoding="utf-8") as f:
            json.dump(session, f, ensure_ascii=False, indent=2)
        print(f"✅ 登录凭证已保存到: {self.cookie_file}")

    # ────────────────────────────────────────────────
    # 加载已保存的会话
    # ────────────────────────────────────────────────
    def load_session(self) -> tuple[Optional[str], list[dict]]:
        """
        加载本地保存的登录凭证

        Returns:
            (token, cookies_list)
            如果文件不存在或已过期，返回 (None, [])
        """
        if not self.cookie_file.exists():
            print("❌ 未找到登录凭证，请先执行 interactive_login()")
            return None, []

        with open(self.cookie_file, "r", encoding="utf-8") as f:
            session = json.load(f)

        token = session.get("token") or None
        cookies = session.get("cookies", [])

        # 检查是否过期（可选：猎聘 Cookie 有效期通常为几天）
        print(f"✅ 已加载登录凭证 (保存时间: {session.get('saved_at', '未知')})")
        return token, cookies

    def is_session_valid(self) -> bool:
        """检查本地会话是否存在且可能有效"""
        if not self.cookie_file.exists():
            return False
        try:
            with open(self.cookie_file, "r", encoding="utf-8") as f:
                session = json.load(f)
            return bool(session.get("token") or session.get("cookies"))
        except Exception:
            return False


# ────────────────────────────────────────────────
# CLI 入口：python -m collector.browser
# ────────────────────────────────────────────────
if __name__ == "__main__":
    login = LiepinLogin()
    if login.is_session_valid():
        print("检测到已保存的登录凭证")
        choice = input("重新登录? (y/N): ")
        if choice.lower() != "y":
            sys.exit(0)

    login.interactive_login()
