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
        """获取所有未读邮件的 ID 列表"""
        try:
            _, messages = self.imap.search(None, 'UNSEEN')
            ids = messages[0].split() if messages[0] else []
            logging.info(f"发现 {len(ids)} 封未读邮件")
            return ids
        except Exception as e:
            logging.error(f"搜索未读邮件失败: {e}")
            return []

    def fetch_email(self, email_id):
        """获取指定 ID 的邮件原始数据"""
        try:
            _, msg_data = self.imap.fetch(email_id, '(RFC822)')
            raw_email = msg_data[0][1]
            return email.message_from_bytes(raw_email)
        except Exception as e:
            logging.error(f"获取邮件 {email_id} 失败: {e}")
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

    def ensure_folder(self, folder_name):
        """确保邮箱文件夹存在，不存在则创建"""
        try:
            self.imap.create(folder_name)
        except imaplib.IMAP4.error:
            # 文件夹可能已存在，忽略
            pass

    def move_to_folder(self, email_id, folder_name):
        """
        将邮件移动到指定文件夹
        使用 IMAP COPY + STORE +FLAGS \\Deleted 实现移动效果
        """
        try:
            self.ensure_folder(folder_name)
            result = self.imap.copy(email_id, folder_name)
            if result[0] == 'OK':
                self.imap.store(email_id, '+FLAGS', '\\Deleted')
                logging.info(f"邮件 {email_id} 已移至 [{folder_name}]")
            else:
                logging.error(f"移动邮件 {email_id} 失败: {result}")
        except Exception as e:
            logging.error(f"移动邮件 {email_id} 到 {folder_name} 失败: {e}")

    # ------------------------------------------------------------------
    # 清理与断开
    # ------------------------------------------------------------------

    def delete_temp_files(self, file_paths):
        """删除临时下载的附件文件"""
        for fp in file_paths:
            try:
                if os.path.exists(fp):
                    os.remove(fp)
            except Exception as e:
                logging.warning(f"删除临时文件 {fp} 失败: {e}")

    def logout(self):
        """断开 IMAP 连接"""
        if self.imap:
            try:
                self.imap.expunge()
                self.imap.logout()
            except:
                pass
            self._connected = False
            logging.info("已断开邮箱连接")
