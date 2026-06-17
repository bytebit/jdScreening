"""
全局配置
========
所有环境变量和全局参数集中管理，修改配置只需改这个文件。
"""

import os
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path
from dotenv import load_dotenv

# 加载 .env 文件（如果有）
load_dotenv(Path(__file__).resolve().parent / ".env")

# ──────────────────────────────────────────────
# DeepSeek API 配置
# ──────────────────────────────────────────────
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "sk-your-key-here")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = "deepseek-chat"          # 或 deepseek-reasoner
DEEPSEEK_TEMPERATURE = 0.1               # 低温度保证评分一致性
DEEPSEEK_MAX_TOKENS = 4096
DEEPSEEK_RATE_LIMIT = 10                  # 每分钟最多请求数
DEEPSEEK_RETRY_TIMES = 3                  # 失败重试次数

# ──────────────────────────────────────────────
# 猎聘配置（Playwright 驱动模式）
# ──────────────────────────────────────────────
LIEPIN = {
    # ── 基础（lpt 新版平台） ──
    "login_url": "https://lpt.liepin.com",                           # 登录页
    "search_base_url": "https://lpt.liepin.com/search",              # 搜索页

    # ── 🎯 候选人卡片选择器（基于实际 HTML） ──
    # li[class*='resumeCardWrap'] 是候选人卡片，有 data-resumeidencode 属性
    "card_selector": "li[class*='resumeCardWrap']",
    # 翻页按钮
    "next_page_selector": "[class*='pagination'] [class*='next'], .pagination .next, a:has-text('>')",
    "next_page_disabled_selector": "[class*='pagination'] [class*='next'].disabled, .pagination .next.disabled",
    # 分页间隔（秒）
    "page_interval": 3.0,

    # ── DOM 提取选择器（基于猎聘 lpt 实际结构） ──
    "dom_selectors": {
        "name": ".nest-resume-personal-name em",
        "title": ".nest-resume-personal-expect [title]",
        "company": ".work-item-compname",
        "skills": ".nest-resume-personal-skills span",
    },

    # ── 详情弹窗选择器（点击穿透用） ──
    "detail_panel_selector": (
        ".resume-detail-modal, .detail-drawer, "
        ".candidate-detail, [class*='detail'], "
        "[class*='drawer'], [class*='modal']"
    ),
    "close_btn_selector": (
        ".close-btn, .close-icon, .drawer-close, "
        "[class*='close'], [aria-label='关闭'], "
        "button:has-text('关闭')"
    ),

    # ── API 拦截关键词（lpt 新版平台） ──
    "list_api_keywords": [
        "/api/search",
        "/api/list",
        "/search/list",
        "/api/talent",
        "/api/resume/search",
    ],
    "detail_api_keywords": [
        "/api/resume/detail",
        "/api/talent/detail",
        "/api/detail",
        "/resume/get",
    ],

    # ── 通用 ──
    "user_agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "request_interval": 1.5,              # 操作间隔(秒)
    "max_retries": 3,
}

# ──────────────────────────────────────────────
# Playwright 登录配置
# ──────────────────────────────────────────────
PLAYWRIGHT_HEADLESS = False               # 登录时必须有 UI
PLAYWRIGHT_VIEWPORT = {"width": 1920, "height": 1080}
PLAYWRIGHT_LOCALE = "zh-CN"
PLAYWRIGHT_TIMEZONE = "Asia/Shanghai"
COOKIE_FILE = "data/cookies/liepin_cookies.json"

# ──────────────────────────────────────────────
# 筛选流水线配置
# ──────────────────────────────────────────────
@dataclass
class PipelineConfig:
    """每个环节的开关和阈值"""

    # ── 第一阶段：规则引擎 ──
    enable_stage1: bool = True
    # 学历等级映射
    education_rank: dict = field(default_factory=lambda: {
        "博士": 5, "博士后": 5,
        "硕士": 4, "研究生": 4,
        "本科": 3, "学士": 3,
        "大专": 2, "专科": 2,
        "高中": 1, "中专": 1, "中技": 1,
        "其他": 0, "不限": 0,
    })
    # 关键词命中比例阈值（命中关键词/总必含关键词 >= 此值才算通过）
    keyword_hit_ratio: float = 0.6

    # ── 第二阶段：向量语义匹配 ──
    enable_stage2: bool = False
    # 嵌入模型名称 (fastembed 支持的模型)
    # "BAAI/bge-small-zh-v1.5" 轻量中文 (~200MB), "BAAI/bge-base-zh-v1.5" (~400MB)
    embedding_model: str = "BAAI/bge-small-zh-v1.5"
    # 相似度阈值，低于此值的简历不进入第三阶段
    similarity_threshold: float = 0.45
    # 或使用 Top-K 策略：只取前 N 份进入下一阶段
    stage2_top_k: Optional[int] = 30

    # ── 第三阶段：DeepSeek 深度分析 ──
    enable_stage3: bool = True
    # 评分等级阈值
    score_levels: dict = field(default_factory=lambda: {
        "S": 90, "A": 75, "B": 60, "C": 40, "D": 0,
    })
    # 哪些等级建议进入面试
    recommend_levels: list = field(default_factory=lambda: ["S", "A", "B"])

    # ── 一般配置 ──
    max_resumes_per_run: int = 200        # 单次任务最多处理简历数
    batch_size: int = 5                   # DeepSeek 批量分析的并发数


PIPELINE = PipelineConfig()

# ──────────────────────────────────────────────
# 数据存储配置
# ──────────────────────────────────────────────
STORAGE_DIR = "data"
COOKIE_DIR = "data/cookies"
RESUME_CACHE_DIR = "data/resumes"
RESULT_DIR = "data/results"
LOG_DIR = "data/logs"
REPORT_DIR = "data/reports"
