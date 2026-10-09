import type {
  ActionRequest,
  ArchetypeId,
  Catalog,
  CreateRunResponse,
  RunResponse,
} from "./types";

const API_ROOT = import.meta.env.VITE_API_URL ?? "";

/** 携带 HTTP 失败状态；401/404/409/422 是明确拒绝，其余失败可能仍已提交。 */
export class ApiError extends Error {
  public constructor(public readonly status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

/** 输入请求失败原因，返回动作结果是否未知；仅本 API 明确拒绝可安全解除幂等锁，无副作用。 */
export function isUnknownActionOutcome(cause: unknown): boolean {
  return !(cause instanceof ApiError && [401, 404, 409, 422].includes(cause.status));
}

/** 读取卡牌、敌人、法宝与流派目录；HTTP 错误抛 ApiError。 */
export function getCatalog(): Promise<Catalog> {
  return request<Catalog>("/api/v2/catalog");
}

/** 创建新局；可传旧 token 继承本机因果，成功返回新的局面与凭证。 */
export function createRun(archetype: ArchetypeId, token?: string): Promise<CreateRunResponse> {
  return request<CreateRunResponse>("/api/v2/runs", {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify({ archetype }),
  });
}

/** 读取 Bearer 所属局面；401/404/网络失败均向调用方抛出。 */
export function getRun(runId: string, token: string): Promise<RunResponse> {
  return request<RunResponse>(`/api/v2/runs/${runId}`, {
    headers: authHeaders(token),
  });
}

/** 提交已带幂等编号的动作；不会自行重试，避免改变未知结果语义。 */
export function sendAction(
  runId: string,
  token: string,
  action: ActionRequest,
): Promise<RunResponse> {
  return request<RunResponse>(`/api/v2/runs/${runId}/actions`, {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify(action),
  });
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_ROOT}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init.headers },
  });
  if (!response.ok) throw await createApiError(response);
  return response.json() as Promise<T>;
}

function authHeaders(token?: string): HeadersInit {
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function createApiError(response: Response): Promise<ApiError> {
  try {
    const body = await response.json() as { detail?: string };
    return new ApiError(response.status, body.detail ?? `请求失败（${response.status}）`);
  } catch {
    return new ApiError(response.status, `请求失败（${response.status}）`);
  }
}
