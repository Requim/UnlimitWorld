import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

import * as client from "../api/client";
import { ApiError } from "../api/client";
import type { CreateRunResponse, RunMode, RunResponse } from "../api/types";
import { loadSession, saveSession } from "../state/storage";
import { deferred } from "../test/deferred";
import { makeCatalog, makeRun } from "../test/fixtures";
import { useGameSession } from "./useGameSession";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return { ...actual, getCatalog: vi.fn(), createRun: vi.fn(), getRun: vi.fn(), sendAction: vi.fn() };
});

const oldRun = makeRun({ run_id: "old-run", revision: 1 });
const newRun = makeRun({ run_id: "new-run", revision: 0 });
const created: CreateRunResponse = { run: newRun, events: [], access_token: "token" };

beforeEach(() => {
  vi.resetAllMocks();
  localStorage.clear();
  vi.mocked(client.getCatalog).mockResolvedValue(makeCatalog());
  vi.mocked(client.getRun).mockResolvedValue({ run: oldRun, events: [] });
  vi.mocked(client.createRun).mockResolvedValue(created);
});

it("StrictMode 清理后的旧初始化不能覆盖已创建的新局", async () => {
  saveSession({ accessToken: "token", runId: oldRun.run_id });
  const catalog = deferred<Awaited<ReturnType<typeof client.getCatalog>>>();
  vi.mocked(client.getCatalog).mockReturnValueOnce(catalog.promise).mockResolvedValueOnce(makeCatalog());
  const hook = renderHook(useGameSession, { reactStrictMode: true });
  await waitFor(() => expect(hook.result.current.run?.run_id).toBe(oldRun.run_id));
  await act(() => hook.result.current.startRun("sword"));
  await act(async () => catalog.resolve(makeCatalog()));

  expect(hook.result.current.run?.run_id).toBe(newRun.run_id);
  expect(hook.result.current.status).toBe("ready");
});

it("新局成功后忽略仍在途的旧档案 GET", async () => {
  saveSession({ accessToken: "token", runId: oldRun.run_id });
  const restore = deferred<RunResponse>();
  vi.mocked(client.getRun).mockReturnValueOnce(restore.promise);
  const hook = renderHook(useGameSession);
  await waitFor(() => expect(client.getRun).toHaveBeenCalled());
  await act(() => hook.result.current.startRun("sword"));
  await act(async () => restore.resolve({ run: { ...oldRun, phase: "completed" }, events: [] }));

  expect(hook.result.current.run?.run_id).toBe(newRun.run_id);
  expect(hook.result.current.run?.phase).toBe("map");
});

it.each([new ApiError(401, "旧档案失效"), new TypeError("旧初始化断网")])(
  "旧初始化失败不能改变新局状态 %s", async (cause) => {
    saveSession({ accessToken: "token", runId: oldRun.run_id });
    const restore = deferred<RunResponse>();
    vi.mocked(client.getRun).mockReturnValueOnce(restore.promise);
    const hook = renderHook(useGameSession);
    await waitFor(() => expect(client.getRun).toHaveBeenCalled());
    await act(() => hook.result.current.startRun("sword"));
    await act(async () => restore.reject(cause));

    expect(hook.result.current.run?.run_id).toBe(newRun.run_id);
    expect(hook.result.current.status).toBe("ready");
    expect(hook.result.current.error).toBeNull();
    expect(hook.result.current.uncertain).toBe(false);
  },
);

it("旧 create 失败不能覆盖后一次成功 create", async () => {
  const oldCreate = deferred<CreateRunResponse>();
  vi.mocked(client.createRun).mockReturnValueOnce(oldCreate.promise).mockResolvedValueOnce(created);
  const hook = renderHook(useGameSession);
  await waitFor(() => expect(hook.result.current.status).toBe("ready"));
  let first!: Promise<void>;
  act(() => { first = hook.result.current.startRun("fire"); });
  await act(() => hook.result.current.startRun("sword"));
  await act(async () => { oldCreate.reject(new ApiError(401, "旧 create 拒绝")); await first; });

  expect(hook.result.current.run?.run_id).toBe(newRun.run_id);
  expect(hook.result.current.status).toBe("ready");
  expect(hook.result.current.error).toBeNull();
});

