"""
微信 API 客户端

实现：
  - jscode2session：wx.login code → openid + session_key
  - stable_token：获取/缓存 access_token（7200s TTL）
  - msg_sec_check：文本内容安全审查

未配置 WECHAT_APPID 时自动降级为 mock 通过模式（开发/测试友好）。
"""

import time
import logging
from typing import Optional

import httpx

from server.config import settings

logger = logging.getLogger("wechat")

WECHAT_API_BASE = "https://api.weixin.qq.com"


class WeChatClient:
    """微信 API 客户端。

    单例，access_token 内存缓存 + 懒加载。
    未配置 appid/secret 时自动降级为 mock 模式。
    """

    def __init__(self):
        self._appid = settings.wechat_appid
        self._secret = settings.wechat_secret
        self._token: Optional[str] = None
        self._token_expires_at: float = 0.0
        self._http = httpx.AsyncClient(timeout=10.0)

    @property
    def enabled(self) -> bool:
        return bool(self._appid and self._secret)

    # ── access_token ──────────────────────────────────────────

    async def ensure_access_token(self) -> Optional[str]:
        """返回缓存的 access_token，若过期则重新获取。未配置时返回 None。"""
        if not self.enabled:
            return None
        if self._token and time.time() < self._token_expires_at - 120:
            return self._token
        return await self._refresh_token()

    async def _refresh_token(self) -> Optional[str]:
        """通过 stable_token 接口获取 access_token。"""
        url = f"{WECHAT_API_BASE}/cgi-bin/stable_token"
        payload = {
            "grant_type": "client_credential",
            "appid": self._appid,
            "secret": self._secret,
        }
        try:
            resp = await self._http.post(url, json=payload)
            data = resp.json()
            token = data.get("access_token")
            expires = data.get("expires_in", 7200)
            if token:
                self._token = token
                self._token_expires_at = time.time() + expires
                logger.info("access_token 刷新成功，有效期 %ds", expires)
                return token
            else:
                logger.error("获取 access_token 失败: %s", data)
                return None
        except Exception as e:
            logger.error("获取 access_token 网络异常: %s", e)
            return None

    # ── wx.login ──────────────────────────────────────────────

    async def code2session(self, code: str) -> dict:
        """用 wx.login 返回的 code 换取 openid + session_key。

        Returns:
            {"openid": str, "session_key": str} 或 {"error": str}
        """
        if not self.enabled:
            return {"openid": f"dev_{code[:12]}", "session_key": "dev_session_key"}

        url = f"{WECHAT_API_BASE}/sns/jscode2session"
        params = {
            "appid": self._appid,
            "secret": self._secret,
            "js_code": code,
            "grant_type": "authorization_code",
        }
        try:
            resp = await self._http.get(url, params=params)
            data = resp.json()
            openid = data.get("openid")
            if openid:
                return {"openid": openid, "session_key": data.get("session_key", "")}
            else:
                errcode = data.get("errcode", -1)
                errmsg = data.get("errmsg", "未知错误")
                logger.error("code2session 失败: errcode=%s errmsg=%s", errcode, errmsg)
                return {"error": f"微信登录失败: {errmsg} (code={errcode})"}
        except Exception as e:
            logger.error("code2session 网络异常: %s", e)
            return {"error": f"登录服务暂不可用: {e}"}

    # ── msgSecCheck ───────────────────────────────────────────

    async def msg_sec_check(self, content: str, openid: str = "") -> dict:
        """文本内容安全审查（msgSecCheck 1.0）。

        Returns:
            {"pass": True} 或 {"pass": False, "suggest": str, "label": str}
        """
        if not content.strip():
            return {"pass": True}

        if not self.enabled:
            return {"pass": True}

        token = await self.ensure_access_token()
        if not token:
            logger.warning("msgSecCheck: 无 access_token，降级放行")
            return {"pass": True}

        url = f"{WECHAT_API_BASE}/wxa/msg_sec_check"
        params = {"access_token": token}
        payload = {
            "version": 2,
            "openid": openid or "",
            "scene": 1,   # 用户生成内容
            "content": content,
        }
        try:
            resp = await self._http.post(url, json=payload, params=params)
            data = resp.json()
            errcode = data.get("errcode", -1)
            if errcode == 0:
                result = data.get("result", {})
                suggest = result.get("suggest", "pass")
                if suggest == "pass":
                    return {"pass": True}
                label = result.get("label", "")
                return {"pass": False, "suggest": suggest, "label": label}
            else:
                errmsg = data.get("errmsg", "未知错误")
                logger.error("msgSecCheck 失败: errcode=%s errmsg=%s", errcode, errmsg)
                # API 调用失败时降级放行（避免误杀）
                return {"pass": True}
        except Exception as e:
            logger.error("msgSecCheck 网络异常: %s", e)
            return {"pass": True}

    async def close(self):
        await self._http.aclose()
