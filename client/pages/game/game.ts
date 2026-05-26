import {
  CS_PLAYER_DECISION,
  CS_SELECT_DESTINY_SIGN,
  CS_START_GAME,
  SC_DESTINY_OFFER,
  SC_ERROR,
  SC_EVENT_SETTLEMENT,
  SC_GAME_LOG,
  SC_HEAVEN_EVENT_TRIGGER,
  SC_PONG,
  SC_STORY_STREAM,
  UIState,
} from '../../utils/actions';
import type { IAppOption } from '../../app';
import type { WsFrame, WsManager } from '../../utils/ws';

type DestinyOffer = { id: string; title: string; summary: string };
type StreamSegment = 'event_title' | 'reason_text' | 'verdict_text' | 'story_text';

let pendingSegments: Record<StreamSegment, string[]> = {
  event_title: [],
  reason_text: [],
  verdict_text: [],
  story_text: [],
};
let mergeTimer: number | null = null;
let countdownTimer: number | null = null;
let autoReturnTimer: number | null = null;
let autoReturnInterval: number | null = null;
let startRetryTimer: number | null = null;
let lastStatusUpdate = 0;
let lastStreamVibrate = 0;
let hasStarted = false;
let unsubWs: (() => void) | null = null;

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

function resolveSinMax(frame: WsFrame, fallbackRealm: string): number {
  const frameSinMax = frame.sin_max as number | undefined;
  if (typeof frameSinMax === 'number' && frameSinMax > 0) {
    return frameSinMax;
  }
  return getSinMaxByRealm(fallbackRealm);
}

