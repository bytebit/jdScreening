"""
第三阶段：DeepSeek 深度分析 (Stage 3 - DeepSeek Analysis)
==========================================================
核心能力：
  1. 深度理解 JD 与简历的语义匹配（超越关键词）
  2. 识别隐性要求（"团队协作"、"抗压能力"等软素质）
  3. 输出结构化评估 + 面试建议

设计原则：
  - 严格控制温度 (0.1) 保证评分一致性
  - Prompt 要求逐项核对，减少幻觉
  - 强制 JSON 输出，方便下游处理
  - 低质量/高成本权衡：只有通过前两阶段的简历才走到这里
"""

import json
import sys
import time
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

from openai import OpenAI

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config as cfg
from models import Resume, JDRequirement, Stage3Result


# ────────────────────────────────────────────────
# DeepSeek Prompt 模板
# ────────────────────────────────────────────────
SYSTEM_PROMPT = """你是一位资深招聘专家。你对国内互联网/科技行业的岗位要求有深刻理解，擅长评估候选人简历与岗位的匹配度。

你的评估原则：
1. 严格基于简历中出现的实际信息，不要脑补、不要推测
2. 区分"硬性条件不满足"和"简历未明确提及"两种情况
3. 对候选人的技能深度做合理推断（如"精通"vs"了解"）
4. 关注职业发展轨迹是否合理（跳槽频率、职位晋升等）
5. 输出 JSON 格式，不要有任何额外内容"""

USER_PROMPT_TEMPLATE = """
请根据以下「岗位描述」和「候选人简历」，进行专业、细致的匹配度评估。

===== 岗位描述 =====
{JD_TEXT}

===== 候选人简历 =====
{RESUME_TEXT}

===== 评估要求 =====
请严格按照以下 JSON 格式输出（不要包含任何额外说明）：

{{
  "basic_qualification": {{
    "years_of_experience": {{ "required": "最低年限要求", "actual": "简历中的实际年限", "matched": true/false, "note": "说明" }},
    "education": {{ "required": "学历要求", "actual": "实际学历", "matched": true/false, "note": "说明" }},
    "major": {{ "required": "专业要求(如无则写'不限')", "actual": "实际专业", "matched": true/false, "note": "说明" }}
  }},
  "skill_match": {{
    "matched_skills": ["与JD要求匹配的技能列表"],
    "partially_matched_skills": ["部分匹配或相关但不够的技能"],
    "missing_skills": ["JD要求但简历中未发现的技能"],
    "skill_depth_note": "对核心技能掌握深度的评估",
    "skill_transferability_note": "技能是否可迁移至目标岗位"
  }},
  "experience_relevance": {{
    "industry_match": {{ "score": 0-10, "note": "行业背景匹配度" }},
    "project_relevance": {{ "score": 0-10, "note": "项目经验相关性" }},
    "career_progression": {{ "score": 0-10, "note": "职业发展轨迹评估" }},
    "company_level": {{ "score": 0-10, "note": "公司背景评估" }},
    "team_management": {{ "score": 0-10, "note": "团队管理经验(如需要)" }}
  }},
  "hidden_signals": {{
    "stability_risk": {{ "score": 0-10, "note": "稳定性风险评估，10=非常稳定", "details": ["如: 每段工作不到1年"] }},
    "career_motivation": "候选人的职业动机分析",
    "red_flags": ["危险信号列表，如频繁跳槽、空白期等"],
    "green_flags": ["加分信号，如大厂经历、创业经验等"]
  }},
  "overall": {{
    "score": 0-100,
    "level": "S/A/B/C/D",
    "summary": "用一句话总结匹配情况",
    "strengths": ["候选人的核心优势"],
    "concerns": ["需要关注的潜在风险"],
    "interview_recommendation": "建议面试 / 待定 / 不推荐",
    "interview_focus": ["面试中应重点考察的方面"],
    "suggested_questions": ["向候选人提出的具体面试问题"]
  }}
}}

评分标准：
- S (90-100)：高度匹配，明显超出预期（经验+技能+背景全面符合）
- A (75-89)：核心要求满足，部分加分项可培养，建议面试
- B (60-74)：基本满足硬性条件，但有明显短板，可待定
- C (40-59)：硬性条件部分不满足，不建议面试
- D (0-39)：完全不匹配

关键提示：
- "matched_skills" 和 "missing_skills" 要区分清楚，不要混淆
- 工作年限不足但有相关项目经验 → 应在经验相关性中体现，不是直接判不匹配
- 注意简历中有没有明显的造假信号（时间重叠、夸大学历等）
- 面试建议题要具体，不要问"你为什么适合这个岗位"这种泛泛问题
"""


