import type { components } from "./schema";

export type ActionRequest = components["schemas"]["ActionRequest"];
type GeneratedCreateRunRequest = components["schemas"]["CreateRunRequest"];

/** 创建局面的请求输入；服务端在 mode 缺失时使用 classic。 */
export type CreateRunInput = Omit<GeneratedCreateRunRequest, "mode"> & {
  mode?: GeneratedCreateRunRequest["mode"];
};

/** 服务端正式支持的局面模式；直接派生自创建请求，避免客户端枚举漂移。 */
export type RunMode = Exclude<CreateRunInput["mode"], undefined>;
export type ArchetypeId = CreateRunInput["archetype"];
export type Catalog = components["schemas"]["CatalogResponse"];
export type GameEvent = components["schemas"]["GameEvent"];
type GeneratedRunView = components["schemas"]["RunView"];

/** 兼容旧局面夹具；服务端读取缺失 mode 时会规范化为 classic。 */
export type RunView = Omit<GeneratedRunView, "mode"> & {
  mode?: GeneratedRunView["mode"];
};

export type CreateRunResponse = Omit<
  components["schemas"]["CreateRunResponse"],
  "run"
> & { run: RunView };
export type RunResponse = Omit<components["schemas"]["RunResponse"], "run"> & {
  run: RunView;
};

/** 对判别联合逐成员移除公共字段，避免普通 Omit 丢失动作变体字段。 */
export type DistributiveOmit<T, K extends PropertyKey> = T extends unknown
  ? Omit<T, K>
  : never;

/** UI 可提交的动作输入；ActionQueue 负责追加幂等编号与 revision。 */
export type ActionInput = DistributiveOmit<
  ActionRequest,
  "action_id" | "expected_revision"
>;
