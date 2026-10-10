import { useEffect, useRef, useState } from "react";
import type { GameEvent, RunView } from "../api/types";
import { PresentationQueue, type PresentationAdapter, type PresentationCallbacks } from "./presentationQueue";

interface DisplayState { run: RunView | null; busy: boolean; error: string | null }
interface Bridge {
  queue: PresentationQueue | null;
  displayed: RunView | null;
  authority: RunView | null;
  adapter: PresentationAdapter | null;
  resync: () => Promise<void>;
  publish: (state: DisplayState) => void;
}

/** 输入权威响应和可取消 adapter，返回展示局面与独立表现锁；恢复只调用 resync。 */
export function useMythPresentation(run: RunView | null, events: GameEvent[],
  adapter: PresentationAdapter | null, resync: () => Promise<void>) {
  const [state, setState] = useState<DisplayState>({ run, busy: false, error: null });
  const bridge = useRef<Bridge>({ queue: null, displayed: run, authority: run, adapter, resync, publish: setState });
  const adapterAvailable = adapter !== null;
  bridge.current.authority = run;
  bridge.current.adapter = adapter;
  bridge.current.resync = resync;
  useEffect(() => {
    const current = bridge.current;
    current.queue = new PresentationQueue((event, signal) => presentCurrent(current, event, signal), callbacks(current));
    return () => { current.queue?.dispose(); current.queue = null; };
  }, []);
  useEffect(() => {
    const current = bridge.current;
    if (adapterAvailable) return;
    current.displayed = current.authority;
    current.queue?.cancel();
    current.publish({ run: current.displayed, busy: false, error: null });
  }, [adapterAvailable]);
  useEffect(() => presentResponse(bridge.current, run, events), [run, events, adapterAvailable]);
  const visible = state.run?.run_id === run?.run_id ? state.run : run;
  const awaiting = Boolean(adapterAvailable && run && visible && run.revision !== visible.revision && events.length);
  return { ...state, run: visible, busy: state.busy || awaiting };
}

function presentCurrent(bridge: Bridge, event: GameEvent, signal: AbortSignal): Promise<void> {
  return bridge.adapter ? bridge.adapter(event, signal) : Promise.resolve();
}

function callbacks(bridge: Bridge): PresentationCallbacks {
  return {
    onBusyChange: (busy) => bridge.publish({ run: bridge.displayed, busy, error: null }),
    onStateAfter: (snapshot) => {
      const run = bridge.displayed;
      if (!run?.combat) return;
      bridge.displayed = { ...run, player: { ...run.player, ...snapshot.player },
        combat: { ...run.combat, enemy: { ...run.combat.enemy, ...snapshot.enemy },
          turn: snapshot.turn ?? run.combat.turn, energy: snapshot.energy ?? run.combat.energy } };
      bridge.publish({ run: bridge.displayed, busy: true, error: null });
    },
    onComplete: () => synchronizeDisplay(bridge),
    onError: (cause) => {
      bridge.displayed = bridge.authority;
      bridge.publish({ run: bridge.authority, busy: false, error: cause instanceof Error ? cause.message : "演出中断" });
      void bridge.resync();
    },
  };
}

function presentResponse(bridge: Bridge, run: RunView | null, events: GameEvent[]): void {
  if (run?.run_id !== bridge.displayed?.run_id) {
    bridge.queue?.cancel();
    synchronizeDisplay(bridge);
    return;
  }
  if (!run || !bridge.displayed?.combat || events.length === 0 || !bridge.adapter) {
    synchronizeDisplay(bridge);
    return;
  }
  if (run.revision === bridge.displayed.revision) return;
  void bridge.queue?.enqueue({ runId: run.run_id, revision: run.revision, events }).catch(() => undefined);
}

function synchronizeDisplay(bridge: Bridge): void {
  bridge.displayed = bridge.authority;
  bridge.publish({ run: bridge.displayed, busy: false, error: null });
}
