/**
 * 挂机主页面
 *
 * 职责：WS 消息路由 → 状态机切换 → setData → 渲染
 * 优化：STORY_STREAM 80ms 帧合并、状态栏 1s 节流、日志上限 200
 */

import {
  CS_START_GAME,
  CS_SELECT_DESTINY_SIGN,
  CS_PLAYER_DECISION,
  SC_DESTINY_OFFER,
  SC_GAME_LOG,
  SC_HEAVEN_EVENT_TRIGGER,
  SC_STORY_STREAM,
  SC_EVENT_SETTLEMENT,
  SC_PONG,
  SC_ERROR,
  UIState,
} from '../../utils/actions';
import type { WsManager, WsFrame } from '../../utils/ws';
import type { IAppOption } from '../../app';

type DestinyOffer = { id: string; title: string; summary: string };

/* ── 节流/合并状态（模块级闭包，不参与 setData） ── */

let pendingChunks: string[] = [];
let mergeTimer: number | null = null;
let lastStatusUpdate = 0;
let countdownTimer: number | null = null;
let lastStreamVibrate = 0;
let hasStarted = false;
let unsubWs: (() => void) | null = null;
let startRetryTimer: number | null = null;

/* ── 工具函数 ── */

function getWs(): WsManager {
  const app = getApp<IAppOption>();
  return app.globalData.wsManager!;
}

function getSinMaxByRealm(realm: string): number {
  const map: Record<string, number> = {
    '练气期': 50,
    '筑基期': 60,
    '金丹期': 70,
    '元婴期': 80,
    '化神期': 90,
    '渡劫期': 100,
    '大乘期': 100,
  };
  return map[realm] || 50;
}

function calcSinPercent(sinValue: number, sinMax: number): number {
  if (sinMax <= 0) return 0;
  return Math.max(0, Math.min(100, Math.round((sinValue / sinMax) * 100)));
}

/* ── Page ── */

