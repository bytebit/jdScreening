"""
岗位匹配模块
负责：根据邮件主题关键词匹配对应的 JD（岗位描述）文件
"""
import os
import logging


class JDMatcherError(Exception):
    """JD 匹配异常"""
    pass


class JDMatcher:
    """JD 匹配器 - 根据邮件主题匹配对应的岗位描述文件"""

    def __init__(self, config):
        self.config = config
        self.jd_dir = config['jobs']['jd_dir']
        self.rules = config['jobs']['subject_rules']
        self.default_jd = config['jobs']['default_jd']

    def match_jd(self, subject):
        """
        根据邮件主题匹配对应的 JD 文件

        参数:
            subject: 邮件主题字符串

        返回:
            tuple: (jd文件名, jd文本内容)

        抛出:
            JDMatcherError: 匹配失败或 JD 文件不存在时
        """
        if not subject:
            logging.warning("邮件主题为空，使用默认 JD")
            return self._load_default_jd()

        # 按顺序匹配规则
        for rule in self.rules:
            keywords = rule['keywords']
            jd_file = rule['jd_file']

            for keyword in keywords:
                if keyword.lower() in subject.lower():
                    jd_path = self._resolve_jd_path(jd_file)
                    if os.path.exists(jd_path):
                        logging.info(
                            f"主题「{subject}」→ 关键词「{keyword}」→ "
                            f"匹配 JD: {jd_file}"
                        )
                        return jd_file, self._load_jd_text(jd_path)
                    else:
                        logging.warning(
                            f"JD 文件不存在: {jd_path}（规则匹配到 {jd_file}）"
                        )
                        break  # 尝试下一条规则

        # 无规则命中，使用默认 JD
        logging.info(f"主题「{subject}」未匹配到规则，使用默认 JD")
        return self._load_default_jd()

    def list_available_jds(self):
        """列出所有可用的 JD 文件（调试用）"""
        jds = []
        if not os.path.isdir(self.jd_dir):
            return jds
        for f in sorted(os.listdir(self.jd_dir)):
            if f.endswith('.txt'):
                jds.append(f)
        return jds

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _resolve_jd_path(self, jd_file):
        """解析 JD 文件的绝对路径"""
        # 支持相对路径和绝对路径
        if os.path.isabs(jd_file):
            return jd_file
        return os.path.join(self.jd_dir, jd_file)

    def _load_jd_text(self, jd_path):
        """读取 JD 文件内容"""
        try:
            with open(jd_path, 'r', encoding='utf-8') as f:
                return f.read().strip()
        except Exception as e:
            raise JDMatcherError(f"读取 JD 文件失败 {jd_path}: {e}")

    def _load_default_jd(self):
        """加载默认 JD"""
        default_path = self._resolve_jd_path(self.default_jd)
        if not os.path.exists(default_path):
            raise JDMatcherError(
                f"默认 JD 文件不存在: {default_path}\n"
                f"请创建该文件或在 config.yaml 中配置正确的 default_jd"
            )
        return self.default_jd, self._load_jd_text(default_path)
