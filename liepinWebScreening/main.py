"""
猎聘智能简历筛选系统 — 主入口
================================

核心流程（CDP 模式，推荐）：
  1. 用 chrome.exe --remote-debugging-port=9222 启动 Chrome
  2. 登录猎聘，设筛选条件，点搜索，看到候选人结果页
  3. 运行以下命令

用法:
    # 1. 调查页面结构（首次必做，自动分析你打开的搜索结果页）
    python main.py survey

    # 2. 一键采集 + 分析 + 报告
    python main.py run --connect --jd-text "JD描述..."

    # 3. 仅采集
    python main.py collect --connect --max 100

    # 4. 重新分析已有缓存
    python main.py analyze --jd-text "..." --resume-dir data/resumes/liepin/20260616

    # 5. 导出报告
    python main.py report --job-id "JD-xxx"

注意：
    --connect 模式不需要传 URL。猎聘搜索页 URL 不带筛选条件，
    系统会直接连接到你已有的浏览器，自动找到搜索结果页。
"""

import asyncio
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config as cfg
from collector.liepin_collector import LiepinCollector
from analyzer import ScreeningPipeline
from models import JDRequirement, AnalysisResult
from storage import JSONStorage
from reporter.excel import ExcelReporter


# ════════════════════════════════════════════════════
# 命令实现
# ════════════════════════════════════════════════════

def cmd_survey(port: int = 9222):
    """调查页面结构，连接已有浏览器自动分析猎聘搜索结果页"""
    if not _check_browser_debug_port(port):
        print()
        print("💡 用以下命令一键启动浏览器调试模式：")
        print("   python -m collector.chrome_launcher")
        return

    from collector.page_survey import PageSurvey
    survey = PageSurvey()
    survey.survey()


def cmd_login():
    """登录猎聘 HR 后台（扫码登录）"""
    collector = LiepinCollector(headless=False)
    try:
        collector.login()
        print("\n✅ 登录成功！")
    except Exception as e:
        print(f"\n❌ 登录失败: {e}")
    finally:
        collector.close()


def cmd_collect(
    use_cdp: bool = True,
    search_url: Optional[str] = None,
    max_resumes: int = 200,
    deep: bool = False,
):
    """采集简历"""
    store = JSONStorage()
    collector = None

    try:
        if use_cdp:
            print("\n🔗 CDP 模式：连接到你的浏览器...")
            collector = LiepinCollector.connect_to_chrome()
            if not collector:
                return

            resumes = collector.collect_from_current_tab(
                max_resumes=max_resumes,
                deep=deep,
                progress_callback=lambda c, t, m: print(
                    f"   进度: [{c}/{t}] {m}", end="\r"
                ),
            )
        elif search_url:
            print("\n🌐 常规模式：新开浏览器...")
            collector = LiepinCollector()
            collector.login()
            resumes = collector.collect_from_search(
                search_url, max_resumes=max_resumes,
            )
        else:
            print("❌ 请指定 --connect 或 --search-url")
            return

        print(f"\n✅ 采集完成: {len(resumes)} 份简历已缓存")
        return resumes

    except Exception as e:
        print(f"\n❌ 采集失败: {e}")
        import traceback
        traceback.print_exc()
        return []
    finally:
        if collector:
            collector.close()


