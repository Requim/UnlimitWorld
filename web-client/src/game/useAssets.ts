import { useCallback, useEffect, useState } from "react";

/** public/assets 的稳定资源键清单；ready 前不得把路径当作可用美术。 */
export interface AssetManifest {
  version: number;
  status: "ready" | "pending-generation";
  reason?: string;
  characters: Record<string, string>;
  enemies: Record<string, string>;
  backgrounds: Record<string, string>;
  cards: Record<string, string>;
}

/** manifest 加载状态；pending 与 error 都要求 UI 明示并允许重试。 */
export interface AssetState {
  status: "loading" | "ready" | "pending" | "error";
  manifest: AssetManifest | null;
  message: string | null;
}

/** 读取统一美术 manifest；支持显式重试，不把待生成状态伪装为成功。 */
export function useAssets(): [AssetState, () => void] {
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<AssetState>({ status: "loading", manifest: null, message: null });
  useEffect(() => {
    let active = true;
    setState({ status: "loading", manifest: null, message: null });
    fetch(`/assets/manifest.json?attempt=${attempt}`)
      .then((response) => response.ok ? response.json() : Promise.reject(new Error(`资源清单 ${response.status}`)))
      .then((manifest: AssetManifest) => active && setState(toAssetState(manifest)))
      .catch((error: unknown) => active && setState({ status: "error", manifest: null, message: errorMessage(error) }));
    return () => { active = false; };
  }, [attempt]);
  const retry = useCallback(() => setAttempt((value) => value + 1), []);
  return [state, retry];
}

function toAssetState(manifest: AssetManifest): AssetState {
  if (manifest.status === "ready") return { status: "ready", manifest, message: null };
  return { status: "pending", manifest, message: manifest.reason ?? "原创位图仍待生成" };
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "资源清单加载失败";
}
