"""
微信 API 客户端模块

Phase 3A：wx.login code2session + 稳定版 access_token 管理 + msgSecCheck 内容安全。
"""

from server.infrastructure.wechat.client import WeChatClient

__all__ = ["WeChatClient"]
