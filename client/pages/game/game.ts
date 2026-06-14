import {
  CS_CHOOSE_MAP_NODE,
  CS_GET_RUN_MAP,
  CS_PLAYER_DECISION,
  CS_SELECT_AMBITION,
  CS_SELECT_DESTINY_SIGN,
  CS_START_GAME,
  SC_AMBITION_OFFER,
  SC_DESTINY_OFFER,
  SC_ERROR,
  SC_EVENT_SETTLEMENT,
  SC_GAME_LOG,
  SC_HEAVEN_EVENT_TRIGGER,
  SC_PONG,
  SC_RUN_MAP,
  SC_STORY_STREAM,
  UIState,
} from '../../utils/actions';
import type { IAppOption } from '../../app';
import { BASE_URL } from '../../utils/config';
import type { WsFrame, WsManager } from '../../utils/ws';

type DestinyOffer = { id: string; title: string; summary: string };
type AmbitionOffer = {
  id: string;
  title: string;
  summary: string;
  target: number;
  progress_label: string;
  reward_hint: string;
};
type StreamSegment = 'event_title' | 'reason_text' | 'verdict_text' | 'story_text';
type LightChoice = { id?: string; text?: string; result_text?: string; effects?: Record<string, unknown> };
type RunMapNode = {
  node_id: string;
  layer: number;
  route_index: number;
  route_label: string;
  node_type: string;
  node_label: string;
  risk_level: string;
  status: string;
  title: string;
  summary: string;
};
type RunMapChapter = { chapter: number; realm_name: string; nodes: RunMapNode[] };
type RunMapState = {
  run_map_id: string;
  current_chapter: number;
  current_node_id: string;
  available_next_nodes: string[];
  visited_nodes: string[];
  route_notice: string;
  route_notice_level: string;
  chapters: RunMapChapter[];
};
type RunMapStageView = {
  chapter: number;
  realm_name: string;
  status: string;
  summary: string;
  is_current: boolean;
  is_expanded: boolean;
  nodes: RunMapNode[];
};
type RouteSummaryState = {
  routeStageTitle: string;
  routeSummaryText: string;
  routeHintText: string;
  routeToggleText: string;
};
type RunStats = {
  leaderboardScoreDelta: number;
  tauntCount: number;
  gambleSurviveCount: number;
  karmaPollutionScore: number;
  deathDramaScore: number;
};

function normalizeOffers<T>(rawOffers: unknown): T[] {
  if (Array.isArray(rawOffers)) return rawOffers as T[];
  if (typeof rawOffers !== 'string') return [];
  try {
    const parsed = JSON.parse(rawOffers) as unknown;
    return Array.isArray(parsed) ? (parsed as T[]) : [];
  } catch (_) {
    return [];
  }
}

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

function getNumber(frame: WsFrame, key: string): number {
  const value = frame[key];
  return typeof value === 'number' ? value : 0;
}

function normalizeChoice(raw: unknown): LightChoice | null {
  if (!raw || typeof raw !== 'object') return null;
  return raw as LightChoice;
}

function buildChoiceSummary(choice: LightChoice | null): string {
  if (!choice) return '';
  return (choice.result_text || choice.text || '').trim();
}

function hasRunStats(stats: RunStats): boolean {
  return Object.values(stats).some((value) => value > 0);
}

function hasPhase3kFrame(frame: WsFrame): boolean {
  return Boolean(
    frame.event_pool
    || frame.risk_level
    || frame.chosen_choice
    || frame.karma_trace_hook
    || frame.node_id
    || frame.node_type
    || frame.route_label
    || frame.route_notice
    || getNumber(frame, 'leaderboard_score_delta') > 0
    || getNumber(frame, 'taunt_count') > 0
    || getNumber(frame, 'gamble_survive_count') > 0
    || getNumber(frame, 'karma_pollution_score') > 0
    || getNumber(frame, 'death_drama_score') > 0,
  );
}

function buildRunStats(current: RunStats, frame: WsFrame): RunStats {
  return {
    leaderboardScoreDelta: current.leaderboardScoreDelta + getNumber(frame, 'leaderboard_score_delta'),
    tauntCount: current.tauntCount + getNumber(frame, 'taunt_count'),
    gambleSurviveCount: current.gambleSurviveCount + getNumber(frame, 'gamble_survive_count'),
    karmaPollutionScore: current.karmaPollutionScore + getNumber(frame, 'karma_pollution_score'),
    deathDramaScore: current.deathDramaScore + getNumber(frame, 'death_drama_score'),
  };
}