class DeepSeekAnalyzer:
    """
    DeepSeek 深度分析器

    用法:
        analyzer = DeepSeekAnalyzer()
        result = analyzer.analyze(jd, resume)
        print(f"评分: {result.overall_score}, 推荐: {result.recommendation}")
    """

    def __init__(self, api_key: Optional[str] = None):
        self.client = OpenAI(
            api_key=api_key or cfg.DEEPSEEK_API_KEY,
            base_url=cfg.DEEPSEEK_BASE_URL,
        )
        self.model = cfg.DEEPSEEK_MODEL
        self.temperature = cfg.DEEPSEEK_TEMPERATURE
        self.max_tokens = cfg.DEEPSEEK_MAX_TOKENS
        self._rate_limiter = threading.Semaphore(cfg.DEEPSEEK_RATE_LIMIT)
        self._last_request_time = 0

    # ────────────────────────────────────────────────
    # 单份分析
    # ────────────────────────────────────────────────
    def analyze(self, jd: JDRequirement, resume: Resume) -> Stage3Result:
        """
        对一份简历进行 DeepSeek 深度分析

        Args:
            jd: 结构化的 JD 要求
            resume: 简历对象

        Returns:
            Stage3Result: 结构化评估结果
        """
        # 构建 prompt
        jd_text = self._build_jd_text(jd)
        resume_text = resume.raw_text or resume.build_raw_text()

        prompt = USER_PROMPT_TEMPLATE.format(
            JD_TEXT=jd_text,
            RESUME_TEXT=resume_text,
        )

        # 限流
        with self._rate_limiter:
            self._apply_rate_limit()

            try:
                start_time = time.time()
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                    response_format={"type": "json_object"},
                )
                elapsed = time.time() - start_time

                content = response.choices[0].message.content

                # 解析 JSON
                parsed = json.loads(content)

                # 映射到 Stage3Result
                result = self._parse_response(parsed)
                result.raw_response = content

                # 计算使用量
                usage = response.usage
                if usage:
                    print(f"  📊 DeepSeek tokens: 输入={usage.prompt_tokens} 输出={usage.completion_tokens} "
                          f"耗时={elapsed:.1f}s")

                return result

            except json.JSONDecodeError as e:
                print(f"❌ DeepSeek 返回 JSON 解析失败: {e}")
                return Stage3Result(
                    overall_score=0,
                    level="D",
                    recommendation="分析失败",
                    summary=f"JSON 解析错误: {e}",
                    raw_response=content if 'content' in dir() else "",
                )
            except Exception as e:
                print(f"❌ DeepSeek API 调用失败: {e}")
                return Stage3Result(
                    overall_score=0,
                    level="D",
                    recommendation="分析失败",
                    summary=f"API 调用失败: {e}",
                )

    # ────────────────────────────────────────────────
    # 重试机制的批量分析
    # ────────────────────────────────────────────────
    def analyze_with_retry(self, jd: JDRequirement, resume: Resume) -> Stage3Result:
        """
        带重试机制的分析
        """
        max_retries = cfg.DEEPSEEK_RETRY_TIMES
        for attempt in range(1, max_retries + 1):
            try:
                return self.analyze(jd, resume)
            except Exception as e:
                if attempt < max_retries:
                    wait = 2 ** attempt
                    print(f"⚠️  第 {attempt} 次失败({e})，{wait}s 后重试...")
                    time.sleep(wait)
                else:
                    print(f"❌ 重试 {max_retries} 次后仍然失败")
                    return Stage3Result(
                        overall_score=0,
                        level="D",
                        recommendation="分析失败",
                        summary=f"重试 {max_retries} 次后失败: {e}",
                    )

    # ────────────────────────────────────────────────
    # 批量分析
    # ────────────────────────────────────────────────
    def batch_analyze(
        self,
        jd: JDRequirement,
        resumes: list[tuple[Resume, float]],  # (resume, stage2_score)
        progress_callback=None,
    ) -> list[tuple[Resume, float, Stage3Result]]:
        """
        批量分析（串行，带限流）

        Args:
            jd: JD 要求
            resumes: [(简历, 阶段2相似度), ...]
            progress_callback: fn(current, total, resume_name)

        Returns:
            [(resume, stage2_score, stage3_result), ...]
        """
        results = []
        total = len(resumes)

        for i, (resume, stage2_score) in enumerate(resumes, 1):
            name = resume.name or resume.id
            print(f"\n  🔍 [{i}/{total}] 分析: {name}")

            if progress_callback:
                progress_callback(i, total, name)

            result = self.analyze_with_retry(jd, resume)
            results.append((resume, stage2_score, result))

        return results

    # ────────────────────────────────────────────────
    # 辅助方法
    # ────────────────────────────────────────────────

    def _build_jd_text(self, jd: JDRequirement) -> str:
        """构建用于分析的 JD 文本"""
        parts = []
        if jd.jd_title:
            parts.append(f"职位名称：{jd.jd_title}")
        if jd.min_education and jd.min_education != "不限":
            parts.append(f"学历要求：{jd.min_education}")
        if jd.min_years > 0:
            parts.append(f"工作经验：{jd.min_years}年以上")
        if jd.must_skills:
            parts.append(f"必备技能：{'、'.join(jd.must_skills)}")
        if jd.nice_skills:
            parts.append(f"加分技能：{'、'.join(jd.nice_skills)}")
        if jd.preferred_industries:
            parts.append(f"优先行业：{'、'.join(jd.preferred_industries)}")
        if jd.responsibility_desc:
            parts.append(f"岗位职责：{jd.responsibility_desc}")
        if jd.jd_text:
            parts.append(f"\n完整描述：\n{jd.jd_text}")

        return "\n".join(parts)

    def _apply_rate_limit(self):
        """请求限流，确保不超过每分钟限制"""
        elapsed = time.time() - self._last_request_time
        min_interval = 60.0 / cfg.DEEPSEEK_RATE_LIMIT
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        self._last_request_time = time.time()

    def _parse_response(self, parsed: dict) -> Stage3Result:
        """将 DeepSeek 返回的 JSON 映射到 Stage3Result"""
        overall = parsed.get("overall", {})

        result = Stage3Result(
            overall_score=overall.get("score", 0),
            level=overall.get("level", "D"),
            recommendation=overall.get("interview_recommendation", "不推荐"),
            summary=overall.get("summary", ""),
            strengths=overall.get("strengths", []),
            concerns=overall.get("concerns", []),
            interview_focus=overall.get("interview_focus", []),
            basic_qualification=parsed.get("basic_qualification", {}),
            skill_match=parsed.get("skill_match", {}),
            experience_relevance=parsed.get("experience_relevance", {}),
            details={
                "hidden_signals": parsed.get("hidden_signals", {}),
                "suggested_questions": overall.get("suggested_questions", []),
            },
        )

        return result
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                