it.each(["success", "rejection"] as const)("旧动作 %s 的 finally 不得解锁新 create", async (outcome) => {
  const oldAction = deferred<RunResponse>();
  const nextCreate = deferred<CreateRunResponse>();
  vi.mocked(client.sendAction).mockReturnValueOnce(oldAction.promise);
  vi.mocked(client.createRun).mockResolvedValueOnce({ ...created, run: oldRun }).mockReturnValueOnce(nextCreate.promise);
  const hook = renderHook(useGameSession);
  await waitFor(() => expect(hook.result.current.status).toBe("ready"));
  await act(() => hook.result.current.startRun("sword"));
  let action!: Promise<void>;
  let create!: Promise<void>;
  act(() => { action = hook.result.current.perform({ kind: "choose_node", node_id: "L1N0" }); });
  act(() => { create = hook.result.current.startRun("fire"); });
  await act(async () => {
    if (outcome === "success") oldAction.resolve({ run: oldRun, events: [] });
    else oldAction.reject(new ApiError(401, "旧动作拒绝"));
    await action;
  });
  expect(hook.result.current.busy).toBe(true);
  expect(hook.result.current.error).toBeNull();
  await act(async () => { nextCreate.resolve(created); await create; });
});

it("旧 409 恢复 GET 不能把新局改回终局", async () => {
  const synchronization = deferred<RunResponse>();
  vi.mocked(client.sendAction).mockRejectedValue(new ApiError(409, "版本冲突"));
  vi.mocked(client.getRun).mockReturnValueOnce(synchronization.promise);
  vi.mocked(client.createRun).mockResolvedValueOnce({ ...created, run: oldRun }).mockResolvedValueOnce(created);
  const hook = renderHook(useGameSession);
  await waitFor(() => expect(hook.result.current.status).toBe("ready"));
  await act(() => hook.result.current.startRun("sword"));
  let action!: Promise<void>;
  act(() => { action = hook.result.current.perform({ kind: "choose_node", node_id: "L1N0" }); });
  await waitFor(() => expect(client.getRun).toHaveBeenCalled());
  await act(() => hook.result.current.startRun("fire"));
  await act(async () => {
    synchronization.resolve({ run: { ...oldRun, phase: "completed" }, events: [] });
    await action;
  });
  expect(hook.result.current.run?.run_id).toBe(newRun.run_id);
  expect(hook.result.current.run?.phase).toBe("map");
  expect(hook.result.current.busy).toBe(false);
});

it("毕方模式显式建局并写入独立档案", async () => {
  const mythRun = makeRun({ run_id: "myth-run", mode: "myth_bifang" });
  vi.mocked(client.createRun).mockResolvedValue({ run: mythRun, events: [], access_token: "myth-token" });
  const hook = renderHook(() => useGameSession("myth_bifang"));
  await waitFor(() => expect(hook.result.current.status).toBe("ready"));

  await act(() => hook.result.current.startRun("fire"));

  expect(client.createRun).toHaveBeenCalledWith("fire", undefined, "myth_bifang");
  expect(loadSession()).toBeNull();
  expect(loadSession("myth_bifang")).toEqual({ accessToken: "myth-token", runId: "myth-run" });
});

it("毕方恢复拒绝缺 mode 的经典响应并保留凭据", async () => {
  const session = { accessToken: "myth-token", runId: "myth-run" };
  saveSession(session, "myth_bifang");
  vi.mocked(client.getRun).mockResolvedValue({ run: oldRun, events: [] });

  const hook = renderHook(() => useGameSession("myth_bifang"));

  await waitFor(() => expect(hook.result.current.retryMode).toBe("sync"));
  expect(hook.result.current.run).toBeNull();
  expect(hook.result.current.error).toMatch(/模式/);
  expect(loadSession("myth_bifang")).toEqual(session);
});

it("切换模式后旧响应及 finally 不能覆盖或解锁新模式", async () => {
  saveSession({ accessToken: "classic-token", runId: "classic-run" });
  saveSession({ accessToken: "myth-token", runId: "myth-run" }, "myth_bifang");
  const classicRestore = deferred<RunResponse>();
  const mythRestore = deferred<RunResponse>();
  vi.mocked(client.getRun).mockReturnValueOnce(classicRestore.promise).mockReturnValueOnce(mythRestore.promise);
  const hook = renderHook(({ mode }: { mode: RunMode }) => useGameSession(mode), {
    initialProps: { mode: "classic" as RunMode },
  });
  await waitFor(() => expect(client.getRun).toHaveBeenCalledTimes(1));

  hook.rerender({ mode: "myth_bifang" });
  await waitFor(() => expect(client.getRun).toHaveBeenCalledTimes(2));
  await act(async () => classicRestore.resolve({ run: oldRun, events: [] }));
  expect(hook.result.current.busy).toBe(true);
  expect(hook.result.current.run).toBeNull();

  const mythRun = makeRun({ run_id: "myth-run", mode: "myth_bifang" });
  await act(async () => mythRestore.resolve({ run: mythRun, events: [] }));
  expect(hook.result.current.run?.run_id).toBe("myth-run");
  expect(hook.result.current.busy).toBe(false);
});

