import { useEffect } from "react";

import type { GameEvent } from "../api/types";
import type { GameSettings } from "../state/storage";

/** 返回事件对应的技术提示音频率；未知事件使用中性确认音。 */
export function toneForEvent(kind: string): number {
  if (kind.includes("thunder")) return 95;
  if (kind.includes("damage") || kind.includes("attack")) return 170;
  if (kind.includes("reward") || kind.includes("purchase") || kind.includes("completed")) return 520;
  if (kind.includes("block") || kind.includes("heal")) return 360;
  return 260;
}

/** 按服务端表现事件播放短促提示音；静音时无副作用，浏览器拒绝音频时静默降级。 */
export function useEventAudio(events: GameEvent[], settings: GameSettings): void {
  useEffect(() => {
    if (!events.length || settings.muted || settings.volume <= 0) return;
    const AudioContextType = window.AudioContext;
    if (!AudioContextType) return;
    const context = new AudioContextType();
    const oscillator = context.createOscillator();
    const gain = context.createGain();
    oscillator.frequency.value = toneForEvent(events.at(-1)?.kind ?? "");
    gain.gain.value = settings.volume * 0.08;
    oscillator.connect(gain).connect(context.destination);
    oscillator.start();
    oscillator.stop(context.currentTime + 0.12);
    oscillator.addEventListener("ended", () => void context.close());
  }, [events, settings.muted, settings.volume]);
}