function buildRouteNoticeState(frame: WsFrame, fallbackNotice: string, fallbackLevel: string) {
  const routeNotice = (frame.route_notice as string) || fallbackNotice;
  return {
    routeNotice,
    routeNoticeLevel: (frame.route_notice_level as string) || fallbackLevel,
    hasRouteNotice: Boolean(routeNotice),
  };
}

function buildPhase3kState(
  frame: WsFrame,
  nextStats: RunStats,
  choiceSummary: string,
  fallbackNotice: string,
  fallbackLevel: string,
) {
  const statsState = {
    runStats: nextStats,
    hasRunStats: hasRunStats(nextStats),
  };
  if (!hasPhase3kFrame(frame)) return statsState;
  return {
    eventPool: (frame.event_pool as string) || '',
    riskLevel: (frame.risk_level as string) || '',
    karmaTraceHook: (frame.karma_trace_hook as string) || '',
    routeNodeType: (frame.node_type as string) || '',
    routeLabel: (frame.route_label as string) || '',
    lightChoiceText: choiceSummary,
    showLightChoice: Boolean(choiceSummary),
    ...buildRouteNoticeState(frame, fallbackNotice, fallbackLevel),
    ...statsState,
  };
}

function normalizeRunMap(raw: unknown): RunMapState | null {
  if (!raw || typeof raw !== 'object') return null;
  const data = raw as Partial<RunMapState>;
  return {
    run_map_id: String(data.run_map_id || ''),
    current_chapter: typeof data.current_chapter === 'number' ? data.current_chapter : 1,
    current_node_id: String(data.current_node_id || ''),
    available_next_nodes: Array.isArray(data.available_next_nodes) ? data.available_next_nodes as string[] : [],
    visited_nodes: Array.isArray(data.visited_nodes) ? data.visited_nodes as string[] : [],
    route_notice: String(data.route_notice || ''),
    route_notice_level: String(data.route_notice_level || ''),
    chapters: Array.isArray(data.chapters) ? data.chapters as RunMapChapter[] : [],
  };
}

function currentChapter(runMap: RunMapState | null): RunMapChapter | null {
  if (!runMap) return null;
  return runMap.chapters.find((item) => item.chapter === runMap.current_chapter) || null;
}

function currentChapterNodes(runMap: RunMapState | null): RunMapNode[] {
  const chapter = currentChapter(runMap);
  return chapter ? chapter.nodes : [];
}

function buildRunMapStages(runMap: RunMapState | null, expandCurrent: boolean): RunMapStageView[] {
  if (!runMap) return [];
  return runMap.chapters.map((chapter) => {
    const isCurrent = chapter.chapter === runMap.current_chapter;
    const isExpanded = isCurrent && expandCurrent;
    return {
      chapter: chapter.chapter,
      realm_name: chapter.realm_name,
      status: resolveStageStatus(chapter.chapter, runMap.current_chapter),
      summary: buildStageSummary(chapter.nodes),
      is_current: isCurrent,
      is_expanded: isExpanded,
      nodes: isExpanded ? chapter.nodes : chapter.nodes.slice(0, 3),
    };
  });
}

function resolveStageStatus(chapter: number, currentChapter: number): string {
  if (chapter < currentChapter) return 'passed';
  if (chapter === currentChapter) return 'current';
  return 'future';
}

function buildStageSummary(nodes: RunMapNode[]): string {
  const available = nodes.filter((node) => node.status === 'available').length;
  const visited = nodes.filter((node) => node.status === 'visited').length;
  const current = nodes.filter((node) => node.status === 'current').length;
  if (available > 0) return `${available}处可选`;
  if (current > 0) return '行进中';
  if (visited > 0) return `已踏${visited}处`;
  return `${nodes.length}处未显`;
}

function buildRouteSummary(runMap: RunMapState | null): Omit<RouteSummaryState, 'routeToggleText'> {
  const chapter = currentChapter(runMap);
  const nodes = chapter ? chapter.nodes : [];
  const available = runMap ? runMap.available_next_nodes.length : 0;
  const currentNode = nodes.find((node) => node.status === 'current');
  const visited = nodes.filter((node) => node.status === 'visited').length;
  if (available > 0) {
    return buildRouteSummaryText(chapter, `${available}处机缘待选`, '择一处符牌，命途才会继续转动');
  }
  if (currentNode) {
    return buildRouteSummaryText(chapter, `${currentNode.route_label} · ${currentNode.node_label}`, '行进中的节点会由挂机事件继续结算');
  }
  if (visited > 0) {
    return buildRouteSummaryText(chapter, `已踏过${visited}处节点`, '当前无可选节点，可展开查看全局命途');
  }
  return buildRouteSummaryText(chapter, '静待命盘显形', '路线图同步后会显示六境预览');
}

