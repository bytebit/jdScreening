"""
数据模型
所有核心数据结构定义，确保上下游与存储格式一致。
"""

from .resume import Resume, WorkExperience, Education
from .jd import JDRequirement, JDParseResult
from .result import AnalysisResult, Stage1Result, Stage2Result, Stage3Result

__all__ = [
    "Resume", "WorkExperience", "Education",
    "JDRequirement", "JDParseResult",
    "AnalysisResult", "Stage1Result", "Stage2Result", "Stage3Result",
]
