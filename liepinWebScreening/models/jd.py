"""
岗位描述 (JD) 相关数据模型
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class JDRequirement:
    """
    经过规则+AI解析后的结构化 JD 要求
    """
    # ── 原始信息 ──
    jd_id: str = ""
    jd_title: str = ""
    jd_text: str = ""                     # 岗位描述原始全文
    jd_url: str = ""                      # 猎聘上的 JD 链接

    # ── 硬性要求 (must-have) ──
    min_education: str = "不限"           # 最低学历要求
    min_years: int = 0                    # 最低工作年限
    must_skills: list = field(default_factory=list)    # 必备技能关键词
    required_certificates: list = field(default_factory=list)  # 证书要求

    # ── 软性偏好 (nice-to-have) ──
    nice_skills: list = field(default_factory=list)    # 加分技能
    preferred_industries: list = field(default_factory=list)   # 优先行业
    preferred_companies: list = field(default_factory=list)    # 目标公司

    # ── 其他特征 ──
    keywords: list = field(default_factory=list)       # 综合关键词
    forbidden_keywords: list = field(default_factory=list)  # 排除关键词
    responsibility_desc: str = ""                      # 岗位职责描述
    team_info: str = ""                                # 团队信息

    @property
    def has_requirements(self) -> bool:
        """是否有有效的硬性要求"""
        return bool(self.must_skills) or self.min_years > 0


@dataclass
class JDParseResult:
    """
    JD 解析结果（包含人工和 AI 解析的完整结果）
    """
    structured: JDRequirement
    raw_response: str = ""               # AI 解析的原始返回（用于调试）
    parsed_at: str = ""                  # 解析时间