function buildRouteSummaryText(
  chapter: RunMapChapter | null,
  routeSummaryText: string,
  routeHintText: string,
): Omit<RouteSummaryState, 'routeToggleText'> {
  return {
    routeStageTitle: chapter ? chapter.realm_name : '六境三路',
    routeSummaryText,
    routeHintText,
  };
}

function buildRouteToggleText(expanded: boolean, hasChoice: boolean): string {
  if (hasChoice) return '择一节点';
  return expanded ? '收起路线' : '展开路线';
}

function buildRunMapViewState(runMap: RunMapState | null, expanded: boolean) {
  const nodes = currentChapterNodes(runMap);
  const stages = buildRunMapStages(runMap, expanded);
  const hasChoice = Boolean(runMap && runMap.available_next_nodes.length > 0);
  return {
    runMap,
    runMapNodes: nodes,
    runMapStages: stages,
    hasRouteStages: stages.length > 0,
    hasRunMapNodes: nodes.length > 0,
    currentRunNodeId: runMap?.current_node_id || '',
    hasRunMapChoice: hasChoice,
    routeNotice: runMap?.route_notice || '',
    routeNoticeLevel: runMap?.route_notice_level || '',
    hasRouteNotice: Boolean(runMap?.route_notice),
    isRouteMapExpanded: expanded,
    routeToggleText: buildRouteToggleText(expanded, hasChoice),
    ...buildRouteSummary(runMap),
  };
}

function formatEventLog(text: string): string {
  const trimmed = text.trim();
  if (!trimmed) return '';
  return trimmed.length > 96 ? `${trimmed.slice(0, 96)}...` : trimmed;
}

