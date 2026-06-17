"""
简历数据模型
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class WorkExperience:
    """工作经历"""
    company: str = ""
    position: str = ""
    start_date: str = ""
    end_date: str = ""
    duration_months: int = 0
    description: str = ""


@dataclass
class Education:
    """教育经历"""
    school: str = ""
    degree: str = ""            # 博士/硕士/本科/大专
    major: str = ""
    start_date: str = ""
    end_date: str = ""


@dataclass
class Resume:
    """
    简历统一表示模型

    无论从哪个平台采集、什么格式，最终都映射到这个模型。
    """
    # ── 标识 ──
    id: str = ""                           # 系统内部 ID
    platform_id: str = ""                  # 猎聘平台的简历 ID (geekId/resumeId)
    platform: str = "liepin"               # 来源平台
    source_url: str = ""                   # 原始链接

    # ── 基本信息 ──
    name: str = ""
    gender: str = ""
    age: int = 0
    phone: str = ""
    email: str = ""
    current_location: str = ""
    current_company: str = ""
    current_position: str = ""

    # ── 教育 ──
    education_level: str = ""              # 最高学历: 博士/硕士/本科/大专
    education: list[Education] = field(default_factory=list)

    # ── 工作经历 ──
    years_of_experience: float = 0         # 工作年限
    work_experiences: list[WorkExperience] = field(default_factory=list)

    # ── 技能 ──
    skills: list[str] = field(default_factory=list)

    # ── 原始数据 ──
    raw_text: str = ""                     # 所有文本拼起来，供 AI/向量分析
    raw_json: dict = field(default_factory=dict)  # API 原始返回（用于调试）

    # ── 元信息 ──
    collected_at: str = ""                 # 采集时间

    def build_raw_text(self) -> str:
        """
        将结构化字段拼接为完整文本，供 AI 分析使用
        """
        parts = [f"姓名：{self.name}"]

        if self.education_level:
            parts.append(f"最高学历：{self.education_level}")
        if self.years_of_experience:
            parts.append(f"工作年限：{self.years_of_experience}年")

        if self.current_company:
            parts.append(f"当前公司：{self.current_company}")
        if self.current_position:
            parts.append(f"当前职位：{self.current_position}")

        if self.skills:
            parts.append(f"技能：{'、'.join(self.skills)}")

        if self.work_experiences:
            parts.append("\n【工作经历】")
            for we in self.work_experiences:
                parts.append(
                    f"{we.company} | {we.position} | "
                    f"{we.start_date} ~ {we.end_date}"
                )
                if we.description:
                    parts.append(f"  描述：{we.description}")

        if self.education:
            parts.append("\n【教育经历】")
            for edu in self.education:
                parts.append(
                    f"{edu.school} | {edu.degree} | {edu.major} | "
                    f"{edu.start_date} ~ {edu.end_date}"
                )

        self.raw_text = "\n".join(parts)
        return self.raw_text
