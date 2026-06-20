"""
第二阶段：向量语义匹配 (Stage 2 - Semantic Matching)
=====================================================
用嵌入模型将 JD 和简历转为向量，通过余弦相似度衡量文本层面的匹配程度。

核心流程：
  1. 将 JD 全文编码为向量
  2. 将每份简历全文编码为向量
  3. 计算余弦相似度
  4. 按相似度排序，淘汰低于阈值的简历

模型选择 (fastembed):
  - "BAAI/bge-base-zh-v1.5"  (推荐，~400MB，专为中文优化)
  - "BAAI/bge-m3"            (质量最高，~2.2GB，支持多语言)

成本：零 API 调用费，本地 CPU/GPU 运行。
"""

import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config as cfg
from models import Resume, JDRequirement, Stage2Result


class SemanticMatcher:
    """
    语义匹配器

    Example:
        matcher = SemanticMatcher()
        matcher.encode_jd(jd_text)
        result = matcher.match(resume)
    """

    def __init__(self, model_name: Optional[str] = None):
        """
        Args:
            model_name: fastembed 支持的模型名称
                        None 则使用配置中的默认模型
        """
        self.model_name = model_name or cfg.PIPELINE.embedding_model
        self._model = None
        self._jd_embedding = None

    # ────────────────────────────────────────────────
    # 模型懒加载
    # ────────────────────────────────────────────────
    @property
    def model(self):
        """Embedding 模型（懒加载）"""
        if self._model is None:
            print(f"🧠 加载嵌入模型: {self.model_name}")
            try:
                from fastembed import TextEmbedding
                self._model = TextEmbedding(
                    model_name=self.model_name,
                    max_length=512,
                )
                print(f"✅ 模型加载完成")
            except ImportError:
                print("❌ 需要安装 fastembed: pip install fastembed")
                raise
            except Exception as e:
                print(f"❌ 模型加载失败: {e}")
                raise
        return self._model

    # ────────────────────────────────────────────────
    # JD 编码
    # ────────────────────────────────────────────────
    def encode_jd(self, jd: JDRequirement):
        """
        对 JD 进行编码，后续匹配时复用

        Args:
            jd: 结构化的 JD 要求
        """
        # 构建待编码文本：JD 的核心部分
        text = self._build_jd_text(jd)
        # fastembed 返回的是生成器，取第一个
        embeddings = list(self.model.embed([text]))
        self._jd_embedding = embeddings[0]

    def _build_jd_text(self, jd: JDRequirement) -> str:
        """构建 JD 的核心文本（用于编码）"""
        parts = [f"职位：{jd.jd_title}"]

        if jd.responsibility_desc:
            parts.append(f"职责：{jd.responsibility_desc}")
        if jd.must_skills:
            parts.append(f"必备技能：{' '.join(jd.must_skills)}")
        if jd.nice_skills:
            parts.append(f"加分技能：{' '.join(jd.nice_skills)}")
        if jd.preferred_industries:
            parts.append(f"行业：{' '.join(jd.preferred_industries)}")
        if jd.team_info:
            parts.append(f"团队：{jd.team_info}")
        if jd.jd_text:
            parts.append(jd.jd_text)

        return "\n".join(parts)

    # ────────────────────────────────────────────────
    # 单份简历匹配
    # ────────────────────────────────────────────────
    def match(self, resume: Resume) -> float:
        """
        计算某份简历与 JD 的语义相似度

        Args:
            resume: 简历对象

        Returns:
            余弦相似度分数 (0~1)
        """
        if self._jd_embedding is None:
            raise ValueError("请先调用 encode_jd() 编码 JD")

        resume_text = self._build_resume_text(resume)
        embeddings = list(self.model.embed([resume_text]))
        resume_embedding = embeddings[0]

        # 余弦相似度
        similarity = self._cosine_similarity(self._jd_embedding, resume_embedding)
        return similarity

    def _build_resume_text(self, resume: Resume) -> str:
        """构建简历文本（优先用 raw_text）"""
        if resume.raw_text:
            return resume.raw_text
        return resume.build_raw_text()

    # ────────────────────────────────────────────────
    # 批量匹配
    # ────────────────────────────────────────────────
    def batch_match(
        self,
        resumes: list[Resume],
        threshold: Optional[float] = None,
        top_k: Optional[int] = None,
    ) -> list[tuple[Resume, float, Stage2Result]]:
        """
        批量匹配并排序

        Args:
            resumes: 待匹配的简历列表
            threshold: 相似度阈值，低于此值标记为不通过
            top_k: 如果设置，只取前 K 份

        Returns:
            [(resume, score, result), ...] 按分数降序排列
        """
        if self._jd_embedding is None:
            raise ValueError("请先调用 encode_jd() 编码 JD")

        threshold = threshold if threshold is not None else cfg.PIPELINE.similarity_threshold
        top_k = top_k if top_k is not None else cfg.PIPELINE.stage2_top_k

        # 批量编码简历
        resume_texts = [
            resume.raw_text or resume.build_raw_text()
            for resume in resumes
        ]

        if not resume_texts:
            return []

        print(f"🧠 批量编码 {len(resume_texts)} 份简历...")
        resume_embeddings = list(self.model.embed(resume_texts))

        # 计算所有相似度
        results = []
        for resume, emb in zip(resumes, resume_embeddings):
            score = self._cosine_similarity(self._jd_embedding, emb)

            result = Stage2Result(
                similarity_score=round(score, 4),
                passed=score >= threshold,
            )
            results.append((resume, score, result))

        # 按分数降序排列
        results.sort(key=lambda x: x[1], reverse=True)

        # 标记排名
        for rank, (_, _, result) in enumerate(results, 1):
            result.rank_in_batch = rank

        # 应用 Top-K
        if top_k and len(results) > top_k:
            results = results[:top_k]
            # Top-K 之外的全部标记为不通过
            for _, _, result in results:
                result.passed = True

        passed = [r for r in results if r[2].passed]
        print(f"📊 语义匹配: {len(passed)}/{len(results)} 通过阈值({threshold})")

        if results:
            print(f"  最高分: {results[0][1]:.4f}  最低分: {results[-1][1]:.4f}")

        return results

    # ────────────────────────────────────────────────
    # 工具方法
    # ────────────────────────────────────────────────
    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        """计算余弦相似度"""
        import math
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)