Page({
  data: {
    uiState: UIState.CONNECTING as string,
    playerName: '无名修士' as string,
    cultivation: 0,
    sinValue: 0,
    luck: 50,
    foundation: 10,
    realm: '练气期' as string,
    sinPhase: '清白' as string,
    sinMax: 50 as number,
    sinPercent: 0 as number,
    logs: [] as string[],
    destinyOffers: [] as DestinyOffer[],
    destinyError: '' as string,
    triggerTitle: '' as string,
    triggerDescription: '' as string,
    triggerOptions: [] as { id: string; label: string }[],
    showCustomInput: false,
    customText: '' as string,
    decisionCountdown: 0,
    streamEventTitle: '' as string,
    storyText: '' as string,
    streamVerdict: '' as string,
    isStreaming: false,
    streamHint: '天道正在陈述因由' as string,
    settlementReason: '' as string,
    settlementVerdict: '' as string,
    settlementText: '' as string,
    heavenPointsEarned: 0,
    gameOver: false,
    gameOverTitle: '' as string,
    returnCountdown: 0,
    returnHint: '' as string,
    shieldRescueActive: false,
    shieldRescueText: '' as string,
    lastHeartbeat: 0,
  },

  onLoad() {
    const ws = getWs();
    unsubWs = ws.onMessage((frame: WsFrame) => {
      this._routeMessage(frame);
    });
    this._tryConnect();
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
    clearAutoReturn();
    hasStarted = false;
  },

  _tryConnect() {
    const id = getApp<IAppOption>().globalData.playerId;
    if (id) {
      getWs().connect(id);
    } else {
      setTimeout(() => this._tryConnect(), 200);
    }
  },

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

  onSelectDestiny(e: WechatMiniprogram.TouchEvent) {
    const signId = e.currentTarget.dataset.id as string;
    if (!signId) return;

    this.setData({ destinyError: '' });
    getWs().send(CS_SELECT_DESTINY_SIGN, {
      sign_id: signId,
      player_name: this.data.playerName,
    });
  },

  onChooseOption(e: WechatMiniprogram.TouchEvent) {
    const choiceId = e.currentTarget.dataset.id as string;
    if (!choiceId) return;
    this._beginStreaming();
    getWs().send(CS_PLAYER_DECISION, { choice_id: choiceId, custom_text: '' });
  },

  onChooseCustom() {
    this.setData({ showCustomInput: true, customText: '' });
  },

  onCancelCustom() {
    this.setData({ showCustomInput: false, customText: '' });
  },

  onCustomInput(e: WechatMiniprogram.InputEvent) {
    this.setData({ customText: e.detail.value });
  },

  onSendCustom() {
    const text = (this.data.customText as string).trim();
    if (!text) return;
    this._beginStreaming();
    this.setData({ showCustomInput: false });
    getWs().send(CS_PLAYER_DECISION, { choice_id: 'C', custom_text: text });
  },

  onNewGame() {
    hasStarted = false;
    clearMergeTimer();
    clearCountdown();
    clearAutoReturn();
    resetPendingSegments();
    this.setData({
      uiState: UIState.CONNECTING,
      logs: [],
      destinyOffers: [],
      destinyError: '',
      triggerTitle: '',
      triggerDescription: '',
      triggerOptions: [],
      showCustomInput: false,
      customText: '',
      decisionCountdown: 0,
      streamEventTitle: '',
      storyText: '',
      streamVerdict: '',
      isStreaming: false,
      streamHint: '天道正在陈述因由',
      settlementReason: '',
      settlementVerdict: '',
      settlementText: '',
      heavenPointsEarned: 0,
      gameOver: false,
      gameOverTitle: '',
      returnCountdown: 0,
      returnHint: '',
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

  _beginStreaming() {
    clearAutoReturn();
    clearCountdown();
    clearMergeTimer();
    resetPendingSegments();
    this.setData({
      uiState: UIState.STREAMING,
      streamEventTitle: '',
      storyText: '',
      streamVerdict: '',
      isStreaming: false,
      streamHint: '天道正在显名',
      settlementReason: '',
      settlementVerdict: '',
      settlementText: '',
      returnCountdown: 0,
      returnHint: '',
    });
  },

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
            destinyError: (frame.message as string) || '命格选择失败，请重试',
          });
        }
        appendLog.call(this, `[错误] ${frame.message || '未知错误'}`);
        break;
    }
  },

  _onDestinyOffer(frame: WsFrame) {
    const offers = Array.isArray(frame.offers) ? (frame.offers as DestinyOffer[]) : [];
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

    const now = Date.now();
    if (now - lastStatusUpdate >= 1000) {
      lastStatusUpdate = now;
      const realm = ((frame.realm as string) ?? this.data.realm) as string;
      const sinValue = ((frame.sin_value as number) ?? this.data.sinValue) as number;
      const sinMax = resolveSinMax(frame, realm);
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

  _onEventTrigger(frame: WsFrame) {
    clearCountdown();
    clearAutoReturn();
    clearMergeTimer();
    resetPendingSegments();

    let trigger = frame.trigger as Record<string, unknown> | undefined;
    if (typeof trigger === 'string') {
      try {
        trigger = JSON.parse(trigger) as Record<string, unknown>;
      } catch (_) {
        trigger = undefined;
      }
    }

    const persona = (typeof trigger?.heaven_persona === 'string' ? trigger.heaven_persona : '') || '天道';
    const triggerType = (typeof trigger?.trigger_type === 'string' ? trigger.trigger_type : '') || 'HEAVEN';
    const typeLabel: Record<string, string> = {
      BREAKTHROUGH: '境界突破',
      HEAVEN: '天道事件',
      SIN_FULL: '天谴神罚',
      ASCENSION: '飞升大劫',
    };

    const rawOptions = (trigger?.fixed_options as { id: string; text: string }[]) || [];
    const mappedOptions = rawOptions.length > 0
      ? rawOptions.map((opt) => ({ id: opt.id, label: opt.text }))
      : [{ id: 'A', label: '选项 A' }, { id: 'B', label: '选项 B' }];

    let karmaDesc = (typeof trigger?.karma_brief === 'string' ? trigger.karma_brief : '');
    if (!karmaDesc) {
      const fallbackDesc: Record<string, string> = {
        BREAKTHROUGH: '境界壁障已现裂痕，天道意志正在凝视你，突破就在此刻。',
        HEAVEN: '天机莫测，命运之轮已开始转动，天道目光投向你。',
        SIN_FULL: '天谴值爆满，神罚之雷正在云层深处酝酿。',
        ASCENSION: '九天十地为之震动，万古仙门正在洞开，最后的考验降临了。',
      };
      karmaDesc = fallbackDesc[triggerType] || '天道意志降临，命运的齿轮开始转动。';
    }

    const realm = ((frame.realm as string) ?? this.data.realm) as string;
    const sinValue = ((frame.sin_value as number) ?? this.data.sinValue) as number;
    const sinMax = resolveSinMax(frame, realm);

    this.setData({
      uiState: UIState.AWAIT_DECISION,
      triggerTitle: `${persona} · ${typeLabel[triggerType] || triggerType}`,
      triggerDescription: karmaDesc,
      triggerOptions: mappedOptions,
      showCustomInput: false,
      customText: '',
      streamEventTitle: '',
      storyText: '',
      streamVerdict: '',
      isStreaming: false,
      streamHint: '天道正在陈述因由',
      settlementReason: '',
      settlementVerdict: '',
      settlementText: '',
      returnCountdown: 0,
      returnHint: '',
      cultivation: (frame.cultivation as number) ?? this.data.cultivation,
      sinValue,
      luck: (frame.luck as number) ?? this.data.luck,
      foundation: (frame.foundation as number) ?? this.data.foundation,
      realm,
      sinPhase: mapSinPhase((frame.sin_phase as string) || 'safe'),
      sinMax,
      sinPercent: calcSinPercent(sinValue, sinMax),
    });

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
    const segment = normalizeSegment(frame.segment as string | undefined);
    const chunk = (frame.chunk as string) || '';
    const isLast = Boolean(frame.is_last);

    if (this.data.uiState !== UIState.STREAMING) {
      this.setData({
        uiState: UIState.STREAMING,
        isStreaming: false,
      });
    }

    if (segment === 'event_title') {
      this.setData({ streamHint: '天道正在显名' });
    } else if (segment === 'verdict_text') {
      this.setData({ streamHint: '天道裁决将落' });
    } else {
      this.setData({ streamHint: '天道正在陈述因由' });
    }

    pendingSegments[segment].push(chunk);
    vibrateForStream();

    if (isLast) {
      flushSegments.call(this);
      this.setData({
        isStreaming: false,
        streamHint: '因由既明，裁决已落',
      });
      return;
    }

    if (mergeTimer === null) {
      mergeTimer = setTimeout(() => {
        mergeTimer = null;
        flushSegments.call(this);
      }, 80) as unknown as number;
    }
  },

  _onEventSettlement(frame: WsFrame) {
    clearCountdown();
    clearAutoReturn();
    flushSegments.call(this);

    const settlement = frame.settlement as Record<string, unknown> | undefined;
    const gameOver = Boolean(frame.game_over);
    const interceptedByShield = Boolean(settlement?.intercepted_by_shield);
    const eventTitle = (settlement?.event_title as string) || (this.data.streamEventTitle as string) || (this.data.triggerTitle as string);
    const settlementReason = (settlement?.reason_text as string) || (this.data.storyText as string);
    const settlementVerdict = ((settlement?.verdict_text as string)
      || (this.data.streamVerdict as string)
      || (gameOver ? ((settlement?.dead_title as string) || '天道裁决已落') : (eventTitle || '天道放行')));
    const realm = ((frame.realm as string) ?? this.data.realm) as string;
    const sinValue = ((frame.sin_value as number) ?? this.data.sinValue) as number;
    const sinMax = resolveSinMax(frame, realm);

    if (interceptedByShield) {
      wx.vibrateShort({ type: 'heavy' });
      setTimeout(() => {
        this.setData({ shieldRescueActive: false });
      }, 2600);
    }

    this.setData({
      uiState: gameOver ? UIState.GAME_OVER : UIState.SETTLEMENT,
      streamEventTitle: eventTitle,
      storyText: settlementReason,
      streamVerdict: settlementVerdict,
      settlementReason,
      settlementVerdict,
      settlementText: (settlement?.story_text as string) || [settlementReason, settlementVerdict].filter(Boolean).join('\n\n'),
      heavenPointsEarned: (frame.heaven_points_earned as number) || 0,
      gameOver,
      gameOverTitle: gameOver ? ((settlement?.dead_title as string) || '修士道陨') : '',
      returnCountdown: gameOver ? 0 : 3,
      returnHint: gameOver ? '' : '裁决已落，神识归位中',
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
      isStreaming: false,
    });

    appendLog.call(this, `[天道裁决] ${settlementVerdict}`);

    if (!gameOver) {
      let remaining = 3;
      autoReturnInterval = setInterval(() => {
        remaining -= 1;
        if (remaining <= 0) {
          if (autoReturnInterval !== null) {
            clearInterval(autoReturnInterval);
            autoReturnInterval = null;
          }
          return;
        }
        this.setData({
          returnCountdown: remaining,
          returnHint: remaining === 1 ? '裁决余波散尽，即将回到挂机' : '裁决已落，神识归位中',
        });
      }, 1000) as unknown as number;

      autoReturnTimer = setTimeout(() => {
        clearAutoReturn();
        this.setData({
          uiState: UIState.IDLE,
          returnCountdown: 0,
          returnHint: '',
          streamHint: '天道正在陈述因由',
        });
      }, 3000) as unknown as number;
    }
  },
});

