"""
JSON 文件存储
==============
初版使用 JSON 文件持久化，无需数据库。
后续可以无缝切换到 SQLite / MySQL。

存储结构:
  data/
  ├── jd/              # JD 信息缓存
  ├── resumes/         # 简历缓存
  ├── results/         # 分析结果
  └── sessions/        # 任务运行记录
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config as cfg
from models import Resume, JDRequirement, AnalysisResult


class JSONStorage:
    """
    基于 JSON 文件的持久化存储

    Example:
        store = JSONStorage()
        store.save_jd(jd)
        store.save_resume(resume)
        store.save_result(result)
    """

    def __init__(self, base_dir: Optional[str] = None):
        self.base_dir = Path(base_dir or cfg.STORAGE_DIR)
        self._ensure_dirs()

    def _ensure_dirs(self):
        """确保目录结构存在"""
        for sub in ["jd", "resumes", "results", "sessions"]:
            (self.base_dir / sub).mkdir(parents=True, exist_ok=True)

    # ────────────────────────────────────────────────
    # JD 存储
    # ────────────────────────────────────────────────
    def save_jd(self, jd: JDRequirement) -> str:
        """保存 JD 信息"""
        path = self.base_dir / "jd" / f"{jd.jd_id or 'unknown'}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump({
                "jd_id": jd.jd_id,
                "jd_title": jd.jd_title,
                "jd_url": jd.jd_url,
                "min_education": jd.min_education,
                "min_years": jd.min_years,
                "must_skills": jd.must_skills,
                "nice_skills": jd.nice_skills,
                "keywords": jd.keywords,
                "saved_at": datetime.now().isoformat(),
            }, f, ensure_ascii=False, indent=2)
        return str(path)

    def load_jd(self, jd_id: str) -> Optional[JDRequirement]:
        """加载 JD 信息"""
        path = self.base_dir / "jd" / f"{jd_id}.json"
        if not path.exists():
            return None
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return JDRequirement(**data)

    # ────────────────────────────────────────────────
    # 简历存储
    # ────────────────────────────────────────────────
    def save_resume(self, resume: Resume) -> str:
        """保存简历到本地缓存（简历ID做文件名）

        相同 ID 的简历直接覆盖旧文件，不产生副本。
        """
        save_dir = self.base_dir / "resumes" / resume.platform
        save_dir.mkdir(parents=True, exist_ok=True)

        path = save_dir / f"{resume.id}.json"

        data = {
            "id": resume.id,
            "platform_id": resume.platform_id,
            "platform": resume.platform,
            "source_url": resume.source_url,
            "name": resume.name,
            "education_level": resume.education_level,
            "years_of_experience": resume.years_of_experience,
            "skills": resume.skills,
            "raw_text": resume.raw_text,
            "collected_at": resume.collected_at,
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
        return str(path)

    def load_resume(self, resume_id: str) -> Optional[Resume]:
        """从缓存加载简历"""
        # 搜索所有子目录
        for path in self.base_dir.glob(f"resumes/**/{resume_id}.json"):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return Resume(**data)
        return None

    # ────────────────────────────────────────────────
    # 分析结果存储
    # ────────────────────────────────────────────────
    def save_result(self, result: AnalysisResult, job_id: str) -> str:
        """保存分析结果"""
        date_str = datetime.now().strftime("%Y%m%d")
        save_dir = self.base_dir / "results" / job_id / date_str
        save_dir.mkdir(parents=True, exist_ok=True)

        path = save_dir / f"{result.resume_id}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump({
                "resume_id": result.resume_id,
                "job_id": result.job_id,
                "candidate_name": result.candidate_name,
                "final_score": result.final_score,
                "final_level": result.final_level,
                "final_recommendation": result.final_recommendation,
                "final_summary": result.final_summary,
                "stage1": {
                    "passed": result.stage1.passed,
                    "checks": result.stage1.checks,
                    "reject_reason": result.stage1.reject_reason,
                },
                "stage2": {
                    "passed": result.stage2.passed,
                    "similarity_score": result.stage2.similarity_score,
                    "rank_in_batch": result.stage2.rank_in_batch,
                },
                "stage3": {
                    "overall_score": result.stage3.overall_score,
                    "level": result.stage3.level,
                    "recommendation": result.stage3.recommendation,
                    "summary": result.stage3.summary,
                    "strengths": result.stage3.strengths,
                    "concerns": result.stage3.concerns,
                    "interview_focus": result.stage3.interview_focus,
                    "details": result.stage3.details,
                },
                "hr_decision": result.hr_decision,
                "hr_notes": result.hr_notes,
                "analyzed_at": result.analyzed_at,
            }, f, ensure_ascii=False, indent=2)
        return str(path)

    def load_results(self, job_id: str) -> list[AnalysisResult]:
        """加载某职位的历史分析结果"""
        date_str = datetime.now().strftime("%Y%m%d")
        path = self.base_dir / "results" / job_id / date_str
        if not path.exists():
            return []

        results = []
        for f in path.glob("*.json"):
            with open(f, "r", encoding="utf-8") as fp:
                data = json.load(fp)
            result = AnalysisResult(
                resume_id=data["resume_id"],
                job_id=data["job_id"],
                candidate_name=data["candidate_name"],
                final_score=data["final_score"],
                final_level=data["final_level"],
                final_recommendation=data["final_recommendation"],
                final_summary=data["final_summary"],
            )
            results.append(result)

        return sorted(results, key=lambda r: r.final_score, reverse=True)

    # ────────────────────────────────────────────────
    # 任务运行记录
    