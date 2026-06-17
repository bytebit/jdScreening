"""
第一阶段：规则引擎 (Stage 1 - Rule Filter)
===========================================
零成本、毫秒级，用硬性规则快速淘汰明显不匹配的简历。

核心逻辑：
  1. 学历要求 - JD 要求本科以上，候选人大专 → 淘汰
  2. 工作经验 - JD 要求 3 年，候选人只有 1 年 → 淘汰
  3. 硬性关键词 - JD 要求"Spring Boot"，简历无提及 → 标记
  4. 排除关键词 - JD 写了"不要培训班"，简历提到"达内" → 标记

设计原则：
  - 规则宁可漏过，不要误杀（让后续阶段处理模糊情况）
  - 所有检查项都有详细注释，方便 HR 理解淘汰理由
"""

import re
from typing import Optional

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config as cfg
from models import Resume, JDRequirement, Stage1Result


class RuleFilter:
    """
    规则过滤器

    Example:
        filter = RuleFilter(jd)
        result = filter.evaluate(resume)
        if result.passed:
            print("通过规则筛选")
        else:
            print(f"淘汰原因: {result.reject_reason}")
    """

    def __init__(self, jd: JDRequirement):
        self.jd = jd
        self.edu_rank = cfg.PIPELINE.education_rank

    # ────────────────────────────────────────────────
    # 主入口
    # ────────────────────────────────────────────────
    def evaluate(self, resume: Resume) -> Stage1Result:
        """
        对一份简历执行所有规则检查

        Args:
            resume: 待检查的简历

        Returns:
            Stage1Result: 包含所有检查项的结果
        """
        result = Stage1Result()
        checks = []
        reject_reasons = []

        # ── 依序执行各项检查 ──
        checks.append(self._check_education(resume))
        checks.append(self._check_experience_years(resume))
        checks.extend(self._check_required_skills(resume))
        checks.extend(self._check_keywords(resume))

        # ── 汇总结果 ──
        result.checks = checks

        failed_checks = [c for c in checks if not c["passed"]]
        if failed_checks:
            result.passed = False
            result.reject_reason = "; ".join(
                c["note"] for c in failed_checks
            )
        else:
            result.passed = True

        return result

    # ────────────────────────────────────────────────
    # 检查项
    # ────────────────────────────────────────────────

    def _check_education(self, resume: Resume) -> dict:
        """
        学历要求检查
        """
        required_level = self.jd.min_education
        actual_level = resume.education_level

        # 如果 JD 没有学历要求，跳过
        if not required_level or required_level in ("不限", "其他", ""):
            return {"item": "学历", "passed": True, "note": "JD 无学历要求，跳过"}

        if not actual_level:
            return {"item": "学历", "passed": False, "note": f"简历中未识别到学历信息"}

        # 比较学历等级
        required_rank = self.edu_rank.get(required_level, 0)
        actual_rank = self.edu_rank.get(actual_level, 0)

        if actual_rank >= required_rank:
            return {
                "item": "学历",
                "passed": True,
                "note": f"符合要求(要求{required_level}，实际{actual_level})",
            }
        else:
            return {
                "item": "学历",
                "passed": False,
                "note": f"学历不达标(要求{required_level}，实际{actual_level})",
                "required": required_level,
                "actual": actual_level,
            }

    def _check_experience_years(self, resume: Resume) -> dict:
        """
        工作年限检查
        """
        required_years = self.jd.min_years
        actual_years = resume.years_of_experience

        if required_years <= 0:
            return {"item": "工作经验", "passed": True, "note": "JD 无年限要求，跳过"}

        if actual_years <= 0:
            return {
                "item": "工作经验",
                "passed": False,
                "note": f"简历中未识别到工作经验",
            }

        if actual_years >= required_years:
            return {
                "item": "工作经验",
                "passed": True,
                "note": f"符合要求(要求{required_years}年，实际{actual_years}年)",
            }
        else:
            # 如果年限差在 1 年以内，算"边缘"，不直接淘汰，让后续阶段判断
            if required_years - actual_years <= 1:
                return {
                    "item": "工作经验",
                    "passed": True,
                    "note": f"边缘(要求{required_years}年，实际{actual_years}年，差距1年内，留待后续判断)",
                    "warning": True,
                }
            return {
                "item": "工作经验",
                "passed": False,
                "note": f"工作年限不足(要求{required_years}年，实际{actual_years}年)",
                "required": required_years,
                "actual": actual_years,
            }

    def _check_required_skills(self, resume: Resume) -> list[dict]:
        """
        必备技能关键词检查

        简历文本全局搜索（包括工作描述中的技能），不局限于 skills 字段。
        """
        results = []
        must_skills = self.jd.must_skills
        if not must_skills:
            return [{"item": "必备技能", "passed": True, "note": "JD 无指定必备技能，跳过"}]

        # 搜索范围：简历全文（小写）
        search_text = resume.raw_text.lower()

        hit_count = 0
        skill_checks = []

        for skill in must_skills:
            skill_lower = skill.lower().strip()
            # 精确匹配（原逻辑）
            pattern = r'(?:^|[\s,，。、；;/\-()（）])' + re.escape(skill_lower) + r'(?:$|[\s,，。、；;/\-()（）])'
            found = bool(re.search(pattern, search_text)) or skill_lower in search_text

            # 如果精确匹配失败且关键词是长短语，提取核心词重新匹配
            # 跳过"工作""经验""能力""技术"等通用词，避免误匹配
            if not found and len(skill) > 4:
                stop_words = {"工作", "经验", "能力", "技术", "水平", "知识", "管理", "相关"}
                # 尝试用 stop words 拆分：取 stop word 前面的部分
                for sw in stop_words:
                    idx = skill_lower.find(sw)
                    if idx > 0:
                        core = skill_lower[:idx].strip()
                        if len(core) >= 2 and core in search_text:
                            found = True
                            break

            if found:
                hit_count += 1

            skill_checks.append({
                "skill": skill,
                "found": found,
            })

        # 计算命中比例
        ratio = hit_count / len(must_skills)
        threshold = cfg.PIPELINE.keyword_hit_ratio

        missing = [s["skill"] for s in skill_checks if not s["found"]]

        if ratio >= 0.8:
            results.append({
                "item": "必备技能",
                "passed": True,
                "note": f"技能匹配良好({hit_count}/{len(must_skills)}命中)",
            })
        elif ratio >= threshold:
            results.append({
                "item": "必备技能",
                "passed": True,
                "warning": True,
                "note": f"部分技能未识别到({hit_count}/{len(must_skills)}命中，缺失: {', '.join(missing)})",
            })
        else:
            results.append({
                "item": "必备技能",
                "passed": False,
                "note": f"必备技能命中率过低({hit_count}/{len(must_skills)}，缺失: {', '.join(missing)})",
            })

        return results

    def _check_keywords(self, resume: Resume) -> list[dict]:
        keywords = self.jd.keywords
        if not keywords:
            return [{"item": "经验关键词", "passed": True, "note": "JD无关键词要求，跳过"}]

        # 如果简历文本很短（卡片摘要，未深度采集），关键词匹配不可靠，直接放行
        if len(resume.raw_text) < 500:
            return [{"item": "经验关键词", "passed": True, "warning": True,
                     "note": "简历为卡片摘要，关键词匹配跳过，留待DeepSeek判断"}]

        search_text = resume.raw_text.lower()
        search_text = resume.raw_text.lower()
        matched = [k for k in keywords if k.lower().strip() and k.lower().strip() in search_text]
        if matched:
            return [{"item": "经验关键词", "passed": True, "note": f"关键词匹配({len(matched)}/{len(keywords)}命中)"}]
        else:
            return [{"item": "经验关键词", "passed": True, "warning": True,
                     "note": "关键词未在简历中直接出现，留待DeepSeek判断"}]

    def batch_evaluate(self, resumes):
        passed_resumes = []
        all_results = []
        for resume in resumes:
            result = self.evaluate(resume)
            all_results.append(result)
            if result.passed:
                passed_resumes.append(resume)
        return passed_resumes, all_results
