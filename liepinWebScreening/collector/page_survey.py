"""
猎聘搜索结果页 — DOM 和 API 调查工具
======================================

用法：
    # 推荐方式：连接到你已有的 Chrome
    # 前提：Chrome 用 chrome.exe --remote-debugging-port=9222 启动
    # 且已登录猎聘，打开了搜索结果页
    python -m collector.page_survey

    # 或通过 main.py
    python main.py survey

说明：
    本工具直接连接到你已有的 Chrome 浏览器，
    自动找到猎聘搜索结果标签页，分析 DOM 结构、API 请求模式，
    输出推荐配置供填入 config.py。

    不需要传 URL——因为猎聘搜索页是 SPA，URL 不带筛选条件。
"""

import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config as cfg
from collector.cdp_connector import CDPConnector


class PageSurvey:
    """
    页面调查工具

    连接到用户已有的 Chrome 浏览器，自动找到猎聘搜索结果页，
    分析 DOM 结构和 API 请求模式，输出推荐配置。
    """

    def __init__(self):
        self.connector = None

    def survey(self, headless: bool = False):
        """
        执行页面调查

        Args:
            headless: 无头模式（CDP 模式下忽略）
        """
        print(f"\n{'='*70}")
        print("  🔍 猎聘页面调查工具")
        print(f"  连接到你已有的 Chrome 浏览器，分析搜索结果页")
        print(f"{'='*70}")

        # 连接到用户 Chrome
        self.connector = CDPConnector()
        if not self.connector.connect():
            print("\n💡 请先用以下命令启动 Chrome：")
            print("   chrome.exe --remote-debugging-port=9222")
            print("   然后登录猎聘 → 搜索候选人 → 看到结果页")
            return

        # 查找搜索标签页
        page = self.connector.find_search_tab()
        if not page:
            print("\n❌ 未找到猎聘页面。确认：")
            print("   1. 已在 Chrome 中打开猎聘并登录")
            print("   2. 已搜索候选人，页面上有结果")
            print("\n   当前打开的标签页：")
            for i, p in enumerate(self.connector.get_all_tabs()):
                print(f"     [{i}] {p.title()[:60]}")
            self.connector.close()
            return

        # 激活标签页
        page.bring_to_front()
        time.sleep(1)

        # 设置 API 监听
        api_calls = []

        def on_request(request):
            if request.resource_type in ("xhr", "fetch"):
                api_calls.append({
                    "url": request.url,
                    "method": request.method,
                    "time": datetime.now().isoformat(),
                })

        page.on("request", on_request)

        # 等页面稳定
        time.sleep(3)

        # 执行分析
        results = {}

        print("\n[1/4] 分析页面基本信息...")
        results["page_info"] = self._analyze_page_info(page)

        if results["page_info"].get("is_login"):
            print("\n⚠️  这个页面是登录页。请先在 Chrome 中登录猎聘并搜索候选人。")
            self.connector.close()
            return

        print("\n[2/4] 分析候选人卡片...")
        results["cards"] = self._analyze_cards(page)

        print("\n[3/4] 分析API请求模式...")
        # 给页面一点时间产生 API 请求
        time.sleep(2)
        results["api_calls"] = self._analyze_api_calls(api_calls)

        print("\n[4/4] 分析翻页组件...")
        results["pagination"] = self._analyze_pagination(page)

        # 输出报告
        self._print_report(results)

        # 保存 Cookie
        self.connector.save_cookies()

        self.connector.close()

    def _analyze_page_info(self, page) -> dict:
        """分析页面基本信息"""
        info = {
            "title": page.title(),
            "url": page.url,
            "is_login": "login" in page.url.lower(),
        }
        print(f"   页面标题: {info['title']}")
        print(f"   当前URL: {info['url'][:80]}")
        print(f"   登录状态: {'❌ 需登录' if info['is_login'] else '✅ 已登录'}")
        return info

    def _analyze_cards(self, page) -> dict:
        """分析候选人卡片 DOM 结构"""
        result = {
            "possible_selectors": [],
            "card_count": 0,
            "sample_card_html": "",
            "field_selectors": {},
        }

        # 尝试所有可能的卡片选择器
        candidate_selectors = [
            "[class*='candidate']",
            "[class*='talent']",
            "[class*='searchResult']",
            "[class*='search-result']",
            "[class*='item']",
            "[class*='card']",
            "li[class*='item']",
            "table tr",
        ]

        found = {}
        for sel in candidate_selectors:
            try:
                els = page.query_selector_all(sel)
                if len(els) >= 2:
                    sample = els[0].inner_text()[:80]
                    found[sel] = {"count": len(els), "sample": sample}
            except Exception:
                continue

        # 按接近 20 条排序
        sorted_sels = sorted(found.items(), key=lambda x: abs(x[1]["count"] - 20))

        result["possible_selectors"] = [
            {"selector": s, "count": v["count"], "sample": v["sample"]}
            for s, v in sorted_sels[:5]
        ]

        if sorted_sels:
            best = sorted_sels[0][0]
            els = page.query_selector_all(best)
            result["card_count"] = len(els)
            if els:
                html = els[0].inner_html()[:500]
                result["sample_card_html"] = html

                # 自动推测字段选择器
                result["field_selectors"] = self._infer_field_selectors(els[0], html)

        print(f"   找到 {result['card_count']} 个候选人卡片")
        print(f"\n   推荐选择器 (按匹配度排序):")
        for idx, sel in enumerate(result["possible_selectors"][:3], 1):
            print(f"     {idx}. {sel['selector']} ({sel['count']}个)")
            print(f"        样例: {sel['sample'][:60]}")

        if result["sample_card_html"]:
            print(f"\n   第一张卡片 HTML (前500字符):")
            print(f"   {'─'*60}")
            print(f"   {result['sample_card_html']}")
            print(f"   {'─'*60}")

        if result.get("field_selectors"):
            print(f"\n   自动推测的字段选择器:")
            for field, sel in result["field_selectors"].items():
                print(f"     {field}: {sel}")

        return result

    def _infer_field_selectors(self, card, html: str) -> dict:
        """从卡片 HTML 自动推测字段选择器"""
        selectors = {}

        # 查找可能包含姓名的元素（通常是第一个文本元素或最大的字体）
        try:
            # 尝试找 em / strong / b / h 等强调标签
            for tag in ["em", "strong", "b", "h3", "h4", "h5", ".name", ".title"]:
                els = card.query_selector_all(tag)
                if els:
                    selectors["name"] = tag
                    break
        except Exception:
            pass

        # 查找标签/技能区域
        for tag_sel in ["[class*='tag']", "[class*='skill']", "[class*='label']"]:
            try:
                els = card.query_selector_all(tag_sel)
                if els:
                    selectors["skills"] = tag_sel
                    break
            except Exception:
                continue

        return selectors

    def _analyze_api_calls(self, api_calls: list) -> dict:
        """分析 API 请求模式"""
        result = {
            "list_api_candidates": [],
            "detail_api_candidates": [],
            "all_urls": [],
        }

        url_counts = {}
        for call in api_calls:
            base = re.sub(r'=[^&]*', '=VALUE', call["url"])
            url_counts[base] = url_counts.get(base, 0) + 1

        sorted_urls = sorted(url_counts.items(), key=lambda x: x[1], reverse=True)

        list_kw = ["search", "list", "page", "recommend", "query"]
        detail_kw = ["detail", "get", "resume", "info", "profile"]

        for url, count in sorted_urls[:20]:
            entry = {"url": url, "count": count}
            if any(k in url.lower() for k in list_kw):
                result["list_api_candidates"].append(entry)
            if any(k in url.lower() for k in detail_kw):
                result["detail_api_candidates"].append(entry)
            result["all_urls"].append(entry)

        print(f"\n   共捕获 {len(api_calls)} 个 XHR/Fetch 请求")
        print(f"\n   📋 可能是【列表 API】的请求:")
        for api in result["list_api_candidates"][:4]:
            url_short = api["url"][:100]
            print(f"     {url_short}  ({api['count']}次)")
        print(f"\n   📋 可能是【详情 API】的请求:")
        for api in result["detail_api_candidates"][:4]:
            url_short = api["url"][:100]
            print(f"     {url_short}  ({api['count']}次)")

        return result

    def _analyze_pagination(self, page) -> dict:
        """分析翻页组件"""
        result = {"selectors": []}

        pagination_sels = [
            "[class*='pagination']",
            "[class*='page']",
            "[class*='paging']",
            ".pager",
            "nav[aria-label*='page']",
        ]

        for sel in pagination_sels:
            try:
                el = page.query_selector(sel)
                if el:
                    text = el.inner_text()[:80]
                    html = el.inner_html()[:200]
                    result["selectors"].append({
                        "selector": sel,
                        "text": text,
                        "html": html,
                    })
            except Exception:
                continue

        if result["selectors"]:
            print(f"\n   找到翻页组件:")
            for s in result["selectors"]:
                print(f"     {s['selector']}: {s['text']}")
        else:
            print(f"\n   ⚠️  未识别到分页组件（可能是滚动加载）")

        return result

    def _print_report(self, results: dict):
        """输出配置建议"""
        cards = results.get("cards", {})
        pagination = results.get("pagination", {})
        apis = results.get("api_calls", {})

        print(f"\n\n{'='*70}")
        print("  📋 推荐配置 — 复制以下内容到 config.py")
        print(f"="*70)

        if cards.get("possible_selectors"):
            best = cards["possible_selectors"][0]
            print(f"""
# ── 候选人卡片选择器 ──
"card_selector": "{best['selector']}",""")

        if pagination.get("selectors"):
            for s in pagination["selectors"]:
                print(f"""
# ── 翻页按钮选择器 ──
"next_page_selector": "{s['selector']} [class*='next'],""")

        if apis.get("list_api_candidates"):
            print(f"""
# ── 列表 API 关键词 ──
"list_api_keywords": [""")
            for api in apis["list_api_candidates"][:4]:
                path = api["url"].split("?")[0]
                for kw in ["/api/", "/v1/", "/v2/"]:
                    if kw in path:
                        path = path[path.index(kw):]
                        break
                print(f'    "{path}",')
            print("],")

        if cards.get("field_selectors"):
            fs = cards["field_selectors"]
            skills_default = "[class*=\"tag\"]"
            print(f"""
# ── DOM 字段提取选择器 ──
"dom_selectors": {{
    "name": "{fs.get('name', '.name')}",
    "title": "{fs.get('title', '.title')}",
    "company": "{fs.get('company', '.company')}",
    "skills": "{fs.get('skills', skills_default)}",
}},""")

        print(f"\n{'='*70}")
        print("  提示：将以上内容复制到 config.py 的 LIEPIN 字典中")
        print(f"{'='*70}")


if __name__ == "__main__":
    survey = PageSurvey()
    survey.survey()