function buildEventFeedState(frame: WsFrame, choiceSummary: string, previousLog: string) {
  const lastEventLog = frame.log_text ? formatEventLog(frame.log_text as string) : previousLog;
  return {
    lastEventLog,
    hasEventFeed: Boolean(lastEventLog || hasPhase3kFrame(frame) || choiceSummary),
  };
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
    ambitionOffers: [] as AmbitionOffer[],
    selectedDestinyId: '' as string,
    destinyError: '' as string,
    ambitionTitle: '' as string,
    ambitionProgress: 0 as number,
    ambitionTarget: 0 as number,
    ambitionProgressLabel: '' as string,
    eventPool: '' as string,
    riskLevel: '' as string,
    karmaTraceHook: '' as string,
    lightChoiceText: '' as string,
    showLightChoice: false,
    runMap: null as RunMapState | null,
    runMapNodes: [] as RunMapNode[],
    runMapStages: [] as RunMapStageView[],
    hasRouteStages: false,
    hasRunMapNodes: false,
    currentRunNodeId: '' as string,
    hasRunMapChoice: false,
    isRouteMapExpanded: false,
    routeStageTitle: '六境三路' as string,
    routeSummaryText: '静待命盘显形' as string,
    routeHintText: '路线图同步后会显示六境预览' as string,
    routeToggleText: '展开路线' as string,
    routeNotice: '' as string,
    routeNoticeLevel: '' as string,
    hasRouteNotice: false,
    routeNodeType: '' as string,
    routeLabel: '' as string,
    lastEventLog: '' as string,
    hasEventFeed: false,
    runStats: {
      leaderboardScoreDelta: 0,
      tauntCount: 0,
      gambleSurviveCount: 0,
      karmaPollutionScore: 0,
      deathDramaScore: 0,
    } as RunStats,
    hasRunStats: false,
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
    epitaphTitle: '' as string,
    leaderboardType: '' as string,
    leaderboardScore: 0 as number,
    nextGoalHint: '' as string,
    karmaMessage: '' as string,
    karmaEffectType: 'mislead' as string,
    karmaSubmitStatus: '' as string,
    karmaSubmitted: false,
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
      ambitionOffers: [],
      selectedDestinyId: '',
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
    const signId = (e.currentTarget.dataset.id || e.target.dataset.id) as string;
    if (!signId) return;

    this.setData({ destinyError: '' });
    getWs().send(CS_SELECT_DESTINY_SIGN, {
      sign_id: signId,
      player_name: this.data.playerName,
    });
  },

  onSelectAmbition(e: WechatMiniprogram.TouchEvent) {
    const ambitionId = (e.currentTarget.dataset.id || e.target.dataset.id) as string;
    if (!ambitionId) return;

    this.setData({ destinyError: '' });
    getWs().send(CS_SELECT_AMBITION, {
      ambition_id: ambitionId,
      player_name: this.data.playerName,
    });
  },

  onChooseMapNode(e: WechatMiniprogram.TouchEvent) {
    const nodeId = (e.currentTarget.dataset.id || e.target.dataset.id) as string;
    const status = (e.currentTarget.dataset.status || e.target.dataset.status) as string;
    if (!nodeId || status !== 'available') return;
    getWs().send(CS_CHOOSE_MAP_NODE, { node_id: nodeId });
  },

  onToggleRouteMap() {
    const runMap = this.data.runMap as RunMapState | null;
    const expanded = this.data.hasRunMapChoice ? true : !this.data.isRouteMapExpanded;
    this.setData(buildRunMapViewState(runMap, expanded));
  },

  _requestRunMap() {
    if (getWs().getStatus() !== 'connected') return;
    getWs().send(CS_GET_RUN_MAP, {});
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
      ambitionOffers: [],
      selectedDestinyId: '',
      destinyError: '',
      ambitionTitle: '',
      ambitionProgress: 0,
      ambitionTarget: 0,
      ambitionProgressLabel: '',
      eventPool: '',
      riskLevel: '',
      karmaTraceHook: '',
      lightChoiceText: '',
      showLightChoice: false,
      runMap: null,
      runMapNodes: [],
      runMapStages: [],
      hasRouteStages: false,
      hasRunMapNodes: false,
      currentRunNodeId: '',
      hasRunMapChoice: false,
      isRouteMapExpanded: false,
      routeStageTitle: '六境三路',
      routeSummaryText: '静待命盘显形',
      routeHintText: '路线图同步后会显示六境预览',
      routeToggleText: '展开路线',
      routeNotice: '',
      routeNoticeLevel: '',
      hasRouteNotice: false,
      routeNodeType: '',
      routeLabel: '',
      lastEventLog: '',
      hasEventFeed: false,
      runStats: {
        leaderboardScoreDelta: 0,
        tauntCount: 0,
        gambleSurviveCount: 0,
        karmaPollutionScore: 0,
        deathDramaScore: 0,
      },
      hasRunStats: false,
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
      epitaphTitle: '',
      leaderboardType: '',
      leaderboardScore: 0,
      nextGoalHint: '',
      karmaMessage: '',
      karmaEffectType: 'mislead',
      karmaSubmitStatus: '',
      karmaSubmitted: false,
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

  onKarmaMessageInput(e: WechatMiniprogram.InputEvent) {
    this.setData({ karmaMessage: e.detail.value });
  },

  onSelectKarmaEffect(e: WechatMiniprogram.TouchEvent) {
    const effect = e.currentTarget.dataset.effect as string;
    if (!effect) return;
    this.setData({ karmaEffectType: effect, karmaSubmitStatus: '' });
  },

  onSubmitKarmaTrace() {
    if (this.data.karmaSubmitted) return;
    const playerId = getApp<IAppOption>().globalData.playerId;
    if (!playerId) {
      this.setData({ karmaSubmitStatus: '缺少玩家身份，因果未能入池。' });
      return;
    }

    wx.request({
      url: `${BASE_URL}/api/karma-traces/submit`,
      method: 'POST',
      header: { 'content-type': 'application/json' },
      data: {
        player_id: playerId,
        player_name: this.data.playerName,
        effect_type: this.data.karmaEffectType,
        message: (this.data.karmaMessage as string).trim(),
      },
      success: (res) => {
        if (res.statusCode === 200) {
          const data = res.data as { sanitized?: boolean };
          this.setData({
            karmaSubmitted: true,
            karmaSubmitStatus: data.sanitized ? '遗言被天道打码后入池。' : '因果已偷渡入池，等后来者踩。',
          });
        } else {
          this.setData({ karmaSubmitStatus: '因果池暂不可用，天道把纸条吞了。' });
        }
      },
      fail: () => {
        this.setData({ karmaSubmitStatus: '网络不稳，因果纸条飘丢了。' });
      },
    });
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
      case SC_AMBITION_OFFER:
        this._onAmbitionOffer(frame);
        break;
      case SC_GAME_LOG:
        this._onGameLog(frame);
        break;
      case SC_RUN_MAP:
        this._onRunMap(frame);
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
    const offers = normalizeOffers<DestinyOffer>(frame.offers);
    this.setData({
      uiState: UIState.PREPARING,
      destinyOffers: offers,
      ambitionOffers: [],
      selectedDestinyId: '',
      destinyError: offers.length ? '' : '命格候选为空，请重新踏入仙途',
    });
  },

  _onAmbitionOffer(frame: WsFrame) {
    const offers = normalizeOffers<AmbitionOffer>(frame.offers);
    this.setData({
      uiState: UIState.PREPARING,
      ambitionOffers: offers,
      selectedDestinyId: (frame.destiny_sign_id as string) || '',
      destinyError: offers.length ? '' : '执念候选为空，请重新选择命格',
    });
  },

  _onGameLog(frame: WsFrame) {
    if (frame.log_text) {
      appendLog.call(this, frame.log_text as string);
      if (String(frame.event_type || '') === 'RUN_MAP_WAITING' || String(frame.log_text).includes('路线停驻')) {
        this._requestRunMap();
      }
    }

    const now = Date.now();
    const nextStats = buildRunStats(this.data.runStats, frame);
    const chosenChoice = normalizeChoice(frame.chosen_choice);
    const choiceSummary = buildChoiceSummary(chosenChoice);
    const phase3kState = buildPhase3kState(
      frame,
      nextStats,
      choiceSummary,
      this.data.routeNotice,
      this.data.routeNoticeLevel,
    );
    const eventFeedState = buildEventFeedState(frame, choiceSummary, this.data.lastEventLog as string);

    if (now - lastStatusUpdate >= 1000) {
      lastStatusUpdate = now;
      const realm = ((frame.realm as string) ?? this.data.realm) as string;
      const sinValue = ((frame.sin_value as number) ?? this.data.sinValue) as number;
      const sinMax = resolveSinMax(frame, realm);
      this.setData({
        ...phase3kState,
        ...eventFeedState,
        cultivation: (frame.cultivation as number) ?? this.data.cultivation,
        sinValue,
        luck: (frame.luck as number) ?? this.data.luck,
        foundation: (frame.foundation as number) ?? this.data.foundation,
        realm,
        sinPhase: mapSinPhase((frame.sin_phase as string) || 'safe'),
        sinMax,
        sinPercent: calcSinPercent(sinValue, sinMax),
        ambitionTitle: (frame.ambition_title as string) || this.data.ambitionTitle,
        ambitionProgress: (frame.ambition_progress as number) ?? this.data.ambitionProgress,
        ambitionTarget: (frame.ambition_target as number) ?? this.data.ambitionTarget,
        ambitionProgressLabel: (frame.ambition_progress_label as string) || this.data.ambitionProgressLabel,
      });
    } else {
      this.setData({
        ...phase3kState,
        ...eventFeedState,
      });
    }

    if (this.data.uiState !== UIState.IDLE) {
      this.setData({ uiState: UIState.IDLE });
    }
  },

  _onRunMap(frame: WsFrame) {
    const runMap = normalizeRunMap(frame.run_map);
    const hasChoice = Boolean(runMap && runMap.available_next_nodes.length > 0);
    const keepsManualExpand = this.data.isRouteMapExpanded && !this.data.hasRunMapChoice;
    const expanded = hasChoice || keepsManualExpand;
    this.setData(buildRunMapViewState(runMap, expanded));
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
      epitaphTitle: (settlement?.epitaph_title as string) || '',
      leaderboardType: mapLeaderboardType((settlement?.leaderboard_type as string) || ''),
      leaderboardScore: (settlement?.leaderboard_score as number) || 0,
      nextGoalHint: (settlement?.next_goal_hint as string) || '',
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

function mapLeaderboardType(type: string): string {
  const map: Record<string, string> = {
    ascension: '飞升榜候选',
    death: '暴毙榜候选',
    taunt: '嘴硬榜候选',
    gamble: '赌命榜候选',
    karma_pollution: '因果污染榜候选',
  };
  return map[type] || '';
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