it("切换模式时立即移除另一档已恢复局面", async () => {
  saveSession({ accessToken: "classic-token", runId: "classic-run" });
  saveSession({ accessToken: "myth-token", runId: "myth-run" }, "myth_bifang");
  const mythRestore = deferred<RunResponse>();
  vi.mocked(client.getRun).mockResolvedValueOnce({ run: oldRun, events: [] }).mockReturnValueOnce(mythRestore.promise);
  const hook = renderHook(({ mode }: { mode: RunMode }) => useGameSession(mode), {
    initialProps: { mode: "classic" as RunMode },
  });
  await waitFor(() => expect(hook.result.current.run?.run_id).toBe("old-run"));

  hook.rerender({ mode: "myth_bifang" });

  await waitFor(() => expect(client.getRun).toHaveBeenCalledTimes(2));
  expect(hook.result.current.run).toBeNull();
  expect(hook.result.current.busy).toBe(true);
  mythRestore.resolve({ run: makeRun({ run_id: "myth-run", mode: "myth_bifang" }), events: [] });
});

it("unknown 动作期间 resync 只 GET 且保留原编号重放", async () => {
  const actionFailure = new TypeError("提交后断网");
  vi.mocked(client.sendAction).mockRejectedValueOnce(actionFailure)
    .mockResolvedValueOnce({ run: makeRun({ revision: 2 }), events: [] });
  vi.mocked(client.createRun).mockResolvedValue(created);
  vi.mocked(client.getRun).mockResolvedValue({ run: makeRun({ revision: 2 }), events: [] });
  const hook = renderHook(useGameSession);
  await waitFor(() => expect(hook.result.current.status).toBe("ready"));
  await act(() => hook.result.current.startRun("sword"));
  await act(() => hook.result.current.perform({ kind: "end_turn" }));
  const original = vi.mocked(client.sendAction).mock.calls[0][2];

  await act(() => hook.result.current.resync());

  expect(client.getRun).toHaveBeenLastCalledWith("new-run", "token");
  expect(client.sendAction).toHaveBeenCalledTimes(1);
  expect(hook.result.current.retryMode).toBe("action");
  await act(() => hook.result.current.retryAction());
  expect(vi.mocked(client.sendAction).mock.calls[1][2]).toEqual(original);
});

it("resync 失败保留凭据并可只读重试后继续原动作", async () => {
  vi.mocked(client.sendAction).mockRejectedValueOnce(new TypeError("提交后断网"))
    .mockResolvedValueOnce({ run: makeRun({ revision: 2 }), events: [] });
  vi.mocked(client.getRun).mockRejectedValueOnce(new TypeError("同步断网"))
    .mockResolvedValueOnce({ run: makeRun({ revision: 2 }), events: [] });
  const hook = renderHook(useGameSession);
  await waitFor(() => expect(hook.result.current.status).toBe("ready"));
  await act(() => hook.result.current.startRun("sword"));
  await act(() => hook.result.current.perform({ kind: "end_turn" }));
  const session = loadSession();
  await act(() => hook.result.current.resync());

  expect(hook.result.current.retryMode).toBe("sync");
  expect(loadSession()).toEqual(session);
  await act(() => hook.result.current.retryAction());
  expect(hook.result.current.retryMode).toBe("action");
  await act(() => hook.result.current.retryAction());
  expect(client.sendAction).toHaveBeenCalledTimes(2);
});

it("迟到 resync 不能覆盖新局", async () => {
  const synchronization = deferred<RunResponse>();
  vi.mocked(client.getRun).mockReturnValueOnce(synchronization.promise);
  const hook = renderHook(useGameSession);
  await waitFor(() => expect(hook.result.current.status).toBe("ready"));
  await act(() => hook.result.current.startRun("sword"));
  let syncing!: Promise<void>;
  act(() => { syncing = hook.result.current.resync(); });
  await act(() => hook.result.current.startRun("fire"));
  await act(async () => { synchronization.resolve({ run: oldRun, events: [] }); await syncing; });

  expect(hook.result.current.run?.run_id).toBe(newRun.run_id);
  expect(hook.result.current.error).toBeNull();
});
