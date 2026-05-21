/**
 * 天道虚无黑市 — 局外商店
 *
 * Phase 3B：REST API 获取商品列表 + 购买 + 封印解除动效。
 * 使用全局 player_id，与后端 /api/shop/* 交互。
 */

import { BASE_URL } from '../../utils/config';
import type { IAppOption } from '../../app';

interface ShopItem {
  id: string;
  name: string;
  cost: number;
  effect: string;
  value: number;
  desc: string;
  icon: string;
}

Page({
  data: {
    heavenPoints: 0,
    items: [] as ShopItem[],
    showToast: false,
    toastType: '',
    toastItemName: '',
    toastMessage: '',
  },

  onLoad() {
    this._fetchItems();
  },

  onShow() {
    // 每次切换到商店 tab 时刷新余额
    this._fetchItems();
  },

  /* ── 加载商品列表 ── */

  _fetchItems() {
    const playerId = this._getPlayerId();
    if (!playerId) {
      // playerId 还没就绪，延迟重试
      setTimeout(() => this._fetchItems(), 300);
      return;
    }

    wx.request({
      url: `${BASE_URL}/api/shop/items?player_id=${playerId}`,
      method: 'GET',
      success: (res) => {
        if (res.statusCode === 200) {
          const data = res.data as { items: ShopItem[]; heaven_points: number };
          this.setData({
            items: data.items || [],
            heavenPoints: data.heaven_points || 0,
          });
        }
      },
      fail: (err) => {
        console.error('[Shop] 获取商品列表失败:', err.errMsg);
      },
    });
  },

  /* ── 购买 ── */

  onBuy(e: WechatMiniprogram.TouchEvent) {
    const itemId = e.currentTarget.dataset.id as string;
    const cost = Number(e.currentTarget.dataset.cost);
    const playerId = this._getPlayerId();

    if (!playerId || !itemId) return;
    if (this.data.heavenPoints < cost) return;

    wx.request({
      url: `${BASE_URL}/api/shop/buy`,
      method: 'POST',
      header: { 'content-type': 'application/json' },
      data: { player_id: playerId, item_id: itemId },
      success: (res) => {
        if (res.statusCode === 200) {
          const data = res.data as {
            success: boolean;
            heaven_points: number;
            item: { id: string; name: string; effect: string };
          };

          if (data.success) {
            const item = data.item;
            this.setData({ heavenPoints: data.heaven_points });

            // 封印解除动效
            const toastType = item.effect === 'sin_reset' ? 'cinnabar' : '';
            const messages: Record<string, string> = {
              karma_shield: '宗门大能已在你身上留下因果印记，死亡时将撕裂时空将你捞回。',
              deafness_protocol: '天道已签署失聪协议。下局游戏中，你的骚话将被选择性忽略。',
              sin_reset: '天道已被收买。你的天谴记录已焚毁，清白之身重铸。',
            };

            this.setData({
              showToast: true,
              toastType,
              toastItemName: item.name,
              toastMessage: messages[item.effect] || '道具已生效',
            });

            // 震动反馈
            wx.vibrateShort({ type: 'medium' });
          }
        } else {
          const data = res.data as { error?: string };
          wx.showToast({ title: data.error || '购买失败', icon: 'none', duration: 2000 });
        }
      },
      fail: (err) => {
        console.error('[Shop] 购买请求失败:', err.errMsg);
        wx.showToast({ title: '网络错误，请重试', icon: 'none', duration: 2000 });
      },
    });
  },

  /* ── 关闭弹层 ── */

  onDismissToast() {
    this.setData({ showToast: false });
  },

  /* ── 工具 ── */

  _getPlayerId(): string {
    const app = getApp<IAppOption>();
    return app.globalData.playerId || '';
  },
});
