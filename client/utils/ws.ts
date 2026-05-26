/**
 * WebSocket 单例管理器
 *
 * 封装原生 wx.connectSocket，提供全局可调用的 send() / onMessage()。
 * 职责：连接建立、心跳维持、固定延迟重连、消息分发、DEBUG 日志。
 */

import { CS_PING } from './actions';
import { WS_CONNECT_TIMEOUT, WS_URL } from './config';

/* ── 常量 ── */
const HEARTBEAT_INTERVAL = 10_000;   // M3：心跳间隔 10s
const RECONNECT_DELAY = 3_000;       // M3：断线后 3s 固定重连
const DEBUG = true;                  // 日志开关

/* ── 类型 ── */

type ConnectionStatus = 'connecting' | 'connected' | 'closed';

export interface WsFrame {
  action: string;
  [key: string]: unknown;
}

export type MessageCallback = (frame: WsFrame) => void;

/* ── WsManager ── */

export class WsManager {
  private _socket: WechatMiniprogram.SocketTask | null = null;
  private _listeners: MessageCallback[] = [];
  private _reconnectAttempts = 0;
  private _heartbeatTimer: number | null = null;
  private _reconnectTimer: number | null = null;
  private _connectTimer: number | null = null;
  private _url = '';
  private _playerId = '';
  private _status: ConnectionStatus = 'closed';

  /* ═══════════════════════════════════════════
   * 公开 API
   * ═══════════════════════════════════════════ */

  /** 建立 WebSocket 连接 */
  connect(playerId: string): void {
    if (this._status === 'connected' || this._status === 'connecting') {
      this._log('已在连接中，跳过重复 connect');
      return;
    }

    this._playerId = playerId;
    this._url = `${WS_URL}?player_id=${playerId}`;
    this._status = 'connecting';

    this._log(`连接中... ${this._url}`);

    this._socket = wx.connectSocket({
      url: this._url,
      tcpNoDelay: true,
      timeout: WS_CONNECT_TIMEOUT,
      fail: (err: { errMsg: string }) => {
        this._log(`连接失败: ${err.errMsg}`);
        this._status = 'closed';
        this._scheduleReconnect();
      },
    });

    this._socket.onOpen(() => {
      this._log('WebSocket 已连接');
      this._status = 'connected';
      this._reconnectAttempts = 0;
      this._startHeartbeat();
    });

    this._socket.onMessage((res: WechatMiniprogram.SocketMessage) => {
      this._onMessage(res);
    });

    this._socket.onClose((res: { code: number; reason: string }) => {
      this._log(`连接关闭 code=${res.code} reason=${res.reason}`);
      this._onDisconnected();
    });

    this._socket.onError((res: { errMsg: string }) => {
      this._log(`连接错误: ${res.errMsg}`);
      this._onDisconnected();
    });
  }

  /** 发送上行帧 */
  send(action: string, data: Record<string, unknown> = {}): void {
    if (!this._socket || this._status !== 'connected') {
      this._log(`send 失败：未连接 (action=${action})`);
      return;
    }

    const frame: WsFrame = { action, ...data };
    const raw = JSON.stringify(frame);

    this._socket.send({
      data: raw,
      fail: (err: { errMsg: string }) => {
        this._log(`发送失败: ${err.errMsg}`);
      },
    });
  }

  /** 注册消息监听，返回取消订阅函数 */
  onMessage(cb: MessageCallback): () => void {
    this._listeners.push(cb);
    return () => {
      const idx = this._listeners.indexOf(cb);
      if (idx >= 0) this._listeners.splice(idx, 1);
    };
  }

  /** 获取连接状态 */
  getStatus(): ConnectionStatus {
    return this._status;
  }

  /** 获取当前 playerId */
  getPlayerId(): string {
    return this._playerId;
  }

  /** 关闭连接并清理所有资源 */
  close(): void {
    this._log('主动关闭连接');
    this._clearTimers();
    this._listeners = [];
    this._status = 'closed';

    if (this._socket) {
      try {
        this._socket.close({ code: 1000, reason: '客户端主动关闭' });
      } catch (_) {
        /* 忽略关闭异常 */
      }
      this._socket = null;
    }
  }

  /* ═══════════════════════════════════════════
   * 内部方法
   * ═══════════════════════════════════════════ */

  /** 收到消息 → 解析 JSON → 分发到所有监听器 */
  private _onMessage(res: WechatMiniprogram.SocketMessage): void {
    let frame: WsFrame;
    try {
      frame = JSON.parse(res.data as string) as WsFrame;
    } catch (_) {
      this._log(`消息解析失败: ${String(res.data).slice(0, 80)}`);
      return;
    }

    this._log(`← ${frame.action}`);

    for (const cb of this._listeners) {
      try {
        cb(frame);
      } catch (e) {
        this._log(`监听器回调异常: ${String(e)}`);
      }
    }
  }

  /** 连接断开后的统一处理 */
  private _onDisconnected(): void {
    this._clearTimers();
    this._status = 'closed';
    this._scheduleReconnect();
  }

  /** 启动心跳定时器 */
  private _startHeartbeat(): void {
    if (this._heartbeatTimer !== null) return;

    this._heartbeatTimer = setInterval(() => {
      if (this._status === 'connected') {
        this.send(CS_PING, {});
      }
    }, HEARTBEAT_INTERVAL) as unknown as number;
  }

  /** 固定 3s 重连 */
  private _scheduleReconnect(): void {
    if (this._reconnectTimer !== null) return;

    this._reconnectAttempts += 1;

    this._log(`${RECONNECT_DELAY / 1000}s 后进行第 ${this._reconnectAttempts} 次重连`);

    this._reconnectTimer = setTimeout(() => {
      this._reconnectTimer = null;
      if (this._playerId) {
        this.connect(this._playerId);
      }
    }, RECONNECT_DELAY) as unknown as number;
  }

  /** 清理所有定时器 */
  private _clearTimers(): void {
    if (this._heartbeatTimer !== null) {
      clearInterval(this._heartbeatTimer);
      this._heartbeatTimer = null;
    }
    if (this._reconnectTimer !== null) {
      clearTimeout(this._reconnectTimer);
      this._reconnectTimer = null;
    }
  }

  /** 条件日志输出 */
  private _log(msg: string): void {
    if (DEBUG) {
      console.log(`[WsManager] ${msg}`);
    }
  }
}
