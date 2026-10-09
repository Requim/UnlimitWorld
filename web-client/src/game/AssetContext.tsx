import { createContext, useContext, type ReactNode } from "react";

import type { AssetState } from "./useAssets";

const EMPTY_ASSETS: AssetState = { status: "loading", manifest: null, message: null };
interface AssetContextValue {
  state: AssetState;
  retry: (() => void) | null;
}

const AssetContext = createContext<AssetContextValue>({ state: EMPTY_ASSETS, retry: null });

/** 提供已校验资源状态和统一重试命令；retry 会重新请求 manifest。 */
export function AssetProvider({ state, retry = null, children }: {
  state: AssetState;
  retry?: (() => void) | null;
  children: ReactNode;
}) {
  return <AssetContext.Provider value={{ state, retry }}>{children}</AssetContext.Provider>;
}

/** 读取已校验资源状态；无 Provider 时返回 loading 状态且不抛异常。 */
export function useAssetState(): AssetState {
  return useContext(AssetContext).state;
}

/** 读取统一资源重试命令；无 Provider 时返回 null。 */
export function useAssetRetry(): (() => void) | null {
  return useContext(AssetContext).retry;
}