def cmd_run(
    use_cdp: bool = True,
    search_url: Optional[str] = None,
    jd_text: Optional[str] = None,
    api_key: Optional[str] = None,
    max_resumes: int = 200,
    deep: bool = False,
):
    """一键执行：采集 → 分析 → 报告"""
    if api_key:
        cfg.DEEPSEEK_API_KEY = api_key

    store = JSONStorage()
    reporter = ExcelReporter()
    resumes = []

    # Step 1: 采集
    collector = None
    try:
        if use_cdp:
            print("\n🔗 CDP 模式：连接到你的浏览器...")
            collector = LiepinCollector.connect_to_chrome()
            if not collector:
                return

            if jd_text:
                print("   JD: 已提供")
            else:
                print("   JD: 暂缺，将仅做语义匹配")

            resumes = collector.collect_from_current_tab(
                max_resumes=max_resumes,
                deep=deep,
                progress_callback=lambda c, t, m: print(
                    f"   进度: [{c}/{t}] {m}", end="\r"
                ),
            )
        elif search_url:
            print("\n🌐 常规模式：新开浏览器...")
            collector = LiepinCollector()
            collector.login()
            resumes = collector.collect_from_search(search_url, max_resumes=max_resumes)
        else:
            print("❌ 请指定 --connect（推荐）或 --search-url")
            return

    except Exception as e:
        print(f"\n❌ 采集阶段失败: {e}")
        import traceback
        traceback.print_exc()
        return
    finally:
        if collector:
            collector.close()

    if not resumes:
        print("❌ 未采集到任何简历")
        return

    print(f"\n{'='*60}")
    print(f"  采集完成: {len(resumes)} 份简历，进入分析流水线")
    print(f"{'='*60}")

    # Step 2: 构建 JD
    jd = JDRequirement(
        jd_id=f"search_{datetime.now():%Y%m%d_%H%M%S}",
        jd_text=jd_text or "（未提供 JD 文本，分析将仅基于语义匹配）",
    )

    if jd_text:
        print(f"\n🧠 正在解析 JD 要求...")
        jd = _enrich_jd_with_deepseek(jd)
        store.save_jd(jd)
    else:
        print(f"\n⚠️  未提供 JD 文本，分析将仅基于语义匹配")
        print(f"   建议: python main.py analyze --resume-dir ... --jd-text '...'")

    # Step 3: 三阶段筛选
    pipeline_start = time.time()
    pipeline = ScreeningPipeline(jd, progress_callback=lambda c, t, s, m: None)
    results = asyncio.run(pipeline.run_all(resumes))

    # Step 4: 保存
    job_id = jd.jd_id
    for result in results:
        result.job_id = job_id
        store.save_result(result, job_id)

    # Step 5: 报告
    report_path = reporter.generate(jd.jd_title or job_id, results)

    # Step 6: 摘要
    pipeline_elapsed = time.time() - pipeline_start
    store.save_session(job_id, {
        "job_title": jd.jd_title or job_id,
        "total_resumes": len(resumes),
        "total_analyzed": len(results),
        "pipeline_time_seconds": round(pipeline_elapsed, 1),
        "levels_distribution": {
            lvl: sum(1 for r in results if r.final_level == lvl)
            for lvl in ["S", "A", "B", "C", "D"]
        },
    })

    print(f"\n✅ 全部完成! 耗时: {pipeline_elapsed:.1f}秒")
    print(f"📊 报告: {report_path}")


def cmd_analyze(jd_text: str, resume_dir: str, api_key: Optional[str] = None):
    """重新分析已有缓存"""
    if api_key:
        cfg.DEEPSEEK_API_KEY = api_key

    resumes = _load_resumes_from_dir(resume_dir)
    if not resumes:
        print("❌ 未找到简历数据")
        return

    jd = JDRequirement(jd_id=f"analysis_{datetime.now():%Y%m%d_%H%M%S}", jd_text=jd_text)
    jd = _enrich_jd_with_deepseek(jd)

    # 打印 JD 筛选条件
    print()
    print("=" * 60)
    print("  JD 筛选条件")
    print("=" * 60)
    if jd.jd_title:
        print(f"  职位: {jd.jd_title}")
    if jd.min_education and jd.min_education != "不限":
        print(f"  学历要求: {jd.min_education}")
    if jd.min_years > 0:
        print(f"  工作经验: {jd.min_years}年以上")
    if jd.must_skills:
        print(f"  硬性技能: {'、'.join(jd.must_skills)}")
    if jd.keywords:
        print(f"  经验关键词: {'、'.join(jd.keywords)}")
    if jd.nice_skills:
        print(f"  加分项: {'、'.join(jd.nice_skills)}")
    print()

    pipeline = ScreeningPipeline(jd)
    results = asyncio.run(pipeline.run_all(resumes))

    store = JSONStorage()
    reporter = ExcelReporter()
    job_id = jd.jd_id
    for result in results:
        result.job_id = job_id
        store.save_result(result, job_id)

    report_path = reporter.generate(jd.jd_title or "自定义分析", results)
    print(f"📊 报告: {report_path}")


def cmd_report(job_id: str):
    """从已有结果生成报告"""
    store = JSONStorage()
    reporter = ExcelReporter()

    results = store.load_results(job_id)
    if not results:
        print(f"❌ 未找到职位 {job_id} 的分析结果")
        return

    report_path = reporter.generate(job_id, results)
    print(f"📊 报告: {report_path}")


