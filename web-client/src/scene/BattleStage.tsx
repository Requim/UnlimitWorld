import { ImageOff, RefreshCw } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";

import type { GameEvent, RunView } from "../api/types";
import type { AssetState } from "../game/useAssets";
import { BattleSceneRuntime, type BattleSnapshot } from "./battleRuntime";
import { useBattleViewport } from "./useBattleViewport";

interface BattleStageProps {
  combat: NonNullable<RunView["combat"]>;
  events: GameEvent[];
  revision: number;
  assets: AssetState;
  reducedMotion: boolean;
  onRetry: () => void;
  info?: ReactNode;
  children?: ReactNode;
}

/** 输入只读局面及 DOM 信息/命中层，返回同坐标战场；卸载销毁 Phaser，资源失败提供 onRetry。 */
export function BattleStage(props: BattleStageProps) {
  const hostRef = useRef<HTMLDivElement>(null);
  const { surfaceRef, viewport } = useBattleViewport();
  const latestRef = useRef<BattleSnapshot>(toSnapshot(props));
  const runtimeRef = useRef<BattleSceneRuntime | null>(null);
  if (!runtimeRef.current) runtimeRef.current = new BattleSceneRuntime(latestRef.current);
  const [runtimeError, setRuntimeError] = useState<string | null>(null);
  latestRef.current = toSnapshot(props);
  useEffect(() => runtimeRef.current?.update(latestRef.current), [props.combat, props.events, props.reducedMotion, props.revision]);
  useEffect(() => {
    let cancelled = false;
    if (!hostRef.current) return;
    setRuntimeError(null);
    void import("./createBattleGame").then(({ createBattleGame }) => {
      if (cancelled || !hostRef.current) return;
      const adapter = createBattleGame(hostRef.current, latestRef.current, props.assets, setRuntimeError);
      runtimeRef.current?.attach(adapter);
    }).catch((error: unknown) => !cancelled && setRuntimeError(error instanceof Error ? error.message : "战场启动失败"));
    return () => { cancelled = true; runtimeRef.current?.detach(); };
  }, [props.combat.enemy.id, props.assets.manifest, props.assets.status]);
  const retry = () => { setRuntimeError(null); props.onRetry(); };
  return (
    <div className="battle-stage">
      <div className="battle-hud">
        <AssetNotice assets={props.assets} runtimeError={runtimeError} onRetry={retry} />
        {props.info}
      </div>
      <div className="battle-surface" ref={surfaceRef}>
        <div className="battle-viewport" data-testid="battle-viewport" style={viewport}>
          <div className="phaser-host" ref={hostRef} aria-label="技术战场画面" />
          {props.children}
        </div>
      </div>
    </div>
  );
}

function toSnapshot(props: BattleStageProps): BattleSnapshot {
  return { combat: props.combat, events: props.events, revision: props.revision, reducedMotion: props.reducedMotion };
}

function AssetNotice({ assets, runtimeError, onRetry }: { assets: AssetState; runtimeError: string | null; onRetry: () => void }) {
  if (assets.status === "ready" && !runtimeError) return null;
  const message = runtimeError ?? assets.message ?? (assets.status === "loading" ? "正在读取资源清单" : "正式美术资源不可用");
  return (
    <div className="asset-notice"><ImageOff /><span><b>技术画面模式</b>{message}</span>
      <button data-testid="retry-assets" onClick={onRetry} title="重试加载美术资源"><RefreshCw /></button>
    </div>
  );
}