Page({
  data: {
    uiState: UIState.CONNECTING as string,
    playerName: '无名修士' as string,
    /* 状态栏 */
    cultivation: 0,
    sinValue: 0,
    luck: 50,
    foundation: 10,
    realm: '练气期' as string,
    sinPhase: '清白' as string,
    sinMax: 50 as number,
    sinPercent: 0 as number,
    /* 日志 */
    logs: [] as string[],
    destinyOffers: [] as DestinyOffer[],
    destinyError: '' as string,
    /* 事件触发 */
    triggerTitle: '' as string,
    triggerDescription: '' as string,
    triggerOptions: [] as { id: string; label: string }[],
    showCustomInput: false,
    customText: '' as string,
    decisionCountdown: 0,
    /* 流式故事 */
    storyText: '' as string,
    isStreaming: false,
    /* 结算 */
    settlementText: '' as string,
    heavenPointsEarned: 0,
    gameOver: false,
    gameOverTitle: '' as string,
    shieldRescueActive: false,
    shieldRescueText: '' as string,
    /* 连接 */
    lastHeartbeat: 0,
  },

  /* ═══════════════════════════════════════════
   * 生命周期
   * ═══════════════════════════════════════════ */

  onLoad() {
    const ws = getWs();

    // 注册 WS 消息回调，保存取消订阅函数
    unsubWs = ws.onMessage((frame: WsFrame) => {
      this._routeMessage(frame);
    });

    // 等待 login 完成拿到 playerId 后再连接（app.ts 中 wx.login 是异步的）
    this._tryConnect();
  },

  _tryConnect() {
    const id = getApp<IAppOption>().globalData.playerId;
    if (id) {
      getWs().connect(id);
    } else {
      // login 尚未完成，200ms 后重试
      setTimeout(() => this._tryConnect(), 200);
    }
  },

  onUnload() {
    if (unsubWs) {
      unsubWs();
      unsubWs = null;
    }
    if (startRetryTimer !== null) {
      clearTimeout(startRetryTimer);
      startRetryTimer = null;
    }
    clearMergeTimer();
    clearCountdown();
    hasStarted = false;
  },

  /* ═══════════════════════════════════════════
   * 用户操作
   * ═══════════════════════════════════════════ */

  onNameInput(e: WechatMiniprogram.InputEvent) {
    this.setData({ playerName: e.detail.value || '无名修士' });
  },

  onStartGame() {
    if (hasStarted) return;
    hasStarted = true;
    this.setData({
      uiState: UIState.CONNECTING,
      destinyOffers: [],
      destinyError: '',
    });
    this._sendStartWhenReady();
  },

  _sendStartWhenReady(retryCount = 0) {
    const ws = getWs();
    if (ws.getStatus() === 'connected') {
      ws.send(CS_START_GAME, { player_name: this.data.playerName });
      return;
    }

    if (retryCount === 0) {
      const id = getApp<IAppOption>().globalData.playerId;
      if (id) ws.connect(id);
    }

    if (retryCount >= 30) {
      appendLog.call(this, '[错误] 天道连接超时，请稍后重试');
      hasStarted = false;
      return;
    }

    startRetryTimer = setTimeout(() => {
      startRetryTimer = null;
      this._sendStartWhenReady(retryCount + 1);
    }, 200) as unknown as number;
  },

  onChooseOption(e: WechatMiniprogram.TouchEvent) {
    const choiceId = e.currentTarget.dataset.id as string;
    if (!choiceId) return;

    this.setData({ uiState: UIState.STREAMING, storyText: '' });
    clearCountdown();

    getWs().send(CS_PLAYER_DECISION, { choice_id: choiceId, custom_text: '' });
  },

  onChooseCustom() {
    this.setData({ showCustomInput: true, customText: '' });
  },

  onSendCustom() {
    const text = (this.data.customText as string).trim();
    if (!text) return;

    this.setData({ showCustomInput: false, uiState: UIState.STREAMING, storyText: '' });
    clearCountdown();

    getWs().send(CS_PLAYER_DECISION, { choice_id: 'C', custom_text: text });
  },

  onCancelCustom() {
    this.setData({ showCustomInput: false, customText: '' });
  },

  onCustomInput(e: WechatMiniprogram.InputEvent) {
    this.setData({ customText: e.detail.value });
  },

  onNewGame() {
    hasStarted = false;
    clearMergeTimer();
    pendingChunks = [];
    this.setData({
      uiState: UIState.CONNECTING,
      logs: [],
      destinyOffers: [],
      destinyError: '',
      storyText: '',
      settlementText: '',
      gameOver: false,
      gameOverTitle: '',
      cultivation: 0,
      sinValue: 0,
      luck: 50,
      foundation: 10,
      realm: '练气期',
      sinPhase: '清白',
      sinMax: 50,
      sinPercent: 0,
      shieldRescueActive: false,
      shieldRescueText: '',
    });
    this.onStartGame();
  },

  /* ═══════════════════════════════════════════
   * 消息路由
   * ═══════════════════════════════════════════ */

  _routeMessage(frame: WsFrame) {
    switch (frame.action) {
      case SC_DESTINY_OFFER:
        this._onDestinyOffer(frame);
        break;
      case SC_GAME_LOG:
        this._onGameLog(frame);
        break;
      case SC_HEAVEN_EVENT_TRIGGER:
        this._onEventTrigger(frame);
        break;
      case SC_STORY_STREAM:
        this._onStoryStream(frame);
        break;
      case SC_EVENT_SETTLEMENT:
        this._onEventSettlement(frame);
        break;
      case SC_PONG:
        this.setData({ lastHeartbeat: Date.now() });
        break;
      case SC_ERROR:
        if (this.data.uiState === UIState.PREPARING) {
          this.setData({
            destinyError: (frame.message as string) || '命格签选择失败，请重试',
          });
        }
        appendLog.call(this, `[错误] ${frame.message || '未知错误'}`);
        break;
    }
  },

  _onDestinyOffer(frame: WsFrame) {
    const offers = Array.isArray(frame.offers)
      ? (frame.offers as DestinyOffer[])
      : [];

    this.setData({
      uiState: UIState.PREPARING,
      destinyOffers: offers,
      destinyError: '',
    });
  },

  _onGameLog(frame: WsFrame) {
    if (frame.log_text) {
      appendLog.call(this, frame.log_text as string);
    }

    // 状态栏 1s 节流
    const now = Date.now();
    if (now - lastStatusUpdate >= 1000) {
      lastStatusUpdate = now;
      const realm = (frame.realm as string) ?? this.data.realm as string;
      const sinValue = (frame.sin_value as number) ?? this.data.sinValue;
      const sinMax = getSinMaxByRealm(realm);
      this.setData({
        cultivation: (frame.cultivation as number) ?? this.data.cultivation,
        sinValue,
        luck: (frame.luck as number) ?? this.data.luck,
        foundation: (frame.foundation as number) ?? this.data.foundation,
        realm,
        sinPhase: mapSinPhase((frame.sin_phase as string) || 'safe'),
        sinMax,
        sinPercent: calcSinPercent(sinValue, sinMax),
      });
    }

    if (this.data.uiState !== UIState.IDLE) {
      this.setData({ uiState: UIState.IDLE });
    }
  },

  onSelectDestiny(e: WechatMiniprogram.TouchEvent) {
    const signId = e.currentTarget.dataset.id as string;
    if (!signId) return;

    this.setData({
      destinyError: '',
    });
    getWs().send(CS_SELECT_DESTINY_SIGN, {
      sign_id: signId,
      player_name: this.data.playerName,
    });
  },

  _onEventTrigger(frame: WsFrame) {
    clearCountdown();

    // 防御：若 trigger 被双重序列化为字符串，尝试解析
    let trigger = frame.trigger as Record<string, unknown> | undefined;
    if (typeof trigger === 'string') {
      try {
        trigger = JSON.parse(trigger) as Record<string, unknown>;
      } catch (_) {
        trigger = undefined;
      }
    }

    const rawPersona = trigger?.heaven_persona;
    const persona = (typeof rawPersona === 'string' ? rawPersona : '') || '天道';

    const typeLabel: Record<string, string> = {
      BREAKTHROUGH: '境界突破',
      HEAVEN: '天道事件',
      SIN_FULL: '天谴神罚',
      ASCENSION: '飞升大考',
    };
    const rawType = trigger?.trigger_type;
    const triggerType = (typeof rawType === 'string' ? rawType : '') || 'HEAVEN';

    // 将后端 fixed_options[{id, text}] 映射为前端 {id, label}
    const rawOptions = (trigger?.fixed_options as { id: string; text: string }[]) || [];
    const mappedOptions = rawOptions.map((opt) => ({
      id: opt.id,
      label: opt.text,
    }));
    if (mappedOptions.length === 0) {
      mappedOptions.push(
        { id: 'A', label: '选项 A' },
        { id: 'B', label: '选项 B' },
      );
    }
    // 自由对线选项 C 由模板中独立按钮处理，不再加入固定选项列表

    // karma_brief 为空时给默认描述
    const rawKarma = trigger?.karma_brief;
    let karmaDesc = (typeof rawKarma === 'string' ? rawKarma : '');
    if (!karmaDesc) {
      const fallbackDesc: Record<string, string> = {
        BREAKTHROUGH: '境界壁垒已现裂痕，天道意志凝视着你，突破在此一举。',
        HEAVEN: '天机莫测，命运之轮开始转动，天道目光投向你。',
        SIN_FULL: '天谴值爆满！天道震怒，神罚之雷在云层中酝酿。',
        ASCENSION: '九天十地为之震动，万古仙穹敞开大门，最后的考验降临！',
      };
      karmaDesc = fallbackDesc[triggerType] || '天道意志降临，命运的齿轮开始转动。';
    }

    const realm = (frame.realm as string) ?? this.data.realm as string;
    const sinValue = (frame.sin_value as number) ?? this.data.sinValue;
    const sinMax = getSinMaxByRealm(realm);

    this.setData({
      uiState: UIState.AWAIT_DECISION,
      triggerTitle: `${persona} · ${typeLabel[triggerType] || triggerType}`,
      triggerDescription: karmaDesc,
      triggerOptions: mappedOptions,
      storyText: '',
      cultivation: (frame.cultivation as number) ?? this.data.cultivation,
      sinValue,
      luck: (frame.luck as number) ?? this.data.luck,
      foundation: (frame.foundation as number) ?? this.data.foundation,
      realm,
      sinPhase: mapSinPhase((frame.sin_phase as string) || 'safe'),
      sinMax,
      sinPercent: calcSinPercent(sinValue, sinMax),
    });

    // 60s 倒计时
    let remaining = 60;
    this.setData({ decisionCountdown: remaining });

    countdownTimer = setInterval(() => {
      remaining -= 1;
      if (remaining <= 0) {
        clearCountdown();
        return;
      }
      this.setData({ decisionCountdown: remaining });
    }, 1000) as unknown as number;
  },

  _onStoryStream(frame: WsFrame) {
    const chunk = (frame.chunk as string) || '';
    const isLast = frame.is_last as boolean;

    if (this.data.uiState !== UIState.STREAMING) {
      this.setData({ uiState: UIState.STREAMING });
    }

    pendingChunks.push(chunk);
    vibrateForStream();

    if (isLast) {
      flushChunks.call(this);
      this.setData({ isStreaming: false });
    } else if (mergeTimer === null) {
      mergeTimer = setTimeout(() => {
        mergeTimer = null;
        flushChunks.call(this);
      }, 80) as unknown as number;
    }
  },

  _onEventSettlement(frame: WsFrame) {
    clearCountdown();
    flushChunks.call(this);

    const settlement = frame.settlement as Record<string, unknown> | undefined;
    const gameOver = (frame.game_over as boolean) || false;
    const interceptedByShield = Boolean(settlement?.intercepted_by_shield);
    const realm = (frame.realm as string) ?? this.data.realm as string;
    const sinValue = (frame.sin_value as number) ?? this.data.sinValue;
    const sinMax = getSinMaxByRealm(realm);

    if (interceptedByShield) {
      wx.vibrateShort({ type: 'heavy' });
      setTimeout(() => {
        this.setData({ shieldRescueActive: false });
      }, 2600);
    }

    this.setData({
      uiState: gameOver ? UIState.GAME_OVER : UIState.SETTLEMENT,
      settlementText: (settlement?.story_text as string) || this.data.storyText,
      heavenPointsEarned: (frame.heaven_points_earned as number) || 0,
      gameOver,
      gameOverTitle: gameOver ? ((settlement?.dead_title as string) || '修士陨落') : '',
      shieldRescueActive: interceptedByShield,
      shieldRescueText: interceptedByShield ? '宗门大能撕裂时空将你捞回！' : '',
      cultivation: (frame.cultivation as number) ?? this.data.cultivation,
      sinValue,
      luck: (frame.luck as number) ?? this.data.luck,
      foundation: (frame.foundation as number) ?? this.data.foundation,
      realm,
      sinPhase: mapSinPhase((frame.sin_phase as string) || 'safe'),
      sinMax,
      sinPercent: calcSinPercent(sinValue, sinMax),
    });
  },
});