function appendLog(this: WechatMiniprogram.Page.Instance<any, any>, text: string) {
  const logs = (this.data.logs as string[]).concat(text);
  if (logs.length > 200) {
    logs.splice(0, logs.length - 200);
  }
  this.setData({ logs });
}

function flushSegments(this: WechatMiniprogram.Page.Instance<any, any>) {
  const titleChunk = pendingSegments.event_title.join('');
  const reasonChunk = (pendingSegments.reason_text.join('') || pendingSegments.story_text.join(''));
  const verdictChunk = pendingSegments.verdict_text.join('');

  if (!titleChunk && !reasonChunk && !verdictChunk) return;

  pendingSegments = {
    event_title: [],
    reason_text: [],
    verdict_text: [],
    story_text: [],
  };

  this.setData({
    streamEventTitle: (this.data.streamEventTitle as string) + titleChunk,
    storyText: (this.data.storyText as string) + reasonChunk,
    streamVerdict: (this.data.streamVerdict as string) + verdictChunk,
    isStreaming: true,
  });
}

function clearMergeTimer() {
  if (mergeTimer !== null) {
    clearTimeout(mergeTimer);
    mergeTimer = null;
  }
  resetPendingSegments();
}

function resetPendingSegments() {
  pendingSegments = {
    event_title: [],
    reason_text: [],
    verdict_text: [],
    story_text: [],
  };
}

function normalizeSegment(segment?: string): StreamSegment {
  if (segment === 'event_title' || segment === 'verdict_text' || segment === 'story_text') {
    return segment;
  }
  return 'reason_text';
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

function clearAutoReturn() {
  if (autoReturnTimer !== null) {
    clearTimeout(autoReturnTimer);
    autoReturnTimer = null;
  }
  if (autoReturnInterval !== null) {
    clearInterval(autoReturnInterval);
    autoReturnInterval = null;
  }
}
