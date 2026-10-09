import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

import * as client from "../api/client";
import { ApiError } from "../api/client";
import type { CreateRunResponse, RunResponse } from "../api/types";
import { saveSession } from "../state/storage";
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
