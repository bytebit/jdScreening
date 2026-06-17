"""
筛选流水线编排器 (Screening Pipeline)
=======================================
将三个阶段串联为完整的分析流水线。

职责：
  1. 维护流水线的执行顺序
  2. 在前一阶段淘汰简历，减少后续阶段不必要的计算
  3. 汇总所有阶段的输出到统一的 AnalysisResult
  4. 提供进度回调

数据流：
  Resume → Stage1(规则) → 通过的 → Stage2(向量) → 排序后 Top-K → Stage3(DeepSeek) → 完整报告
             淘汰 ❌                         淘汰 ❌
"""

import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config as cfg
from models import (
    Resume, JDRequirement,
    AnalysisResult, Stage1Result, Stage2Result, Stage3Result,
)
from .stage1_rules import RuleFilter
from .stage2_vector import SemanticMatcher
from .stage3_deepseek import DeepSeekAnalyzer


class ScreeningPipeline:
    """
    简历筛选流水线

    Example:
        pipeline = ScreeningPipeline(jd)
        results = await pipeline.run_all(resumes)

        for r in results:
            print(f"{r.candidate_name}: {r.final_level} - {r.final_recommendation}")
    """

    def __init__(
        self,
        jd: JDRequirement,
        progress_callback: Optional[Callable] = None,
    ):
        """
        Args:
            jd: 结构化的 JD 要求
            progress_callback: fn(current, total, stage_name, message)
        """
        self.jd = jd
        self.progress_callback = progress_callback

    # ────────────────────────────────────────────────
    # 主入口
    # ────────────────────────────────────────────────
    async def run_all(self, resumes: list[Resume]) -> list[AnalysisResult]:
        """
        对一批简历执行完整的三阶段分析

        Args:
            resumes: 待分析的简历列表

        Returns:
            所有简历的完整分析结果
        """
        total = len(resumes)
        print(f"\n{'='*60}")
        print(f"  开始筛选流水线: {total} 份简历")
        print(f"  岗位: {self.jd.jd_title or self.jd.jd_id}")
        print(f"{'='*60}\n")

        # ── Stage 1: 规则引擎 ──
        stage1_passed, stage1_results = self._run_stage1(resumes)
        print()

        # 映射 stage1 结果
        results_map = {
            r.resume_id: r for r in
            self._init_results(resumes, stage1_results)
        }

        # ── Stage 2: 向量语义匹配 ──
        stage2_passed, stage2_scores = self._run_stage2(
            stage1_passed, results_map
        )
        print()

        # ── Stage 3: DeepSeek 深度分析 ──
        stage3_input = stage2_passed if cfg.PIPELINE.enable_stage2 else [(r, 0) for r in stage1_passed]
        if cfg.PIPELINE.enable_stage3 and stage3_input:
            self._run_stage3(stage3_input, results_map)
        else:
            print("🔇 第三阶段已关闭或无简历进入")

        # ── 汇总最终结果 ──
        final_results = self._finalize_results(results_map, list(resumes))
        print(f"\n{'='*60}")
        print(f"  ✅ 筛选完成!")
        self._print_summary(final_results)
        print(f"{'='*60}\n")

        return final_results

    # ────────────────────────────────────────────────
    # Stage 1: 规则引擎
    # ────────────────────────────────────────────────
    def _run_stage1(
        self, resumes: list[Resume]
    ) -> tuple[list[Resume], dict[str, Stage1Result]]:
        """执行规则过滤"""
        self._progress("第一阶段", "规则引擎", 0, len(resumes))

        if not cfg.PIPELINE.enable_stage1:
            print("⏭️  第一阶段已关闭")
            return resumes, {r.id: Stage1Result(passed=True) for r in resumes}

        filter_engine = RuleFilter(self.jd)
        passed, all_results = filter_engine.batch_evaluate(resumes)

        # 构建 ID 映射
        results_map = {}
        for resume, result in zip(resumes, all_results):
            results_map[resume.id] = result

        rejected = total = len(resumes) - len(passed)
        if rejected > 0:
            print(f"  ⏭️  淘汰: {rejected} 份:")
            for resume, result in zip(resumes, all_results):
                if not result.passed:
                    name = resume.name or resume.id
                    print(f"     - {name}: {result.reject_reason}")

        self._progress("第一阶段", "规则引擎", len(resumes), len(resumes))
        return passed, results_map

    # ────────────────────────────────────────────────
    # Stage 2: 向量语义匹配
    # ────────────────────────────────────────────────
    def _run_stage2(
        self, resumes: list[Resume],
        results_map: dict[str, AnalysisResult],
    ) -> tuple[list[tuple[Resume, float]], dict[str, float]]:
        """执行语义匹配"""
        self._progress("第二阶段", "向量语义匹配", 0, len(resumes))

        if not cfg.PIPELINE.enable_stage2 or not resumes:
            return [], {}

        matcher = SemanticMatcher()
        try:
            matcher.encode_jd(self.jd)
            matched = matcher.batch_match(
                resumes,
                threshold=cfg.PIPELINE.similarity_threshold,
                top_k=cfg.PIPELINE.stage2_top_k,
            )

            # 更新 stage2 结果
            scores_map = {}
            passed = []
            for resume, score, s2_result in matched:
                results_map[resume.id].stage2 = s2_result
                results_map[resume.id].stage2.similarity_score = score
                scores_map[resume.id] = score
                if s2_result.passed:
                    passed.append((resume, score))

            self._progress("第二阶段", "向量语义匹配", len(resumes), len(resumes))
            return passed, scores_map

        except ImportError:
            print("⚠️  fastembed 未安装，跳过第二阶段")
            return [(r, 0.5) for r in resumes], {}
        except Exception as e:
            print(f"⚠️  第二阶段执行异常: {e}")
            return [(r, 0.5) for r in resumes], {}

    # ────────────────────────────────────────────────
    # Stage 3: DeepSeek 深度分析
    # ────────────────────────────────────────────────
    def _run_stage3(
        self,
        candidates: list[tuple[Resume, float]],
        results_map: dict[str, AnalysisResult],
    ):
        """执行 DeepSeek 深度分析"""
        total = len(candidates)
        self._progress("第三阶段", "DeepSeek 深度分析", 0, total)

        if not candidates:
            return

        analyzer = DeepSeekAnalyzer()

        def callback(current, total, name):
            self._progress("第三阶段", "DeepSeek 深度分析", current, total, name)

        stage3_results = analyzer.batch_analyze(
            self.jd, candidates,
            progress_callback=callback,
        )

        # 更新 stage3 结果
        for resume, stage2_score, s3_result in stage3_results:
            results_map[resume.id].stage3 = s3_result

        self._progress("第三阶段", "DeepSeek 深度分析", total, total)

    # ────────────────────────────────────────────────
    # 汇总
    # ────────────────────────────────────────────────
    def _init_results(
        self, resumes: list[Resume],
        stage1_results: dict[str, Stage1Result],
    ) -> list[AnalysisResult]:
        """初始化 AnalysisResult"""
        results = []
        for resume in resumes:
            result = AnalysisResult(
                resume_id=resume.id,
                candidate_name=resume.name or resume.id,
                stage1=stage1_results.get(resume.id, Stage1Result()),
            )
            results.append(result)
        return results

    def _finalize_results(
        self,
        results_map: dict[str, AnalysisResult],
        all_resumes: list[Resume],
    ) -> list[AnalysisResult]:
        """汇总最终评分"""
        now = datetime.now().isoformat()

        for resume in all_resumes:
            result = results_map.get(resume.id)
            if not result:
                continue

            result.analyzed_at = now

            # 最终分数：如果有 DeepSeek 评分就用它，否则用语义匹配分
            if result.stage3.overall_score > 0:
                result.final_score = result.stage3.overall_score
                result.final_level = result.stage3.level
                result.final_recommendation = result.stage3.recommendation
                result.final_summary = result.stage3.summary
            elif result.stage2.similarity_score > 0:
                # 只有 Stage2 分数的情况（DeepSeek 没跑）
                score = result.stage2.similarity_score * 100
                result.final_score = round(score, 1)
                result.final_level = "B" if score >= 45 else "C"
                result.final_recommendation = (
                    "待定" if score >= 45 else "不推荐"
                )
                result.final_summary = (
                    f"语义匹配度 {result.stage2.similarity_score:.2%}"
                )
            else:
                # 仅 Stage1 就淘汰了
                result.final_level = "D"
                result.final_recommendation = "不推荐"
                result.final_summary = result.stage1.reject_reason

        # 按评分排序
        sorted_results = sorted(
            [r for r in results_map.values()],
            key=lambda x: x.final_score,
            reverse=True,
        )
        return sorted_results

    # ────────────────────────────────────────────────
    # 汇总打印
    # ────────────────────────────────────────────────
    def _print_summary(self, results: list[AnalysisResult]):
        """打印结果汇总"""
        levels = {"S": 0, "A": 0, "B": 0, "C": 0, "D": 0}
        for r in results:
            levels[r.final_level] = levels.get(r.final_level, 0) + 1

        print(f"  S 级 (强烈推荐): {levels['S']} 人")
        print(f"  A 级 (建议面试): {levels['A']} 人")
        print(f"  B 级 (待定):     {levels['B']} 人")
        print(f"  C 级 (不推荐):   {levels['C']} 人")
        print(f"  D 级 (淘汰):     {levels['D']} 人")

        # 打印前 5 名
        top5 = [r for r in results if r.final_level in ("S", "A")][:5]
        if top5:
            print(f"\n  🏆 Top 推荐:")
            for r in top5:
                print(f"    {r.candidate_name}: {r.final_score}分({r.final_level}) - {r.final_summary}")

    # ────────────────────────────────────────────────
    # 进度回调
    # ────────────────────────────────────────────────
    def _progress(self, stage, action, current, total, message=""):
        """触发进度回调"""
        if self.progress_callback:
            self.progress_callback(current, total, stage, message or action)
