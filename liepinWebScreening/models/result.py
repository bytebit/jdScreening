"""
分析结果数据模型
每个阶段的输出以及最终的汇总结果。
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Stage1Result:
    """第一阶段：规则引擎结果"""
    passed: bool = False
    checks: list[dict] = field(default_factory=list)  # [{"item": "学历", "passed": True, "note": "..."}, ...]
    reject_reason: str = ""


@dataclass
class Stage2Result:
    """第二阶段：向量语义匹配结果"""
    passed: bool = False
    similarity_score: float = 0.0
    rank_in_batch: int = 0


@dataclass
class Stage3Result:
    """第三阶段：DeepSeek 深度分析结果"""
    # 原始打分
    overall_score: float = 0.0
    level: str = "D"                     # S/A/B/C/D

    # 硬性条件核对
    basic_qualification: dict = field(default_factory=dict)

    # 技能匹配
    skill_match: dict = field(default_factory=dict)

    # 经验相关性
    experience_relevance: dict = field(default_factory=dict)

    # 综合结论
    recommendation: str = ""             # 建议面试 / 待定 / 不推荐
    summary: str = ""
    strengths: list = field(default_factory=list)
    concerns: list = field(default_factory=list)
    interview_focus: list = field(default_factory=list)

    # 原始 LLM 输出（用于调试）
    raw_response: str = ""

    # 各维度详细评分
    details: dict = field(default_factory=dict)


@dataclass
class AnalysisResult:
    """
    一份简历的完整分析结果

    包含三个阶段的全量信息，最终持久化到存储中。
    """
    # ── 关联信息 ──
    resume_id: str = ""
    job_id: str = ""
    candidate_name: str = ""

    # ── 各阶段结果 ──
    stage1: Stage1Result = field(default_factory=Stage1Result)
    stage2: Stage2Result = field(default_factory=Stage2Result)
    stage3: Stage3Result = field(default_factory=Stage3Result)

    # ── 综合结论 ──
    final_score: float = 0.0
    final_level: str = "D"
    final_recommendation: str = "不推荐"
    final_summary: str = ""

    # ── HR 反馈（后续由 HR 填写） ──
    hr_decision: Optional[str] = None    # 邀面试 / 不合适 / 未处理
    hr_decision_time: Optional[str] = None
    hr_notes: str = ""

    # ── 元信息 ──
    analyzed_at: str = ""
    processing_time_ms: float = 0

    @property
    def passed_all_stages(self) -> bool:
        """是否通过了所有阶段"""
        return self.stage1.passed and self.stage2.passed

    def to_export_dict(self) -> dict:
        """导出为扁平字典（用于 Excel 报告）"""
        return {
            "姓名": self.candidate_name,
            "简历ID": self.resume_id,
            "综合评分": self.final_score,
            "等级": self.final_level,
            "推荐决策": self.final_recommendation,
            "摘要": self.final_summary,
            "规则筛选": "通过" if self.stage1.passed else f"淘汰({self.stage1.reject_reason})",
            "语义匹配分": round(self.stage2.similarity_score, 4),
            "DeepSeek评分": self.stage3.overall_score,
            "优势": "; ".join(self.stage3.strengths),
            "风险": "; ".join(self.stage3.concerns),
            "面试重点": "; ".join(self.stage3.interview_focus),
            "HR决策": self.hr_decision or "待处理",
            "分析时间": self.analyzed_at,
        }
