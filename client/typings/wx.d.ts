/**
 * 微信小程序 API 类型补充声明
 *
 * 补充 @types/wechat-miniprogram 中缺失或不完整的类型定义。
 */

declare namespace WechatMiniprogram {
  interface SocketTask {
    /** WebSocket 连接已打开 */
    onOpen(callback: (res: { header: Record<string, string> }) => void): void;
    /** 收到服务端消息 */
    onMessage(callback: (res: SocketMessage) => void): void;
    /** WebSocket 连接关闭 */
    onClose(callback: (res: { code: number; reason: string }) => void): void;
    /** WebSocket 错误 */
    onError(callback: (res: { errMsg: string }) => void): void;
    /** 发送数据 */
    send(opts: { data: string | ArrayBuffer; success?: () => void; fail?: (err: { errMsg: string }) => void }): void;
    /** 关闭连接 */
    close(opts?: { code?: number; reason?: string; success?: () => void; fail?: (err: { errMsg: string }) => void }): void;
  }

  interface SocketMessage {
    data: string | ArrayBuffer;
  }

  /** wx.connectSocket 参数 */
  interface ConnectSocketOption {
    url: string;
    header?: Record<string, string>;
    protocols?: string[];
    tcpNoDelay?: boolean;
    perMessageDeflate?: boolean;
    timeout?: number;
    success?: () => void;
    fail?: (err: { errMsg: string }) => void;
    complete?: () => void;
  }

  /** wx.connectSocket */
  function connectSocket(option: ConnectSocketOption): SocketTask;

  /** wx.sendSocketMessage */
  interface SendSocketMessageOption {
    data: string | ArrayBuffer;
    success?: () => void;
    fail?: (err: { errMsg: string }) => void;
  }

  /** wx.closeSocket */
  interface CloseSocketOption {
    code?: number;
    reason?: string;
    success?: () => void;
    fail?: (err: { errMsg: string }) => void;
  }
}
