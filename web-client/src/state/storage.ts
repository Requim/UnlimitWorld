import type { RunMode } from "../api/types";

export const SESSION_KEY = "tiandao.cardRogue.session.v1";
export const MYTH_BIFANG_SESSION_KEY = "tiandao.cardRogue.mythBifang.session.v1";
export const SETTINGS_KEY = "tiandao.cardRogue.settings.v1";

/** localStorage 中唯一允许持久化的匿名档案凭证与当前局号。 */
export interface StoredSession {
  accessToken: string;
  runId: string;
}

/** 仅保存在本机的音频和动画偏好，不上传服务端。 */
export interface GameSettings {
  volume: number;
  muted: boolean;
  reducedMotion: boolean;
}

export const DEFAULT_SETTINGS: GameSettings = {
  volume: 0.65,
  muted: false,
  reducedMotion: false,
};

/** 读取并校验指定模式的匿名局面凭证；默认经典档，格式错误返回 null 且不抛异常。 */
export function loadSession(mode: RunMode = "classic"): StoredSession | null {
  return parseStored(sessionKey(mode), isSession, null);
}

/** 保存指定模式的匿名局面凭证；默认经典档，存储失败会抛出异常。 */
export function saveSession(session: StoredSession, mode: RunMode = "classic"): void {
  localStorage.setItem(sessionKey(mode), JSON.stringify(session));
}

/** 删除指定模式的失效会话；默认经典档，仅影响对应 localStorage 键。 */
export function clearSession(mode: RunMode = "classic"): void {
  localStorage.removeItem(sessionKey(mode));
}

/** 读取设置并做边界校验；无有效记录时返回不可变默认值副本。 */
export function loadSettings(): GameSettings {
  return parseStored(SETTINGS_KEY, isSettings, { ...DEFAULT_SETTINGS });
}

/** 保存音频与动态效果设置；覆盖当前浏览器设置记录。 */
export function saveSettings(settings: GameSettings): void {
  localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
}

function parseStored<T>(key: string, validate: (value: unknown) => value is T, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    const value: unknown = raw ? JSON.parse(raw) : null;
    return validate(value) ? value : fallback;
  } catch {
    return fallback;
  }
}

function sessionKey(mode: RunMode): string {
  return mode === "myth_bifang" ? MYTH_BIFANG_SESSION_KEY : SESSION_KEY;
}

function isSession(value: unknown): value is StoredSession {
  if (!value || typeof value !== "object") return false;
  const session = value as Partial<StoredSession>;
  return Boolean(session.accessToken && session.runId);
}

function isSettings(value: unknown): value is GameSettings {
  if (!value || typeof value !== "object") return false;
  const settings = value as Partial<GameSettings>;
  return typeof settings.volume === "number"
    && settings.volume >= 0
    && settings.volume <= 1
    && typeof settings.muted === "boolean"
    && typeof settings.reducedMotion === "boolean";
}
