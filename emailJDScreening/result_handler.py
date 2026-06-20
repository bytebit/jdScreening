"""
结果处理模块
负责：将邮件移动到分类文件夹、生成 CSV 报表、记录日志
"""
import csv
import logging
import os
from datetime import datetime


class ResultHandler:
    """结果处理器 - 处理 AI 评估后的结果"""

    def __init__(self, config, email_handler):
        self.config = config
        self.email_handler = email_handler
        self.folders = config['email']['folders']
        self.report_dir = config['logging']['report_dir']

    def process_result(self, email_id, msg, subject, sender_name, sender_email,
                       jd_name, attachment_name, ai_result):
        """
        处理一次评估结果：移动邮件 + 写日志 + 记录 CSV + 标记已读

        参数:
            email_id: IMAP 邮件 ID
            msg: 原始邮件对象（用于调试）
            subject: 邮件主题
            sender_name: 发件人姓名
            sender_email: 发件人邮箱
            jd_name: 匹配到的 JD 文件名
            attachment_name: 简历附件文件名
            ai_result: AI 评估结果 dict {decision, reason, ...}
        """
        decision = ai_result['decision']
        reason = ai_result['reason']

        # 1. 确定目标文件夹并移动邮件
        target_folder = self._get_target_folder(decision)
        self.email_handler.move_to_folder(email_id, target_folder)

        # 2. 控制台/日志输出
        log_line = (
            f"[{decision}] {sender_name} <{sender_email}> | "
            f"岗位: {jd_name} | 简历: {attachment_name} | "
            f"理由: {reason}"
        )
        logging.info(log_line)

        # 3. 写入 CSV 报表
        self._append_csv(sender_name, sender_email, subject,
                         jd_name, decision, reason, attachment_name)

        # 4. 标记为已读，防止下次重复处理
        if hasattr(self.email_handler, 'mark_as_read'):
            self.email_handler.mark_as_read(email_id)

    # ------------------------------------------------------------------
    # 邮件移动
    # ------------------------------------------------------------------

    def _get_target_folder(self, decision):
        """根据决策获取目标邮箱文件夹名称"""
        folder_map = {
            '通过': self.folders['pass'],
            '待定': self.folders['pending'],
            '不通过': self.folders['fail'],
        }
        return folder_map.get(decision, self.folders['pending'])

    # ------------------------------------------------------------------
    # CSV 报表
    # ------------------------------------------------------------------

    def _append_csv(self, sender_name, sender_email, subject,
                    jd_name, decision, reason, attachment_name):
        """追加一条记录到本次运行的 CSV 报表（每次运行生成新文件）"""
        os.makedirs(self.report_dir, exist_ok=True)

        ts = datetime.now().strftime('%Y-%m-%d_%H%M')
        report_file = os.path.join(self.report_dir, f'简历筛选报告_{ts}.csv')

        # 检查文件是否已存在（决定是否写表头）
        file_exists = os.path.exists(report_file)

        try:
            with open(report_file, 'a', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)

                if not file_exists:
                    writer.writerow([
                        '时间', '姓名', '邮箱', '邮件主题', '投递岗位',
                        '分类', '理由', '简历文件名'
                    ])

                writer.writerow([
                    datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    sender_name,
                    sender_email,
                    subject,
                    jd_name.replace('.txt', ''),
                    decision,
                    reason,
                    attachment_name,
                ])

            logging.info(f"已记录到报表: {report_file}")

        except Exception as e:
            log