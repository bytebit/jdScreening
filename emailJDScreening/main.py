#!/usr/bin/env python3
"""
AI 简历自动筛选系统 - 主入口

工作流程:
  1. 加载配置
  2. 连接邮箱，获取未读邮件
  3. 对每封含简历附件的邮件：
     a. 下载附件
     b. 解析简历文本
     c. 根据邮件主题匹配 JD
     d. 调用 DeepSeek API 评估匹配度
     e. 将邮件移动到对应分类文件夹
     f. 记录 CSV 报表
  4. 清理临时文件，断开连接

用法:
  python main.py                    # 单次运行（由 PM2 循环调度）
  python main.py --dry-run          # 试运行（不下结论、不移动邮件）
  python main.py --debug            # 调试模式（输出详细日志）
  python main.py --daemon           # 守护模式：持续循环运行（配合 PM2 使用）
  python main.py --daemon --interval 3  # 守护模式，每次间隔 3 分钟
"""
import argparse
import logging
import os
import signal
import sys
import time
import traceback
from pathlib import Path

import yaml


def load_config(config_path='config.yaml'):
    """加载 YAML 配置文件"""
    # 查找配置文件：当前目录 → 脚本所在目录
    search_paths = [
        config_path,
        os.path.join(os.path.dirname(__file__), 'config.yaml'),
    ]

    for path in search_paths:
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            logging.info(f"已加载配置文件: {path}")
            return config

    raise FileNotFoundError(
        f"配置文件 config.yaml 未找到，请在以下路径之一创建：\n"
        + '\n'.join(f"  - {p}" for p in search_paths)
    )


def setup_logging(config, debug=False):
    """配置日志系统"""
    log_config = config['logging']
    level = logging.DEBUG if debug else getattr(logging, log_config['level'], logging.INFO)

    # 确保日志目录存在
    log_dir = os.path.dirname(log_config['file'])
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)

    # 同时输出到文件和控制台
    handlers = [
        logging.FileHandler(log_config['file'], encoding='utf-8'),
        logging.StreamHandler(sys.stdout),
    ]

    logging.basicConfig(
        level=level,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=handlers,
    )


def ensure_directories(config):
    """确保必要的目录存在"""
    dirs = [
        config['logging']['temp_dir'],
        config['logging']['report_dir'],
        config['jobs']['jd_dir'],
    ]
    for d in dirs:
        if d and not d.startswith('${'):
            os.makedirs(d, exist_ok=True)


def process_single_email(email_handler, resume_parser, jd_matcher,
                          ai_analyzer, result_handler, email_id, config, dry_run=False):
    """处理单封邮件"""
    # 1. 获取邮件
    msg = email_handler.fetch_email(email_id)
    if msg is None:
        return

    subject = email_handler.get_subject(msg)
    sender_name = email_handler.get_sender_name(msg)
    sender_email = email_handler.get_sender_email(msg)

    logging.info(f"--- 处理邮件: 「{subject}」({sender_name} <{sender_email}>)")

    # 2. 下载附件
    temp_dir = config['logging']['temp_dir']
    attachments = email_handler.download_attachments(msg, temp_dir)

    if not attachments:
        logging.info(f"邮件「{subject}」无简历附件，跳过")
        # 将无附件的邮件移到「待定」避免反复处理
        if not dry_run:
            email_handler.move_to_folder(
                email_id, config['email']['folders']['pending']
            )
        return

    # 3. 处理每个附件
    for attachment_path in attachments:
        attachment_name = Path(attachment_path).name

        try:
            # 3a. 解析简历
            resume_text = resume_parser.parse(attachment_path)
            logging.info(f"简历解析完成: {attachment_name} ({len(resume_text)} 字符)")

            # 3b. 匹配 JD
            jd_name, jd_text = jd_matcher.match_jd(subject)
            logging.info(f"匹配 JD: {jd_name}")

            # 3c. AI 评估
            if dry_run:
                logging.info(f"[试运行] 将调用 DeepSeek API 评估 {attachment_name}")
                if not dry_run:
                    pass  # 防止 lint 警告
            else:
                ai_result = ai_analyzer.evaluate(jd_text, resume_text)
                logging.info(
                    f"AI 评估结果: [{ai_result['decision']}] "
                    f"{ai_result['reason']}"
                )

                # 3d. 处理结果（移动邮件 + 记录报表）
                result_handler.process_result(
                    email_id=email_id,
                    msg=msg,
                    subject=subject,
                    sender_name=sender_name,
                    sender_email=sender_email,
                    jd_name=jd_name,
                    attachment_name=attachment_name,
                    ai_result=ai_result,
                )

        except Exception as e:
            logging.error(f"处理 {attachment_name} 失败: {e}")
            logging.debug(traceback.format_exc())
            continue

    # 4. 清理临时附件文件
    email_handler.delete_temp_files(attachments)


# ======================================================================
# 守护进程信号管理
# ======================================================================

_shutdown_flag = False


def _signal_handler(signum, frame):
    """捕获 SIGTERM/SIGINT，优雅关闭守护进程"""
    global _shutdown_flag
    _shutdown_flag = True
    logging.info(f"收到信号 {signum}，将在本轮处理完成后退出...")


def _register_signal_handlers():
    """注册信号处理器"""
    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)


# ======================================================================
# 核心运行逻辑（单次执行）
# ======================================================================

def run_once(config, dry_run=False):
    """
    执行一次处理流程：连接邮箱 → 处理未读邮件 → 断开

    返回:
        int: 成功处理的邮件数量
    """
    from email_handler import EmailHandler
    from resume_parser import ResumeParser
    from jd_matcher import JDMatcher
    from ai_analyzer import AIAnalyzer
    from result_handler import ResultHandler

    email_handler = EmailHandler(config)
    resume_parser = ResumeParser()
    jd_matcher = JDMatcher(config)
    ai_analyzer = AIAnalyzer(config)
    result_handler = ResultHandler(config, email_handler)

    success_count = 0

    try:
        # 1. 连接邮箱
        logging.info("正在连接邮箱...")
        email_handler.connect()

        # 2. 获取未读邮件
        email_ids = email_handler.get_unseen_emails()
        if not email_ids:
            logging.info("没有未读邮件")
            return 0

        logging.info(f"共发现 {len(email_ids)} 封未读邮件，开始处理...")

        # 3. 逐封处理
        for email_id in email_ids:
            try:
                process_single_email(
                    email_handler, resume_parser, jd_matcher,
                    ai_analyzer, result_handler,
                    email_id, config, dry_run=dry_run
                )
                success_count += 1
            except Exception as e:
                logging.error(f"处理邮件 {email_id} 时发生未预期错误: {e}")
                logging.debug(traceback.format_exc())
                continue

        # 4. 输出汇总
        logging.info(f"本轮完成：{success_count}/{len(email_ids)} 封邮件处理成功")
        return success_count

    except Exception as e:
        logging.error(f"运行异常: {e}")
        logging.debug(traceback.format_exc())
