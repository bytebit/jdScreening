"""
简历解析模块
负责：将 PDF、DOCX、TXT 格式的简历文件解析为纯文本
"""
import logging
from pathlib import Path


class ResumeParserError(Exception):
    """简历解析异常"""
    pass


class ResumeParser:
    """简历解析器 - 支持 PDF / DOCX / TXT"""

    @staticmethod
    def parse(filepath):
        """
        解析简历文件，返回纯文本内容

        参数:
            filepath: 简历文件的完整路径

        返回:
            str: 简历的纯文本内容

        抛出:
            ResumeParserError: 解析失败时
        """
        filepath = str(filepath)
        ext = Path(filepath).suffix.lower()

        if ext == '.pdf':
            return ResumeParser._parse_pdf(filepath)
        elif ext in ('.docx', '.doc'):
            return ResumeParser._parse_docx(filepath)
        elif ext == '.txt':
            return ResumeParser._parse_txt(filepath)
        else:
            raise ResumeParserError(f"不支持的简历格式: {ext}")

    # ------------------------------------------------------------------
    # PDF 解析：使用 PyMuPDF (fitz)
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_pdf(filepath):
        """解析 PDF 简历"""
        try:
            import fitz
        except ImportError:
            raise ResumeParserError(
                "缺少 PyMuPDF 库，请执行: pip install PyMuPDF"
            )

        try:
            doc = fitz.open(filepath)
            text_parts = []

            for page_num, page in enumerate(doc, 1):
                page_text = page.get_text()
                if page_text.strip():
                    text_parts.append(page_text.strip())

            doc.close()

            if not text_parts:
                raise ResumeParserError(f"PDF 文件为空或无可提取文本: {filepath}")

            full_text = '\n'.join(text_parts)
            logging.info(f"PDF 解析成功: {Path(filepath).name} ({len(full_text)} 字符)")
            return full_text

        except fitz.FileDataError as e:
            raise ResumeParserError(f"PDF 文件损坏: {e}")
        except Exception as e:
            raise ResumeParserError(f"PDF 解析失败: {e}")

    # ------------------------------------------------------------------
    # DOCX 解析：使用 python-docx
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_docx(filepath):
        """解析 DOCX 简历"""
        try:
            import docx
        except ImportError:
            raise ResumeParserError(
                "缺少 python-docx 库，请执行: pip install python-docx"
            )

        try:
            doc = docx.Document(filepath)
            text_parts = []

            for para in doc.paragraphs:
                text = para.text.strip()
                if text:
                    text_parts.append(text)

            if not text_parts:
                raise ResumeParserError(f"DOCX 文件为空或无可提取文本: {filepath}")

            full_text = '\n'.join(text_parts)
            logging.info(f"DOCX 解析成功: {Path(filepath).name} ({len(full_text)} 字符)")
            return full_text

        except Exception as e:
            raise ResumeParserError(f"DOCX 解析失败: {e}")

    # ------------------------------------------------------------------
    # TXT 解析
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_txt(filepath):
        """解析纯文本简历"""
        try:
            with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                text = f.read().strip()

            if not text:
                raise ResumeParserError(f"TXT 文件为空: {filepath}")

            logging.info(f"TXT 解析成功: {Path(filepath).name} ({len(text)} 字符)")
            return text

        except Exception as e:
            raise ResumeParserError(f"TXT 解析失败: {e}")
