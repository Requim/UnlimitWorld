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

/** ready 清单必须包含的全部卡牌资源键。 */
export const REQUIRED_CARD_ASSETS = [
  "flying_sword", "guard", "focus", "charge_sword", "flurry", "sword_draw",
  "myriad_swords", "hidden_edge", "fire_seed", "fan_flames", "burn_heaven",
  "borrow_fire", "embers", "golden_bell", "demon_mirror", "silence_talisman",
  "swift_script", "lightning_talisman",
] as const;

/** ready 清单必须包含的全部敌人资源键。 */
export const REQUIRED_ENEMY_ASSETS = [
  "paper_soldier", "incense_guest", "fallen_monk", "debt_immortal",
  "heaven_tax_collector", "heaven_judge",
] as const;

/** 读取统一美术 manifest；支持显式重试，不把待生成状态伪装为成功。 */
export function useAssets(): [AssetState, () => void] {
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<AssetState>({ status: "loading", manifest: null, message: null });
  useEffect(() => {
    let active = true;
    setState({ status: "loading", manifest: null, message: null });
    fetch(`/assets/manifest.json?attempt=${attempt}`)
      .then((response) => response.ok ? response.json() : Promise.reject(new Error(`资源清单 ${response.status}`)))
      .then((manifest: unknown) => active && setState(resolveAssetManifest(manifest)))
      .catch((error: unknown) => active && setState({ status: "error", manifest: null, message: errorMessage(error) }));
    return () => { active = false; };
  }, [attempt]);
  const retry = useCallback(() => setAttempt((value) => value + 1), []);
  return [state, retry];
}

/** 校验资源清单；ready 缺少任一必需键时返回显式 error。 */
export function resolveAssetManifest(value: unknown): AssetState {
  if (!isAssetManifest(value)) return { status: "error", manifest: null, message: "资源清单格式无效" };
  const manifest = value;
  if (manifest.status === "ready") {
    const missing = missingAssetKeys(manifest);
    if (missing.length) return { status: "error", manifest: null, message: `资源清单缺少：${missing.join("、")}` };
    return { status: "ready", manifest, message: null };
  }
  return { status: "pending", manifest, message: manifest.reason ?? "原创位图仍待生成" };
}

function isAssetManifest(value: unknown): value is AssetManifest {
  if (!value || typeof value !== "object") return false;
  const manifest = value as Partial<AssetManifest>;
  if (manifest.status !== "ready" && manifest.status !== "pending-generation") return false;
  if (!isRecord(manifest.characters) || !isRecord(manifest.enemies)
    || !isRecord(manifest.backgrounds) || !isRecord(manifest.cards)) return false;
  return true;
}

function missingAssetKeys(manifest: AssetManifest): string[] {
  const groups: Array<[string, Record<string, string>, readonly string[]]> = [
    ["characters", manifest.characters, ["cultivator"]],
    ["backgrounds", manifest.backgrounds, ["battle", "boss"]],
    ["enemies", manifest.enemies, REQUIRED_ENEMY_ASSETS],
    ["cards", manifest.cards, REQUIRED_CARD_ASSETS],
  ];
  return groups.flatMap(([name, entries, keys]) => keys.filter((key) => !entries[key]).map((key) => `${name}.${key}`));
}

function isRecord(value: unknown): value is Record<string, string> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "资源清单加载失败";
}
