import { useLayoutEffect, useRef, useState } from "react";

import { fitBattleViewport, type BattleViewport } from "./battleLayout";

/** 观察挂载的可用区域，返回容器 ref 与等比像素尺寸；卸载断开观察，不提交游戏动作。 */
export function useBattleViewport() {
  const surfaceRef = useRef<HTMLDivElement>(null);
  const [viewport, setViewport] = useState<BattleViewport>({ width: 0, height: 0 });
  useLayoutEffect(() => {
    const surface = surfaceRef.current;
    if (!surface) return;
    const update = () => {
      const next = fitBattleViewport(surface.getBoundingClientRect());
      setViewport((current) => current.width === next.width && current.height === next.height ? current : next);
    };
    update();
    const observer = new ResizeObserver(update);
    observer.observe(surface);
    return () => observer.disconnect();
  }, []);
  return { surfaceRef, viewport };
}
