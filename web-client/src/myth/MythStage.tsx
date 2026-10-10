import { RefreshCw } from "lucide-react";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import type { MythAssets } from "./mythAssets";
import { mythLayout } from "./mythLayout";
import type { MythSceneAdapter } from "./createMythGame";
import type { PresentationAdapter } from "./presentationQueue";

interface Props {
  assets: MythAssets; enabled: boolean; onTarget: () => void; onRetry: () => void;
  onAdapter: (adapter: PresentationAdapter | null) => void; reducedMotion: boolean;
}

/** 全景战场与同源 DOM 目标；资源变化/卸载销毁 scene，迟到 import 不再附着，不发网络命令。 */
export function MythStage(props: Props) {
  const host = useRef<HTMLDivElement>(null);
  const runtime = useRef<MythSceneAdapter | null>(null);
  const [bounds, setBounds] = useState({ width: 0, height: 0 });
  const [error, setError] = useState<string | null>(null);
  const boundsRef = useRef(bounds);
  const reducedMotionRef = useRef(props.reducedMotion);
  boundsRef.current = bounds;
  reducedMotionRef.current = props.reducedMotion;
  useLayoutEffect(() => {
    if (!host.current) return;
    const update = () => {
      const rect = host.current!.getBoundingClientRect();
      setBounds({ width: rect.width, height: rect.height });
    };
    update();
    return observeSize(host.current, update);
  }, []);
  useEffect(() => {
    let cancelled = false;
    const manifest = props.assets.manifest;
    setError(null);
    if (props.assets.status !== "ready" || !manifest || !host.current) return;
    void import("./createMythGame").then(({ createMythGame }) => {
      if (cancelled || !host.current) return;
      runtime.current = createMythGame(host.current, manifest, boundsRef.current.width, boundsRef.current.height,
        reducedMotionRef.current,
        (adapter) => {
          if (cancelled) return;
          adapter.setReducedMotion(reducedMotionRef.current);
          props.onAdapter(adapter.present);
        },
        (message) => { if (!cancelled) { setError(message); props.onAdapter(null); } });
    }).catch((cause: unknown) => {
      if (!cancelled) { setError(cause instanceof Error ? cause.message : "战场加载失败"); props.onAdapter(null); }
    });
    return () => { cancelled = true; props.onAdapter(null); runtime.current?.destroy(); runtime.current = null; };
  }, [props.assets.manifest, props.assets.status, props.onAdapter]);
  useEffect(() => runtime.current?.resize(bounds.width, bounds.height), [bounds]);
  useEffect(() => runtime.current?.setReducedMotion(props.reducedMotion), [props.reducedMotion]);
  const manifest = props.assets.manifest;
  const layout = mythLayout(bounds.width, bounds.height, manifest?.seeds.hero, manifest?.seeds.bifang);
  return <div className="myth-stage" data-testid="myth-stage">
    <div className="myth-canvas" ref={host} aria-label="章莪山·毕方战场" />
    <button data-testid="enemy-target" className="myth-target" style={layout.target}
      disabled={!props.enabled || Boolean(error)} onClick={props.onTarget} aria-label="对毕方打出所选卡牌" title="毕方" />
    {(error || props.assets.status !== "ready") && <div className="myth-asset-error" role="status">
      <span>{error ?? props.assets.error ?? "正在读取神话素材"}</span>
      <button data-testid="retry-assets" title="重试加载神话素材" onClick={props.onRetry}><RefreshCw /></button>
    </div>}
  </div>;
}

function observeSize(element: HTMLElement, update: () => void): () => void {
  if (typeof ResizeObserver !== "undefined") {
    const observer = new ResizeObserver(update);
    observer.observe(element);
    return () => observer.disconnect();
  }
  window.addEventListener("resize", update);
  return () => window.removeEventListener("resize", update);
}
