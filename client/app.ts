/**
 * 天道不正经 — 应用入口
 *
 * 全局职责：
 *   - wx.login → 后端换 openid → player_id
 *   - 持有 WsManager 单例引用
 *   - 管理前后台生命周期
 *
 * Phase 3A：微信登录 + openid 绑定，开发环境降级为本地 ID。
 */

import { WsManager } from './utils/ws';
import { BASE_URL } from './utils/config';

export interface IAppOption {
  globalData: {
    playerId: string;
    wsManager: WsManager | null;
  };
}

App<IAppOption>({
  globalData: {
    playerId: '',
    wsManager: null,
  },

  onLaunch() {
    // 初始化 WsManager 单例
    this.globalData.wsManager = new WsManager();

    // Phase 3A：微信登录 → openid
    this._doLogin();
  },

  onShow() {
    const ws = this.globalData.wsManager;
    if (ws && ws.getStatus() === 'closed' && this.globalData.playerId) {
      console.log('[App] 从后台恢复，重连 WebSocket');
      ws.connect(this.globalData.playerId);
    }
  },

  onHide() {
    console.log('[App] 进入后台，保持 WebSocket');
  },

  onError(msg: string) {
    console.error('[App] 全局错误:', msg);
  },

  /* ── Phase 3A：登录流程 ── */

  _doLogin() {
    // 清理旧版 fake ID（genPlayerId 的 wx_ 前缀）
    const cached = wx.getStorageSync('player_id');
    if (cached && cached.startsWith('wx_')) {
      wx.removeStorageSync('player_id');
    }

    wx.login({
      success: (res) => {
        if (!res.code) {
          console.error('[App] wx.login 返回空 code，使用本地 ID');
          this._setPlayerId(genPlayerId());
          return;
        }
        this._exchangeCode(res.code);
      },
      fail: (err) => {
        console.error('[App] wx.login 失败:', err.errMsg);
        // 降级：使用缓存的 ID 或生成本地 ID
        const fallback = wx.getStorageSync('player_id') as string;
        if (fallback && !fallback.startsWith('wx_') && !fallback.startsWith('dev_')) {
          this._setPlayerId(fallback);
        } else {
          this._setPlayerId(genPlayerId());
        }
      },
    });
  },

  _exchangeCode(code: string) {
    wx.request({
      url: `${BASE_URL}/api/auth/login`,
      method: 'POST',
      data: { code },
      header: { 'content-type': 'application/json' },
      success: (res) => {
        if (res.statusCode === 200) {
          const data = res.data as { player_id?: string; error?: string };
          if (data.player_id) {
            console.log('[App] 微信登录成功, player_id:', data.player_id);
            this._setPlayerId(data.player_id);
            return;
          }
          console.error('[App] 登录接口返回错误:', data.error);
        } else {
          console.error('[App] 登录接口 HTTP', res.statusCode);
        }
        // 降级
        const fallback = wx.getStorageSync('player_id') as string;
        if (fallback && !fallback.startsWith('wx_') && !fallback.startsWith('dev_')) {
          this._setPlayerId(fallback);
        } else {
          this._setPlayerId(genPlayerId());
        }
      },
      fail: (err) => {
        console.error('[App] 登录接口请求失败:', err.errMsg);
        // 降级：开发环境可用
        const fallback = wx.getStorageSync('player_id') as string;
        if (fallback && !fallback.startsWith('wx_') && !fallback.startsWith('dev_')) {
          this._setPlayerId(fallback);
        } else {
          this._setPlayerId(genPlayerId());
        }
      },
    });
  },

  _setPlayerId(id: string) {
    this.globalData.playerId = id;
    wx.setStorageSync('player_id', id);
  },
});

/** 开发环境降级：生成模拟 player_id */
function genPlayerId(): string {
  const ts = Date.now().toString(36);
  const rand = Math.random().toString(36).slice(2, 8);
  return `dev_${ts}_${rand}`;
}
