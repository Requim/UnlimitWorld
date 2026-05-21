/**
 * 天道不正经 — 应用入口
 *
 * 全局职责：
 *   - 生成/持久化 player_id（模拟微信 openid）
 *   - 持有 WsManager 单例引用
 *   - 管理前后台生命周期
 */

import { WsManager } from './utils/ws';

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

    const stored = wx.getStorageSync('player_id');
    if (stored) {
      this.globalData.playerId = stored;
    } else {
      this.globalData.playerId = genPlayerId();
      wx.setStorageSync('player_id', this.globalData.playerId);
    }
    console.log('[App] player_id:', this.globalData.playerId);
  },

  onShow() {
    const ws = this.globalData.wsManager;
    if (ws && ws.getStatus() === 'closed' && this.globalData.playerId) {
      console.log('[App] 从后台恢复，重连 WebSocket');
      ws.connect(this.globalData.playerId);
    }
  },

  onHide() {
    // 保持连接不关闭（后台挂机）
    console.log('[App] 进入后台，保持 WebSocket');
  },

  onError(msg: string) {
    console.error('[App] 全局错误:', msg);
  },
});

/** 生成模拟 player_id（生产环境替换为 wx.login 获取 openid） */
function genPlayerId(): string {
  const ts = Date.now().toString(36);
  const rand = Math.random().toString(36).slice(2, 8);
  return `wx_${ts}_${rand}`;
}
