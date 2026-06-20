import json, re, sys, time
from datetime import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config as cfg
from models import Resume

class LiepinCollector:
    def __init__(self, headless=False):
        self._playwright=None; self.browser=None; self.context=None; self.page=None
        self.headless=headless; self.is_cdp_mode=False
        self._captured_api_data=[]; self._captured_detail_data=[]; self._api_calls=[]
        self._has_cards=False; self._card_selector=cfg.LIEPIN["card_selector"]

    @classmethod
    def connect_to_chrome(cls, cdp_url="http://127.0.0.1:9222"):
        from playwright.sync_api import sync_playwright
        c=cls.__new__(cls)
        c.is_cdp_mode=True; c._captured_api_data=[]; c._captured_detail_data=[]
        c._api_calls=[]; c._has_cards=False; c._card_selector=cfg.LIEPIN["card_selector"]
        c._playwright=None; c.browser=None; c.context=None; c.page=None
        c._playwright=sync_playwright().__enter__()
        try: c.browser=c._playwright.chromium.connect_over_cdp(cdp_url)
        except Exception as e: print(f"连接失败: {e}"); c._playwright.__exit__(None,None,None); return None
        contexts=c.browser.contexts
        c.context=contexts[0] if contexts else c.browser.new_context()
        page=c._find_search_tab()
        if page: c.page=page; c._setup_api_interception(); print("CDP 就绪")
        else: c.close(); return None
        return c

    def _find_search_tab(self):
        pages=self.context.pages if self.context else []
        for p in pages:
            try:
                u=p.url.lower()
                if 'liepin' not in u and 'lpt' not in u: continue
                if any(k in u for k in ['search','talent']) or any(k in p.title().lower() for k in ['搜索','人才','筛选']):
                    self.page=p; return p
            except: continue
        return None

    def _setup_api_interception(self):
        self._captured_api_data=[]; self._captured_detail_data=[]
        if not self.page: return
        def on_resp(r):
            if 'json' not in r.headers.get('content-type',''): return
            try:
                d=r.json()
                if isinstance(d,dict):
                    inner=d.get('data',d)
                    inner2=inner.get('data',inner) if isinstance(inner,dict) else inner
                    items=inner2.get('list') or inner2.get('items') or inner2.get('rows',[]) if isinstance(inner2,dict) else (inner2 if isinstance(inner2,list) else [])
                    if isinstance(items,list) and len(items)>=2 and isinstance(items[0],dict):
                        if any(k in json.dumps(items[0],ensure_ascii=False)[:200] for k in ['name','姓名','title','职位','company']):
                            self._captured_api_data.extend(items); return
                    dd=d.get('data',d)
                    if isinstance(dd,dict) and any(k in dd for k in ['name','educationList','workExperienceList','skillList']):
                        self._captured_detail_data.append(dd)
            except: pass
        self.page.on('response',on_resp)

    def collect_from_current_tab(self, max_resumes=200, deep=False, progress_callback=None):
        if not self.page: print("未连接"); return []
        all_resumes, seen_ids = [], set()
        page_no, empty_pages = 1, 0
        from storage import JSONStorage as _Store
        store = _Store()
        while len(all_resumes) < max_resumes and empty_pages < 3:
            print(f"第 {page_no} 页...")
            self._wait_for_cards()
            page_resumes = self._extract_from_dom()
            # 只取还需要的那几份（按 max 截断）
            need = max_resumes - len(all_resumes)
            taken = []
            for r in page_resumes:
                if len(taken) >= need: break
                if r.id not in seen_ids: seen_ids.add(r.id); taken.append(r)
            print(f"新增 {len(taken)} 份 (共 {len(all_resumes) + len(taken)} 份)")

            if taken:
                if deep:
                    self._enrich_with_details(taken, store)
                    for r in taken:
                        if not r.source_url:
                            store.save_resume(r)
                        print(f"   已完成采集: {r.name}")
                else:
                    for r in taken:
                        store.save_resume(r)
                        print(f"   已完成采集: {r.name}")

            all_resumes.extend(taken)
            empty_pages = 0 if taken else empty_pages + 1
            if progress_callback: progress_callback(len(all_resumes), max_resumes, f"第{page_no}页")
            if len(all_resumes) >= max_resumes: break
            if not self._go_to_next_page(): print("已到最后一页"); break
            page_no += 1; time.sleep(cfg.LIEPIN["page_interval"])
        print(f"\n采集完成: {len(all_resumes)} 份")
        self._save_cookies()
        return all_resumes

    def _wait_for_cards(self, timeout=10):
        try: self.page.wait_for_load_state("networkidle", timeout=timeout*1000)
        except: pass
        time.sleep(2)
        for sel in self._card_selector.split(","):
            s=sel.strip()
            if not s: continue
            try:
                if len(self.page.query_selector_all(s)) >= 2: self._card_selector=s; return
            except: continue

    def _extract_from_dom(self):
        resumes=[]
        try: cards=self.page.query_selector_all(self._card_selector)
        except: return []
        for card in cards:
            try:
                text=card.inner_text()
                rid=card.get_attribute('data-resumeidencode') or card.get_attribute('data-id') or f"dom_{abs(hash(text[:80]))}"
                url=card.get_attribute('data-resumeurl') or ''
                name=''
                for ns in cfg.LIEPIN['dom_selectors']['name'].split(','):
                    ns=ns.strip()
                    if not ns: continue
                    try:
                        el=card.query_selector(ns)
                        if el: name=el.inner_text().strip(); break
                    except: continue
                if not name: name=(text.split('\n')[0] if text else '')
                resume=Resume(id=rid, platform_id=rid, platform='liepin', name=name, source_url=url, raw_text=text, collected_at=datetime.now().isoformat())
                m=re.search(r'(\d+)\s*年',text)
                if m: resume.years_of_experience=float(m.group(1))
                for kw in ['博士','硕士','本科','大专','中专']:
                    if kw in text: resume.education_level=kw; break
                resumes.append(resume)
            except: continue
        return resumes

    def _enrich_with_details(self, resumes, store=None):
        if not self.context: return
        to_enrich=[r for r in resumes if r.source_url]
        if not to_enrich: return
        for r in to_enrich:
            new_page=None
            try:
                new_page=self.context.new_page()
                new_page.goto(r.source_url, wait_until="load", timeout=30000)
                best_html=""
                for _ in range(5):
                    time.sleep(1)
                    try:
                        html=new_page.content()
                        if len(html)>len(best_html): best_html=html
                        if len(html)>50000: break
                    except: pass
                detail_text=""
                if best_html:
                    clean=re.sub(r'<(script|style)[^>]*>.*?</\1>','',best_html,flags=re.DOTALL|re.IGNORECASE)
                    clean=re.sub(r'<[^>]+>','\n',clean)
                    lines=[l.strip() for l in clean.split('\n') if l.strip()]
                    detail_text='\n'.join(lines)
                if len(detail_text)>len(r.raw_text)+50:
                    r.raw_text=detail_text
                new_page.close()
                # 每采完一份立即保存
                if store:
                    store.save_resume(r)
                    print(f"   已保存: {r.name} ({len(r.raw_text)}ch)")
            except:
                if new_page:
                    try: new_page.close()
                    except: pass

    def _go_to_next_page(self):
        if not self.page: return False
        try:
            # 猎聘分页 DOM 结构（已验证）：
            # ul.ant-lpt-pagination > li.ant-lpt-pagination-next > button
            # 当前页码: li.ant-lpt-pagination-item-active

            # 找"下一页"按钮（优先）
            next_btn = self.page.query_selector('li.ant-lpt-pagination-next:not(.ant-lpt-pagination-disabled)')
            if next_btn:
                next_btn.click()
                time.sleep(2)
                return True

            # 兜底：找任意可点的页码
            for page_sel in [
                'li.ant-lpt-pagination-item:not(.ant-lpt-pagination-item-active) a',
                '[class*="pagination-next"]',
                '[class*="next"]:not([class*="disabled"])',
            ]:
                el = self.page.query_selector(page_sel)
                if el:
                    try:
                        el.click()
                        time.sleep(2)
                        return True
                    except: continue

            return False
        except:
            return False

    def _save_cookies(self):
        try:
            from .cdp_connector import CDPConne