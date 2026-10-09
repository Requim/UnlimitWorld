import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, createRun, getRun } from "./client";

describe("API client", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("保留 HTTP 状态和服务端错误文本", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ detail: "revision 已过期" }),
      { status: 409, headers: { "Content-Type": "application/json" } },
    )));

    await expect(getRun("run-1", "token")).rejects.toEqual(
      expect.objectContaining({ status: 409, message: "revision 已过期" }),
    );
  });

  it("携带同档案 Bearer 获取局面", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      run: { run_id: "run-1" },
      events: [],
    }), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);

    await getRun("run-1", "token");

    expect(fetchMock).toHaveBeenCalledWith("/api/v2/runs/run-1", expect.objectContaining({
      headers: expect.objectContaining({ Authorization: "Bearer token" }),
    }));
  });

  it("创建经典局可省略 mode，神话局可显式提交 mode", async () => {
    const fetchMock = vi.fn().mockImplementation(async () => new Response(JSON.stringify({
      run: { run_id: "run-1" },
      events: [],
      access_token: "token",
    }), {
      status: 201,
      headers: { "Content-Type": "application/json" },
    }));
    vi.stubGlobal("fetch", fetchMock);

    await createRun("sword");
    await createRun("fire", undefined, "myth_bifang");

    expect(fetchMock.mock.calls[0][1].body).toBe(JSON.stringify({ archetype: "sword" }));
    expect(fetchMock.mock.calls[1][1].body).toBe(JSON.stringify({
      archetype: "fire",
      mode: "myth_bifang",
    }));
  });
});
