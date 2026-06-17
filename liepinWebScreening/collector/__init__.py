"""
采集模块
=========

两种工作模式：

模式 A（推荐）：CDP 连接
  - 连接到用户已有的 Chrome 浏览器
  - 自动找到猎聘搜索结果标签页
  - 无需传 URL、无需重新登录
  - 用法: python main.py run --connect

模式 B：常规 Playwright
  - 新开浏览器窗口
  - 需先 login 保存 Cookie
  - 后备方案
  - 用法: python main.py login + python main.py run --search-url "..."
"""

from .liepin_collector import LiepinCollector
from .cdp_connector import CDPConnector

__all__ = ["LiepinCollector", "CDPConnector"]