# ════════════════════════════════════════════════════
# 辅助函数
# ════════════════════════════════════════════════════

def _enrich_jd_with_deepseek(jd: JDRequirement) -> JDRequirement:
    """用 DeepSeek 从 JD 文本中提取结构化要求"""
    if not jd.jd_text or jd.must_skills:
        return jd

    try:
        from openai import OpenAI

        client = OpenAI(api_key=cfg.DEEPSEEK_API_KEY, base_url=cfg.DEEPSEEK_BASE_URL)

        prompt = f"""你是一位招聘JD解析专家。请从以下JD文本中提取结构化要求，以JSON格式输出。

判断标准：
- must_skills = 硬性资格/证书/具体技能名称（如"律师执业证""CPA""Java""CET-6""驾照"）
  必须是能直接核验的硬条件，通常3~5字以内。
- keywords = 经验领域/业务方向描述（如"刑诉""并购""股权投资""建设工程"）
  这些是经验相关的软性描述，在简历中出现相关词就算匹配。
- nice_skills = 加分项（"英语流利""团队管理""有大厂经验"）

注意：不要把经验描述放到 must_skills 里。"刑诉工作经验"应该拆成 keywords=["刑诉"]。

{jd.jd_text}

{{
  "job_title": "职位名称",
  "min_education": "最低学历要求（博士/硕士/本科/大专/不限）",
  "min_years": 数字（最低工作年限，没有则填0）,
  "must_skills": ["硬性技能/资质关键词"],
  "keywords": ["经验领域/业务方向关键词"],
  "nice_skills": ["加分项"],
  "preferred_industries": ["优先行业"],
  "responsibility": "岗位职责简要描述"
}}"""

        response = client.chat.completions.create(
            model=cfg.DEEPSEEK_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            response_format={"type": "json_object"},
        )

        parsed = json.loads(response.choices[0].message.content)

        jd.jd_title = parsed.get("job_title", jd.jd_title)
        jd.min_education = parsed.get("min_education", "不限")
        jd.min_years = parsed.get("min_years", 0)
        jd.must_skills = []
        jd.nice_skills = parsed.get("nice_skills", [])
        jd.keywords = parsed.get("keywords", [])
        jd.forbidden_keywords = parsed.get("forbidden_keywords", [])
        jd.preferred_industries = parsed.get("preferred_industries", [])
        jd.responsibility_desc = parsed.get("responsibility", "")

        # 后处理：把 must_skills 拆成硬关键词和经验关键词
        stop_words = {"工作", "经验", "能力", "技术", "水平", "知识", "管理", "相关", "背景", "方向"}
        for skill in parsed.get("must_skills", []):
            skill = skill.strip()
            # 短词（<=4字）直接作为硬关键词
            if len(skill) <= 4:
                jd.must_skills.append(skill)
            else:
                # 长短语：去掉停用词后缀取核心词
                for sw in stop_words:
                    idx = skill.find(sw)
                    if idx > 0:
                        core = skill[:idx].strip()
                        if core and len(core) >= 2:
                            jd.keywords.append(core)
                            break
                else:
                    # 没有匹配到停用词，也放到 keywords 做宽松匹配
                    jd.keywords.append(skill)

        # 去重
        jd.must_skills = list(dict.fromkeys(jd.must_skills))
        jd.keywords = list(dict.fromkeys(jd.keywords))

        print(f"✅ JD 解析完成: {jd.jd_title}")
        print(f"   硬性技能: {jd.must_skills}")
        print(f"   经验关键词: {jd.keywords}")
        print(f"   学历要求: {jd.min_education}, 经验: {jd.min_years}年")

    except Exception as e:
        print(f"⚠️  JD 解析失败: {e}，使用原始文本")

    return jd


def _load_resumes_from_dir(dir_path: str) -> list:
    """从目录加载缓存的简历"""
    from models import Resume

    resumes = []
    path = Path(dir_path)
    if not path.exists():
        print(f"❌ 目录不存在: {dir_path}")
        return []

    for f in sorted(path.glob("*.json")):
        try:
            with open(f, "r", encoding="utf-8") as fp:
                data = json.load(fp)
            resumes.append(Resume(**data))
        except Exception as e:
            print(f"⚠️  加载失败 {f.name}: {e}")

    print(f"📂 从 {dir_path} 加载了 {len(resumes)} 份简历")
    return resumes


