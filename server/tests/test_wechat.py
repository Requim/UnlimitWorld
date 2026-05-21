"""
Phase 3A 测试：微信 API 客户端 + Auth 端点 + 内容安全审查

覆盖：
  - WeChatClient mock 模式（无真实 AppID/Secret）
  - code2session 降级逻辑
  - msgSecCheck 通过/拦截
  - POST /api/auth/login 端点
  - 无配置时 access_token 返回 None
"""

import sys
from pathlib import Path

_project_root = Path(__file__).parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from server.infrastructure.wechat.client import WeChatClient


class TestWeChatClientMockMode:
    """未配置 AppID/Secret 时的降级行为"""

    def test_disabled_when_no_credentials(self):
        client = WeChatClient()
        # settings 默认 wechat_appid="" wechat_secret=""
        assert client.enabled is False

    def test_code2session_returns_dev_openid(self):
        client = WeChatClient()
        result = client._appid = ""  # force disabled
        result = asyncio_run(client.code2session("test_code_123"))
        assert "openid" in result
        assert result["openid"].startswith("dev_")
        assert "session_key" in result

    def test_ensure_access_token_returns_none_when_disabled(self):
        client = WeChatClient()
        result = asyncio_run(client.ensure_access_token())
        assert result is None

    def test_msg_sec_check_passes_when_disabled(self):
        client = WeChatClient()
        result = asyncio_run(client.msg_sec_check("敏感内容"))
        assert result["pass"] is True

    def test_msg_sec_check_empty_content_passes(self):
        client = WeChatClient()
        result = asyncio_run(client.msg_sec_check("  "))
        assert result["pass"] is True


class TestWeChatClientEnabled:
    """配置了 AppID/Secret 时的行为（mock HTTP 响应）"""

    @pytest.fixture
    def client_with_creds(self):
        client = WeChatClient()
        client._appid = "wx_test_appid"
        client._secret = "test_secret_123"
        return client

    def test_enabled_with_credentials(self, client_with_creds):
        assert client_with_creds.enabled is True

    @pytest.mark.asyncio
    async def test_code2session_success(self, client_with_creds):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "openid": "oUpF8uMuAJO_TEST",
            "session_key": "HyVFkGl5F5OQWJZZaNzBBg==",
        }
        with patch.object(client_with_creds._http, "get", return_value=mock_resp):
            result = await client_with_creds.code2session("real_code")
            assert result["openid"] == "oUpF8uMuAJO_TEST"
            assert "error" not in result

    @pytest.mark.asyncio
    async def test_code2session_error_response(self, client_with_creds):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"errcode": 40029, "errmsg": "invalid code"}
        with patch.object(client_with_creds._http, "get", return_value=mock_resp):
            result = await client_with_creds.code2session("bad_code")
            assert "error" in result
            assert "40029" in result["error"]

    @pytest.mark.asyncio
    async def test_code2session_network_error(self, client_with_creds):
        with patch.object(client_with_creds._http, "get", side_effect=Exception("timeout")):
            result = await client_with_creds.code2session("any_code")
            assert "error" in result

    @pytest.mark.asyncio
    async def test_refresh_token_success(self, client_with_creds):
        client_with_creds._token = None
        client_with_creds._token_expires_at = 0
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "access_token": "55_test_access_token",
            "expires_in": 7200,
        }
        with patch.object(client_with_creds._http, "post", return_value=mock_resp):
            token = await client_with_creds._refresh_token()
            assert token == "55_test_access_token"
            assert client_with_creds._token == "55_test_access_token"

    @pytest.mark.asyncio
    async def test_token_cached_within_ttl(self, client_with_creds):
        import time
        client_with_creds._token = "cached_token"
        client_with_creds._token_expires_at = time.time() + 3600
        token = await client_with_creds.ensure_access_token()
        assert token == "cached_token"

    @pytest.mark.asyncio
    async def test_token_refreshed_when_expired(self, client_with_creds):
        import time
        client_with_creds._token = "old_token"
        client_with_creds._token_expires_at = time.time() - 60  # expired
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "access_token": "new_token",
            "expires_in": 7200,
        }
        with patch.object(client_with_creds._http, "post", return_value=mock_resp):
            token = await client_with_creds.ensure_access_token()
            assert token == "new_token"

    @pytest.mark.asyncio
    async def test_msg_sec_check_pass(self, client_with_creds):
        client_with_creds._token = "valid_token"
        client_with_creds._token_expires_at = time_in_future()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "errcode": 0,
            "result": {"suggest": "pass", "label": "normal"},
        }
        with patch.object(client_with_creds._http, "post", return_value=mock_resp):
            result = await client_with_creds.msg_sec_check("正常文本")
            assert result["pass"] is True

    @pytest.mark.asyncio
    async def test_msg_sec_check_block(self, client_with_creds):
        client_with_creds._token = "valid_token"
        client_with_creds._token_expires_at = time_in_future()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "errcode": 0,
            "result": {"suggest": "risky", "label": "politics"},
        }
        with patch.object(client_with_creds._http, "post", return_value=mock_resp):
            result = await client_with_creds.msg_sec_check("违规内容")
            assert result["pass"] is False
            assert result["label"] == "politics"

    @pytest.mark.asyncio
    async def test_msg_sec_check_api_error_degrades_to_pass(self, client_with_creds):
        """内容安全 API 异常时降级放行，避免误杀"""
        client_with_creds._token = "valid_token"
        client_with_creds._token_expires_at = time_in_future()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"errcode": 40001, "errmsg": "invalid token"}
        with patch.object(client_with_creds._http, "post", return_value=mock_resp):
            result = await client_with_creds.msg_sec_check("文本")
            assert result["pass"] is True  # 降级放行

    @pytest.mark.asyncio
    async def test_msg_sec_check_network_error_degrades_to_pass(self, client_with_creds):
        """网络异常时降级放行"""
        client_with_creds._token = "valid_token"
        client_with_creds._token_expires_at = time_in_future()
        with patch.object(client_with_creds._http, "post", side_effect=Exception("timeout")):
            result = await client_with_creds.msg_sec_check("文本")
            assert result["pass"] is True


class TestAuthEndpoint:
    """POST /api/auth/login 端点测试"""

    @pytest.mark.asyncio
    async def test_missing_code_returns_400(self):
        from server.interface.app import create_app
        from fastapi.testclient import TestClient

        app = create_app()
        client = TestClient(app)
        resp = client.post("/api/auth/login", json={})
        assert resp.status_code == 400
        assert "缺少 code" in resp.json()["error"]

    @pytest.mark.asyncio
    async def test_login_returns_player_id(self):
        from server.interface.app import create_app
        from fastapi.testclient import TestClient

        app = create_app()
        client = TestClient(app)
        resp = client.post("/api/auth/login", json={"code": "test_wx_code_abc"})
        assert resp.status_code == 200
        data = resp.json()
        assert "player_id" in data
        # mock 模式返回 dev_ 前缀
        assert data["player_id"].startswith("dev_")

    @pytest.mark.asyncio
    async def test_login_dev_mode_consistent(self):
        """相同 code 在 mock 模式返回相同 player_id（幂等）"""
        from server.interface.app import create_app
        from fastapi.testclient import TestClient

        app = create_app()
        client = TestClient(app)
        resp1 = client.post("/api/auth/login", json={"code": "same_code"})
        resp2 = client.post("/api/auth/login", json={"code": "same_code"})
        assert resp1.json()["player_id"] == resp2.json()["player_id"]


# ── 辅助 ──

def time_in_future(offset=3600):
    import time
    return time.time() + offset


def asyncio_run(coro):
    import asyncio
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()
