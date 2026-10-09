import type { components } from "./schema";

export type ActionRequest = components["schemas"]["ActionRequest"];
export type ArchetypeId = components["schemas"]["CreateRunRequest"]["archetype"];
export type Catalog = components["schemas"]["CatalogResponse"];
export type CreateRunResponse = components["schemas"]["CreateRunResponse"];
export type GameEvent = components["schemas"]["GameEvent"];
export type RunResponse = components["schemas"]["RunResponse"];
export type RunView = components["schemas"]["RunView"];

/** 对判别联合逐成员移除公共字段，避免普通 Omit 丢失动作变体字段。 */
export type DistributiveOmit<T, K extends PropertyKey> = T extends unknown
  ? Omit<T, K>
  : never;

/** UI 可提交的动作输入；ActionQueue 负责追加幂等编号与 revision。 */
export type ActionInput = DistributiveOmit<
  ActionRequest,
  "action_id" | "expected_revision"
>;
