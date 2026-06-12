/**
 * Action Frame 常量 — 与后端 server/interface/ws.py:Action 保持一致
 *
 * 上行（Client → Server）: CS_*
 * 下行（Server → Client）: SC_*
 */

/* ── 上行 ── */
export const CS_START_GAME = 'CS_START_GAME';
export const CS_SELECT_DESTINY_SIGN = 'CS_SELECT_DESTINY_SIGN';
export const CS_SELECT_AMBITION = 'CS_SELECT_AMBITION';
export const CS_CHOOSE_MAP_NODE = 'CS_CHOOSE_MAP_NODE';
export const CS_GET_RUN_MAP = 'CS_GET_RUN_MAP';
export const CS_PING = 'CS_PING';
export const CS_PLAYER_DECISION = 'CS_PLAYER_DECISION';

/* ── 下行 ── */
export const SC_DESTINY_OFFER = 'SC_DESTINY_OFFER';
export const SC_AMBITION_OFFER = 'SC_AMBITION_OFFER';
export const SC_RUN_MAP = 'SC_RUN_MAP';
export const SC_GAME_LOG = 'SC_GAME_LOG';
export const SC_HEAVEN_EVENT_TRIGGER = 'SC_HEAVEN_EVENT_TRIGGER';
export const SC_STORY_STREAM = 'SC_STORY_STREAM';
export const SC_EVENT_SETTLEMENT = 'SC_EVENT_SETTLEMENT';
export const SC_PONG = 'SC_PONG';
export const SC_ERROR = 'SC_ERROR';

/* ── UI 状态（镜像后端 Stage） ── */
export enum UIState {
  CONNECTING = 'connecting',
  PREPARING = 'preparing',
  IDLE = 'idle',
  AWAIT_DECISION = 'await_decision',
  STREAMING = 'streaming',
  SETTLEMENT = 'settlement',
  GAME_OVER = 'game_over',
}
