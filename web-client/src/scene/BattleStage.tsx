import { ImageOff, RefreshCw } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import type { GameEvent, RunView } from "../api/types";
import type { AssetState } from "../game/useAssets";

interface BattleStageProps {
  combat: NonNullable<RunView["combat"]>;
  events: GameEvent[];
  assets: AssetState;
  reducedMotion: boolean;
  onRetry: () => void;
}

/** 承载 Phaser 技术战场；规则与胜负始终来自服务端 RunView。 */
export function BattleStage(props: BattleStageProps) {
  const hostRef = useRef<HTMLDivElement>(null);
  const gameRef = useRef<{ destroy: (removeCanvas: boolean) => void } | null>(null);
  const [runtimeError, setRuntimeError] = useState<string | null>(null);
  useEffect(() => {
    let cancelled = false;
    if (!hostRef.current) return;
    void import("./createBattleGame").then(({ createBattleGame }) => {
      if (cancelled || !hostRef.current) return;
      gameRef.current = createBattleGame(hostRef.current, props.combat, props.assets, props.events, props.reducedMotion, setRuntimeError);
    }).catch((error: unknown) => setRuntimeError(error instanceof Error ? error.message : "战场启动失败"));
    return () => { cancelled = true; gameRef.current?.destroy(true); gameRef.current = null; };
  }, [props.combat.enemy.id, props.assets.manifest, props.reducedMotion]);
  return (
    <div className="battle-stage">
      <div className="phaser-host" ref={hostRef} aria-label="技术战场画面" />
      <AssetNotice assets={props.assets} runtimeError={runtimeError} onRetry={props.onRetry} />
    </div>
  );
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
