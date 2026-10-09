import { createContext, useContext, type ReactNode } from "react";

import type { AssetState } from "./useAssets";

const EMPTY_ASSETS: AssetState = { status: "loading", manifest: null, message: null };
const AssetContext = createContext<AssetState>(EMPTY_ASSETS);

/** 向卡牌等 DOM 组件提供已校验资源状态；仅传递只读上下文。 */
export function AssetProvider({ state, children }: { state: AssetState; children: ReactNode }) {
  return <AssetContext.Provider value={state}>{children}</AssetContext.Provider>;
}

/** 读取已校验资源状态；无 Provider 时返回 loading 状态且不抛异常。 */
export function useAssetState(): AssetState {
  return useContext(AssetContext);
}
