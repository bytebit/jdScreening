"""
CDP 连接器 — 连接到用户已有的 Chrome 浏览器
==============================================

核心：
  1. 通过 CDP 连接用户已有的 Chrome（需 --remote-debugging-port=9222 启动）
  2. 自动找到猎聘搜索结果标签页
  3. 读取 DOM、Cookie、网络请求，无需重新登录

如果 Chrome 还没以调试模式启动，提供了 chrome_launcher.py 帮你一键启动。
"""

import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable

from playwright.sync_api import sync_playwright


class CDPConnector:
    """
    CDP 连接器

    连接到用户已有的 Chrome 浏览器，找到猎聘搜索结果页。

    用法：
        connector = CDPConnector()
        if connector.connect():
            page = connector.find_search_tab()
            if page:
                # 在页面上工作
                pass
        connector.close()
    """

    def __init__(self, cdp_url: str = "http://127.0.0.1:9222"):
        self.cdp_url = cdp_url
        self._playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.connected = False

    # ──────────────────────────────────────────────
    # 连接
    # ──────────────────────────────────────────────

    def connect(self) -> bool:
        """
        连接到用户已有的 Chrome 浏览器

        Returns:
            是否连接成功
        """
        try:
            self._playwright = sync_playwright().__enter__()
            self.browser = self._playwright.chromium.connect_over_cdp(self.cdp_url)

            contexts = self.browser.contexts
            if contexts:
                self.context = contexts[0]
            else:
                self.context = self.browser.new_context()

            self.connected = True
            page_count = len(self.context.pages)
            print(f"✅ 已连接到 Chrome 浏览器 ({page_count} 个标签页)")
            return True

        except Exception as e:
            print(f"❌ 连接 Chrome 失败: {e}")
            print()
            print("💡 解决方法（三选一）：")
            print()
            print("   方法 1：运行一键启动脚本（推荐）")
            print("   ─────────────────────────────")
            print("   python -m collector.chrome_launcher")
            print()
            print("   方法 2：命令行启动（Windows）")
            print("   ─────────────────────────────")
            print("   先关掉所有 Chrome 窗口，然后运行：")
            print('   "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" --remote-debugging-port=9222')
            print()
            print("   或按 Win+R，粘贴：")
            print("   chrome.exe --remote-debugging-port=9222")
            print()
            print("   方法 3：macOS/Linux")
            print("   ─────────────────────────────")
            print("   macOS: /Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome --remote-debugging-port=9222")
            print("   Linux: google-chrome --remote-debugging-port=9222")
            print()
            print("   Chrome 启动后，登录猎聘 → 搜索候选人 → 再运行此命令")
            return False

    # ──────────────────────────────────────────────
    # 查找猎聘标签页
    # ──────────────────────────────────────────────

    def find_search_tab(self) -> Optional[object]:
        """
        自动找到猎聘搜索结果标签页

        查找优先级：
          1. 标题含"搜索"/"人才"/"筛选" 且 URL 含 liepin
          2. 任何 liepin 标签页
          3. 从所有标签页中智能选择

        Returns:
            页面对应 (playwright Page)，或 None
        """
        if not self.connected or not self.context:
            return None

        pages = self.context.pages
        liepin_pages = []

        for p in pages:
            try:
                url = p.url.lower()
                if "liepin" in url or "lpt" in url:
                    liepin_pages.append(p)
            except Exception:
                continue

        # 优先找搜索结果页
        for p in liepin_pages:
            title = p.title().lower()
            url = p.url.lower()
            if any(kw in title for kw in ["搜索", "人才", "筛选"]) or \
               any(kw in url for kw in ["search", "talent"]):
                self.page = p
                print(f"✅ 找到猎聘搜索标签: 「{p.title()[:50]}」")
                return p

        # 其次找任何猎聘页面
        for p in liepin_pages:
            self.page = p
            print(f"✅ 找到猎聘标签: 「{p.title()[:50]}」")
            return p

        # 没有任何猎聘页面，让用户选
        print(f"⚠️  未自动找到猎聘页面。你当前有 {len(pages)} 个标签页：")
        for i, p in enumerate(pages):
            try:
                print(f"   [{i}] {p.title()[:60]}")
            except Exception:
                print(f"   [{i}] <不可访问>")

        # 自动选第一个有内容的标签
        for p in pages:
            try:
                title = p.title()
                if title and title != "about:blank" and "新标签页" not in title:
                    print(f"   → 自动选择: 「{title[:40]}」")
                    self.page = p
                    return p
            except Exception:
                continue

        return None

    def get_page_by_index(self, index: int):
        """按索引获取标签页"""
        pages = self.context.pages
        if 0 <= index < len(pages):
            return pages[index]
        return None

    def get_all_tabs(self) -> list:
        """列出所有标签页"""
        if not self.connected or not self.context:
            return []
        return self.context.pages

    # ──────────────────────────────────────────────
    # Cookie 导出
    # ──────────────────────────────────────────────

    def export_cookies(self) -> list[dict]:
        if not self.context:
            return []
        try:
            cookies = self.context.cookies()
            print(f"📦 已导出 {len(cookies)} 条 Cookie")
            return cookies
        except Exception as e:
            print(f"⚠️  导出 Cookie 失败: {e}")
            return []

    def save_cookies(self, filepath: str = "data/cookies/liepin_cookies.json"):
        """导出 Cookie 并保存到文件"""
        cookies = self.export_cookies()
        if not cookies:
            return False

        Path(filepath).parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump({
                "cookies": cookies,
                "saved_at": datetime.now().isoformat(),
                "source": "cdp",
            }, f, ensure_ascii=False, indent=2)
        print(f"💾 Cookie 已保存到: {filepath}")
        return True

    # ──────────────────────────────────────────────
    # 等待结果
    # ──────────────────────────────────────────────

    def wait_for_results(self, timeout: int = 10) -> bool:
        """等待搜索结果加载"""
        if not self.page:
            return False

        print("⏳ 等待搜索结果加载...")
        try:
            self.page.wait_for_load_state("networkidle", timeout=timeout * 1000)
        except Exception:
            pass
        time.sleep(3)

        # 检测候选人卡片
        card_selectors = [
            "[class*='candidate']",
            "[class*='talent']",
            "[class*='searchResult'] [class*='item']",
            "[class*='list'] [class*='item']",
        ]
        for sel in card_selectors:
            try:
                cards = self.page.query_selector_all(sel)
                if len(cards) >= 3:
                    print(f"✅ 检测到候选人卡片: {len(cards)} 个")
                    return True
            except Exception:
                continue

        page_text = self.page.inner_text("body").lower() if self.page else ""
        if any(kw in page_text for kw in ["暂无", "没有找到", "未找到", "无结果"]):
            print("⚠️  搜索无结果")
            return False

        print("⚠️  未检测到候选人卡片，请确认是否已在搜索页点了搜索")
        return False

    # ──────────────────────────────────────────────
    # 清理
    # ──────────────────────────────────────────────

    def close(self):
        """关闭连接（不关闭用户浏览器）"""