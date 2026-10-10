import type { MythClipKey } from "./mythAnimation";

interface AnimationActor {
  play: (key: string) => unknown;
  once: (event: string, listener: () => void) => unknown;
  off: (event: string, listener: () => void) => unknown;
}

/** 单段真实序列帧的完成结果；取消表示调用方不得继续该事件的后续片段。 */
export type MythPlaybackResult = "completed" | "cancelled";
/** 登记可取消资源并返回反登记函数，用于场景 destroy 和设置切换。 */
export type TrackMythCancellation = (cancel: () => void) => () => void;

/** 播放指定 Phaser 动作并等待其精确完成事件；取消会解绑所有旧回调。 */
export function waitForMythAnimation(actor: AnimationActor, key: MythClipKey,
  signal: AbortSignal, track: TrackMythCancellation): Promise<MythPlaybackResult> {
  if (signal.aborted) return Promise.resolve("cancelled");
  return new Promise((resolve, reject) => {
    const event = `animationcomplete-${key}`;
    let release: () => void = () => undefined;
    let settled = false;
    const finish = (result: MythPlaybackResult) => {
      if (settled) return;
      settled = true;
      actor.off(event, complete);
      signal.removeEventListener("abort", cancel);
      release();
      resolve(result);
    };
    const complete = () => finish("completed");
    const cancel = () => finish("cancelled");
    actor.once(event, complete);
    signal.addEventListener("abort", cancel, { once: true });
    release = track(cancel);
    try { actor.play(key); } catch (cause) {
      actor.off(event, complete);
      signal.removeEventListener("abort", cancel);
      release();
      reject(cause);
    }
  });
}

/** 判断完成后必须停在末帧的终局动作，防止结算前闪回待机。 */
export function isTerminalMythClip(key: MythClipKey): boolean {
  return key === "hero_defeat" || key === "bifang_retreat";
}
