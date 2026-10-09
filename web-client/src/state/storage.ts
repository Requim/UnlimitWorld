export const SESSION_KEY = "tiandao.cardRogue.session.v1";
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

/** 读取并校验匿名局面凭证；无入参，格式错误返回 null 且不抛异常。 */
export function loadSession(): StoredSession | null {
  return parseStored(SESSION_KEY, isSession, null);
}

/** 保存匿名局面凭证；覆盖当前浏览器会话记录，存储失败会抛出异常。 */
export function saveSession(session: StoredSession): void {
  localStorage.setItem(SESSION_KEY, JSON.stringify(session));
}

/** 删除已失效会话；无返回值，仅影响当前浏览器 localStorage。 */
export function clearSession(): void {
  localStorage.removeItem(SESSION_KEY);
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