/* ═══════════════════════════════════════════
 * 工具函数
 * ═══════════════════════════════════════════ */

function appendLog(this: WechatMiniprogram.Page.Instance<any, any>, text: string) {
  const logs: string[] = (this.data.logs as string[]).concat(text);
  if (logs.length > 200) {
    logs.splice(0, logs.length - 200);
  }
  this.setData({ logs });
}

function flushChunks(this: WechatMiniprogram.Page.Instance<any, any>) {
  if (pendingChunks.length === 0) return;

  const newText = pendingChunks.join('');
  pendingChunks = [];
  const currentText = this.data.storyText as string;

  this.setData({
    storyText: currentText + newText,
    isStreaming: true,
  });
}

function clearMergeTimer() {
  if (mergeTimer !== null) {
    clearTimeout(mergeTimer);
    mergeTimer = null;
  }
  pendingChunks = [];
}

function vibrateForStream() {
  const now = Date.now();
  if (now - lastStreamVibrate < 120) return;
  lastStreamVibrate = now;
  wx.vibrateShort({ type: 'light' });
}

function mapSinPhase(phase: string): string {
  const map: Record<string, string> = {
    safe: '清白',
    warning: '业障',
    danger: '天谴',
  };
  return map[phase] || phase;
}

function clearCountdown() {
  if (countdownTimer !== null) {
    clearInterval(countdownTimer);
    countdownTimer = null;
  }
}
