"""
AI 智能匹配模块
负责：调用 DeepSeek API 对简历进行匹配评估，输出三分类结果
"""
import json
import logging
import os
import time

import requests


class AIAnalyzerError(Exception):
    """AI 分析异常"""
    pass


class AIAnalyzer:
    """AI 评估器 - 调用 DeepSeek API 进行简历-JD 匹配分析"""

    def __init__(self, config):
        self.config = config['deepseek']
        self.resume_config = config['resume']
        self.api_key = self._resolve_api_key()
        self.api_url = self.config['api_url']
        self.model = self.config['model']
        self.temperature = self.config['temperature']
        self.max_tokens = self.config['max_tokens']
        self.max_text_length = self.resume_config['max_text_length']

    def _resolve_api_key(self):
        """解析 API Key：优先从环境变量读取"""
        key = self.config['api_key']
        if key.startswith('${') and key.endswith('}'):
            env_var = key[2:-1]
            key = os.environ.get(env_var, '')
            if not key:
                raise AIAnalyzerError(
                    f"DeepSeek API Key 未设置！\n"
                    f"请执行: export {env_var}='sk-你的key'"
                )
        return key

    # ------------------------------------------------------------------
    # 核心评估方法
    # ------------------------------------------------------------------

    def evaluate(self, jd_text, resume_text, max_retries=2):
        """
        评估简历与 JD 的匹配程度

        参数:
            jd_text: 岗位描述文本
            resume_text: 简历文本
            max_retries: API 调用失败时的最大重试次数

        返回:
            dict: {
                "decision": "通过" | "待定" | "不通过",
                "reason": "判断理由",
                "matched_requirements": ["匹配项1", ...],
                "unmatched_requirements": ["不匹配项1", ...]
            }
        """
        if not jd_text.strip():
            return self._fallback_result("JD 内容为空")
        if not resume_text.strip():
            return self._fallback_result("简历内容为空")

        # 截断过长的简历
        resume_text = self._truncate_resume(resume_text)

        prompt = self._build_prompt(jd_text, resume_text)

        for attempt in range(max_retries + 1):
            try:
                result = self._call_api(prompt)
                if result:
                    return result

                logging.warning(f"API 返回解析失败 (尝试 {attempt + 1}/{max_retries + 1})")
                if attempt < max_retries:
                    time.sleep(2)

            except requests.exceptions.Timeout:
                logging.warning(f"API 超时 (尝试 {attempt + 1}/{max_retries + 1})")
                if attempt < max_retries:
                    time.sleep(2)

            except requests.exceptions.RequestException as e:
                logging.warning(f"API 请求失败 (尝试 {attempt + 1}/{max_retries + 1}): {e}")
                if attempt < max_retries:
                    time.sleep(2)

            except Exception as e:
                logging.error(f"评估异常 (尝试 {attempt + 1}/{max_retries + 1}): {e}")
                if attempt < max_retries:
                    time.sleep(2)

        return self._fallback_result("API 调用失败（已重试）")

    # ------------------------------------------------------------------
    # Prompt 构建
    # ------------------------------------------------------------------

    def _build_prompt(self, jd_text, resume_text):
        """构建评估用 Prompt"""
        return f"""你是一位资深的HR招聘专家。请根据以下【岗位描述】严格评估【候选人简历】是否满足招聘要求。

【岗位描述】
{jd_text}

【候选人简历】
{resume_text}

请严格按以下 JSON 格式输出，不要包含其他内容：
{{
  "decision": "通过" | "待定" | "不通过",
  "reason": "20字以内说明核心判断依据",
  "matched_requirements": ["匹配点1", "匹配点2"],
  "unmatched_requirements": ["不匹配点1"]
}}"""

    # ------------------------------------------------------------------
    # API 调用
    # ------------------------------------------------------------------

    def _call_api(self, prompt):
        """调用 DeepSeek API 并解析结果"""
        response = requests.post(
            self.api_url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": self.model,
                "messages": [
                    {"role": "user", "content": prompt}
                ],
                "temperature": self.temperature,
                "max_tokens": self.max_tokens
            },
            timeout=30
        )

        if response.status_code != 200:
            error_msg = f"HTTP {response.status_code}"
            try:
                error_detail = response.json()
                error_msg += f" - {error_detail}"
            except:
                error_msg += f" - {response.text[:200]}"
            raise AIAnalyzerError(f"API 返回错误: {error_msg}")

        # 提取响应内容
        try:
            data = response.json()
            content = data['choices'][0]['message']['content']
        except (KeyError, IndexError, json.JSONDecodeError) as e:
            raise AIAnalyzerError(f"解析 API 响应结构失败: {e}")

        return self._parse_response(content)

    # ------------------------------------------------------------------
    # 响应解析
    # ------------------------------------------------------------------

    def _parse_response(self, content):
        """从 AI 响应中提取 JSON 结果"""
        content = content.strip()

        # 处理 markdown 代码块包裹
        if '```json' in content:
            content = content.split('```json', 1)[1]
            if '```' in content:
                content = content.split('```', 1)[0]
        elif '```' in content:
            # 尝试提取第一个代码块
            parts = content.split('```')
            if len(parts) >= 3:
                content = parts[1]
                # 跳过语言标识行
                if '\n' in content:
                    content = content.split('\n', 1)[1]

        content = content.strip()

        # 尝试 JSON 解析
        try:
            result = json.loads(content)
        except json.JSONDecodeError:
            # 尝试用正则提取 JSON 对象
            import re
            match = re.search(r'\{[\s\S]*"decision"[\s\S]*\}', content)
            if match:
                try:
                    result = json.loads(match.group(0))
                except json.JSONDecodeError:
                    raise AIAnalyzerError("无法解析 AI 响应中的 JSON")
            else:
                raise AIAnalyzerError("AI 响应中未找到 JSON 内容")

        # 验证并规范化结果
        return self._validate_result(result)

    def _validate_result(self, result):
        """验证并规范化评估结果"""
        decision = result.get('decision', '').strip()

        # 标准化决策值
        if decision in ('通过', '待定', '不通过'):
            pass
        elif decision in ('pass', 'PASS', '通过面试', '建议面试'):
            decision = '通过'
        elif decision in ('pending', 'PENDING', '待定面试', '待进一步确认'):
            decision = '待定'
        elif decision in ('fail', 'FAIL', '不通过面试', '拒绝'):
            decision = '不通过'
        else:
            logging.warning(f"AI 返回了未知决策: {decision}，已设为「待定」")
            decision = '待定'

        return {
            "decision": decision,
            "reason": result.get('reason', '')[:100],
            "matched_requirements": result.get('matched_requirements', []),
            "unmatched_requirements": result.get('unmatched_requirements', [])
        }

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------

    def _truncate_resume(self, resume_text):
        """截断过长的简历文本以控制 token 消耗"""
        if len(resume_text) > self.max_text_length:
            logging.info(
                f"简历文本过长 ({len(resume_text)} 字符)，"
                f"截断至 {self.max_text_length} 字符"
            )
            return resume_text[:self.max_text_length]
        return resume_text

    def _fallback_result(self, reason):
        """返回降级结果（标记为待定，避免误判）"""
        return {
            "decision": "待定",
            "reason": reason,
            "matched_requirements": [],
            "unmatched_requirements": []
        }
