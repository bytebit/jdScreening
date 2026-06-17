"""
智能分析模块 — 三阶段流水线
============================

Stage 1: 规则引擎      — 毫秒级，零成本，淘汰明显不符合的简历
Stage 2: 向量语义匹配   — 秒级，零 API 成本，用嵌入模型排序
Stage 3: DeepSeek 分析  — 仅对 Top 候选人深度分析，输出结构化评估

使用方式:
    from analyzer.pipeline import ScreeningPipeline

    pipeline = ScreeningPipeline(jd_requirement)
    result = await pipeline.run(resume)
"""

from .stage1_rules import RuleFilter
from .stage2_vector import SemanticMatcher
from .stage3_deepseek import DeepSeekAnalyzer
from .pipeline import ScreeningPipeline

__all__ = ["RuleFilter", "SemanticMatcher", "DeepSeekAnalyzer", "ScreeningPipeline"]