# ════════════════════════════════════════════════════
# 工具
# ════════════════════════════════════════════════════

def _check_browser_debug_port(port: int = 9222) -> bool:
    """检查浏览器调试端口是否可用"""
    import urllib.request
    try:
        resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=2)
        return resp.status == 200
    except Exception:
        pass
    print(f"❌ 无法连接浏览器调试端口 127.0.0.1:{port}")
    return False


def _resolve_jd_text(jd_text, jd_file):
    """从 --jd-text 或 --jd-file 获取 JD 文本"""
    if jd_file:
        path = Path(jd_file)
        if not path.exists():
            print(f"❌ JD 文件不存在: {jd_file}")
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception as e:
            print(f"❌ 读取 JD 文件失败: {e}")
            return None
    return jd_text

# ════════════════════════════════════════════════════
# CLI
# ════════════════════════════════════════════════════

def print_banner():
    print(r"""
    ╔══════════════════════════════════════╗
    ║   猎聘智能简历筛选系统 v2.0          ║
    ║   CDP 连接你已有浏览器              ║
    ║   规则 → 向量 → DeepSeek 分析       ║
    ╚══════════════════════════════════════╝
    """)


def main():
    print_banner()

    import argparse

    parser = argparse.ArgumentParser(
        description="猎聘智能简历筛选系统",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # survey
    p_survey = subparsers.add_parser("survey",
        help="调查页面结构")
    p_survey.add_argument("--port", type=int, default=9222,
        help="浏览器调试端口（默认9222）")

    # login
    subparsers.add_parser("login", help="登录猎聘 HR 后台（扫码）")

    # collect
    p_collect = subparsers.add_parser("collect", help="仅采集简历")
    p_collect.add_argument("--connect", action="store_true", help="连接到你的浏览器（推荐）")
    p_collect.add_argument("--port", type=int, default=9222, help="调试端口")
    p_collect.add_argument("--search-url", help="搜索页 URL（后备选项）")
    p_collect.add_argument("--max", type=int, default=200, help="最大采集数量")
    p_collect.add_argument("--deep", action="store_true", help="深度采集：逐点打开获取完整详情")

    # run
    p_run = subparsers.add_parser("run", help="一键采集+分析+报告")
    p_run.add_argument("--connect", action="store_true", help="连接到你的浏览器（推荐）")
    p_run.add_argument("--port", type=int, default=9222, help="调试端口")
    p_run.add_argument("--search-url", help="搜索页 URL（后备选项）")
    p_run.add_argument("--jd-text", help="JD 文本描述（与 --jd-file 二选一）")
    p_run.add_argument("--jd-file", help="从文件读取 JD 文本（与 --jd-text 二选一）")
    p_run.add_argument("--api-key", help="DeepSeek API Key")
    p_run.add_argument("--max", type=int, default=200, help="最大采集数量")
    p_run.add_argument("--deep", action="store_true", help="深度采集：逐点打开获取完整详情")

    # analyze
    p_analyze = subparsers.add_parser("analyze", help="分析已有简历缓存")
    p_analyze.add_argument("--jd-text", help="JD 文本（与 --jd-file 二选一）")
    p_analyze.add_argument("--jd-file", help="从文件读取 JD 文本（与 --jd-text 二选一）")
    p_analyze.add_argument("--resume-dir", required=True, help="简历缓存目录")
    p_analyze.add_argument("--api-key", help="DeepSeek API Key")

    # report
    p_report = subparsers.add_parser("report", help="从已有结果生成报告")
    p_report.add_argument("--job-id", required=True, help="职位 ID")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    if args.command == "survey":
        cmd_survey(port=args.port)

    elif args.command == "login":
        cmd_login()

    elif args.command == "collect":
        if args.connect:
            if _check_browser_debug_port(args.port):
                cmd_collect(use_cdp=True, max_resumes=args.max, deep=args.deep)

    elif args.command == "analyze":
        jd_text = _resolve_jd_text(args.jd_text, args.jd_file)
        if not jd_text:
            print("请提供 JD 文本（--jd-text 或 --jd-file）")
            return
        cmd_analyze(jd_text=jd_text, resume_dir=args.resume_dir, api_key=args.api_key)

    elif args.command == "report":
        cmd_report(args.job_id)

if __name__ == "__main__":
    main()
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               