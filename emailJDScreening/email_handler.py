"""
邮件接入模块
负责：IMAP连接、搜索未读邮件、下载附件、邮件移动到分类文件夹
"""
import imaplib
import email
from email.header import decode_header
import os
import re
import logging
from pathlib import Path
from datetime import datetime


class EmailHandler:
    """邮件处理器 - 封装所有IMAP操作"""

    def __init__(self, config):
        self.config = config
        self.email_config = config['email']
        self.imap = None
        self._connected = False

    # ------------------------------------------------------------------
    # 连接与登录
    # ------------------------------------------------------------------

    def connect(self):
        """连接到 IMAP 服务器并登录"""
        try:
            self.imap = imaplib.IMAP4_SSL(
                self.email_config['imap_server'],
                self.email_config['imap_port']
            )
            self.imap._encoding = 'utf-8'
            password = self._resolve_password()
            self.imap.login(self.email_config['account'], password)
            self.imap.select(self.email_config['inbox_folder'])
            self._connected = True
            logging.info(
                f"已连接到邮箱 {self.email_config['account']} "
                f"({self.email_config['imap_server']})"
            )
        except imaplib.IMAP4.error as e:
            logging.error(f"IMAP 连接/登录失败: {e}")
            raise
        except Exception as e:
            logging.error(f"邮箱连接异常: {e}")
            raise

    def _resolve_password(self):
        """解析密码：优先从环境变量读取"""
        pwd = self.email_config['password']
        if pwd.startswith('${') and pwd.endswith('}'):
            env_var = pwd[2:-1]
            pwd = os.environ.get(env_var, '')
            if not pwd:
                logging.warning(f"环境变量 {env_var} 未设置，请检查")
        return pwd

    def is_connected(self):
        """检查连接是否仍然有效"""
        if not self.imap or not self._connected:
            return False
        try:
            self.imap.noop()
            return True
        except:
            return False

    # ------------------------------------------------------------------
    # 邮件获取
    # ------------------------------------------------------------------

    def get_unseen_emails(self):
        """获取所有未读邮件的序列号列表（用 SEARCH ALL 过滤幽灵邮件）"""
        try:
            # 先获取所有实际存在的邮件序列号
            _, all_data = self.imap.search(None, 'ALL')
            all_ids = set(all_data[0].split()) if all_data[0] else set()

            # 再获取未读邮件序列号
            _, unseen_data = self.imap.search(None, 'UNSEEN')
            unseen_ids = unseen_data[0].split() if unseen_data[0] else []

            # 只保留两者交集（过滤 SEARCH UNSEEN 可能返回的幽灵邮件）
            valid = [sid for sid in unseen_ids if sid in all_ids]
            if len(valid) != len(unseen_ids):
                ghost_count = len(unseen_ids) - len(valid)
                logging.warning(f"过滤了 {ghost_count} 封幽灵序列号")

            return valid
        except Exception as e:
            logging.error(f"搜索未读邮件失败: {e}")
            return []

    def fetch_email(self, email_id):
        """获取指定 ID 的邮件原始数据"""
        fetch_attempts = [
            '(RFC822)',
            '(BODY[])',
            '(BODY.PEEK[])',
        ]
        for fetch_item in fetch_attempts:
            try:
                typ, msg_data = self.imap.fetch(email_id, fetch_item)
                if typ != 'OK' or not msg_data:
                    continue
                raw_bytes = None
                for part in msg_data:
                    if part is None:
                        continue
                    if isinstance(part, tuple) and len(part) >= 2:
                        raw_bytes = part[1]
                        break
                    elif isinstance(part, bytes):
                        raw_bytes = part
                        break
                if raw_bytes:
                    return email.message_from_bytes(raw_bytes)
            except Exception:
                continue

        logging.warning(f"邮件 {email_id} 获取失败")
        return None

    # ------------------------------------------------------------------
    # 邮件头解析
    # ------------------------------------------------------------------

    def _decode_mime_header(self, header_value):
        """解码 MIME 编码的邮件头（如 Subject、From）"""
        if not header_value:
            return ''
        decoded_parts = decode_header(header_value)
        result = ''
        for part_text, charset in decoded_parts:
            if isinstance(part_text, bytes):
                charset = charset or 'utf-8'
                try:
                    result += part_text.decode(charset, errors='replace')
                except LookupError:
                    result += part_text.decode('utf-8', errors='replace')
            else:
                result += part_text
        return result

    def get_subject(self, msg):
        """获取邮件主题"""
        subject = msg.get('Subject', '')
        return self._decode_mime_header(subject)

    def get_sender_email(self, msg):
        """提取发件人邮箱地址"""
        from_header = msg.get('From', '')
        match = re.search(r'[\w.+\-]+@[\w\-]+\.[\w.\-]+', from_header)
        return match.group(0) if match else from_header

    def get_sender_name(self, msg):
        """提取发件人显示名称"""
        from_header = msg.get('From', '')
        # 尝试提取 "Name" <email> 中的 Name
        match = re.search(r'^"?([^"<]*)"?\s*<', from_header)
        if match:
            name = match.group(1).strip()
            if name:
                return self._decode_mime_header(name)
        # 没有显示名称，返回邮箱地址
        return self.get_sender_email(msg)

    def get_date(self, msg):
        """获取邮件发送时间"""
        date_str = msg.get('Date', '')
        return date_str

    # ------------------------------------------------------------------
    # 正文提取
    # ------------------------------------------------------------------

    def get_body_text(self, msg):
        """提取邮件正文纯文本（支持 HTML 转纯文本）"""
        import re as _re
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                ct = part.get_content_type()
                if ct == 'text/plain':
                    payload = part.get_payload(decode=True)
                    if payload:
                        try:
                            body += payload.decode('utf-8', errors='replace')
                        except:
                            body += payload.decode('gbk', errors='replace')
                    break
            if not body:
                for part in msg.walk():
                    ct = part.get_content_type()
                    if ct == 'text/html':
                        payload = part.get_payload(decode=True)
                        if payload:
                            try:
                                html = payload.decode('utf-8', errors='replace')
                            except:
                                html = payload.decode('gbk', errors='replace')
                            # HTML 转纯文本
                            html = _re.sub(r'<head>.*?</head>', '', html, flags=_re.DOTALL)
                            html = _re.sub(r'<style[^>]*>.*?</style>', '', html, flags=_re.DOTALL)
                            html = _re.sub(r'<[^>]+>', '\n', html)
                            html = _re.sub(r'\s+', ' ', html)
                            body = html.strip()
                        break
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                try:
                    body = payload.decode('utf-8', errors='replace')
                except:
                    body = payload.decode('gbk', errors='replace')
        return body.strip()

    # ------------------------------------------------------------------
    # 附件处理
    # ------------------------------------------------------------------

    def download_attachments(self, msg, download_dir):
        """
        下载邮件中的简历附件
        返回附件文件路径列表
        """
        attachments = []
        supported = self.config['resume']['supported_formats']

        if not msg.is_multipart():
            logging.warning("邮件不是 multipart 格式，可能没有附件")
            return attachments

        for part in msg.walk():
            if part.get_content_maintype() == 'multipart':
                continue
            if part.get('Content-Disposition') is None:
                continue

            filename = part.get_filename()
            if not filename:
                continue

            # 解码文件名
            filename = self._decode_mime_header(filename)

            # 检查文件格式
            ext = Path(filename).suffix.lower()
            if ext not in supported:
                logging.info(f"跳过不支持的格式: {filename}")
                continue

            # 添加时间戳前缀避免同名文件覆盖
            timestamp = datetime.now().strftime('%H%M%S')
            safe_name = f"{timestamp}_{self._sanitize_filename(filename)}"
            filepath = os.path.join(download_dir, safe_name)

            try:
                os.makedirs(download_dir, exist_ok=True)
                with open(filepath, 'wb') as f:
                    f.write(part.get_payload(decode=True))
                file_size = os.path.getsize(filepath)
                logging.info(f"下载附件: {safe_name} ({file_size} bytes)")
                attachments.append(filepath)
            except Exception as e:
                logging.error(f"保存附件 {filename} 失败: {e}")

        return attachments

    @staticmethod
    def _sanitize_filename(filename):
        """清理文件名中的非法字符"""
        return re.sub(r'[\\/:*?"<>|]', '_', filename)

    # ------------------------------------------------------------------
    # 邮件移动
    # ------------------------------------------------------------------

    _chinese_folder_supported = None  # 缓存：该服务器是否支持中文文件夹名

    def _list_folders(self):
        """列出邮箱中的所有文件夹，返回 (分隔符, 文件夹列表)"""
        try:
            typ, folders = self.imap.list()
            if typ != 'OK':
                return None, []
            separator = '/'
            parsed = []
            for line in folders:
                decoded = line.decode('utf-8', errors='replace')
                # IMAP 