import { describe, expect, it, vi } from "vitest";

import type { RunResponse } from "./types";
import { ApiError } from "./client";
import { ActionQueue } from "./actionQueue";
import { deferred } from "../test/deferred";
import { makeRun } from "../test/fixtures";

const response: RunResponse = { run: makeRun({ revision: 2 }), events: [] };

describe("ActionQueue unknown outcomes", () => {
  it.each([new SyntaxError("Unexpected end of JSON"), new ApiError(503, "响应不可用"), new ApiError(408, "代理超时")])(
    "截断 JSON 或 5xx 后锁定其他动作并保留原请求 %s", async (cause) => {
      const transport = vi.fn().mockRejectedValueOnce(cause).mockResolvedValueOnce(response);
      const queue = new ActionQueue(transport);
      await expect(queue.submit("run-1", "token", 1, { kind: "end_turn" })).rejects.toThrow();
      const original = transport.mock.calls[0][2];
      await expect(queue.submit("run-1", "token", 1, { kind: "taunt" })).rejects.toThrow("仍有结果未知的动作");
      await expect(queue.retry()).resolves.toEqual(response);
      expect(transport.mock.calls[1][2]).toEqual(original);
    },
  );

  it("明确规则拒绝后允许下一条正常动作", async () => {
    const transport = vi.fn().mockRejectedValueOnce(new ApiError(422, "非法动作")).mockResolvedValueOnce(response);
    const queue = new ActionQueue(transport);
    await expect(queue.submit("run-1", "token", 1, { kind: "taunt" })).rejects.toThrow("非法动作");
    await expect(queue.submit("run-1", "token", 1, { kind: "end_turn" })).resolves.toEqual(response);
  });
});

describe("ActionQueue request ownership", () => {
  it("旧世代的明确拒绝不能清除新世代未决请求", async () => {
    const old = deferred<RunResponse>();
    const transport = vi.fn().mockReturnValueOnce(old.promise).mockRejectedValueOnce(new TypeError("断网"))
      .mockResolvedValueOnce(response);
    const queue = new ActionQueue(transport);
    const abandoned = queue.submit("old", "token", 1, { kind: "end_turn" });
    queue.advanceGeneration();
    await expect(queue.submit("new", "token", 1, { kind: "taunt" })).rejects.toThrow("断网");
    const current = transport.mock.calls[1][2];
    old.reject(new ApiError(422, "旧请求拒绝"));
    await expect(abandoned).resolves.toBeNull();
    await expect(queue.retry()).resolves.toEqual(response);
    expect(transport.mock.calls[2][2]).toEqual(current);
  });

  it("同一世代的旧重试完成也不能清除后续动作", async () => {
    const oldRetry = deferred<RunResponse>();
    const transport = vi.fn().mockRejectedValueOnce(new TypeError("断网")).mockReturnValueOnce(oldRetry.promise)
      .mockResolvedValueOnce(response).mockRejectedValueOnce(new TypeError("再次断网")).mockResolvedValueOnce(response);
    const queue = new ActionQueue(transport);
    await expect(queue.submit("run-1", "token", 1, { kind: "end_turn" })).rejects.toThrow();
    const abandoned = queue.retry();
    await queue.retry();
    await expect(queue.submit("run-1", "token", 2, { kind: "taunt" })).rejects.toThrow();
    const current = transport.mock.calls[3][2];
    oldRetry.resolve(response);
    await expect(abandoned).resolves.toBeNull();
    await expect(queue.retry()).resolves.toEqual(response);
    expect(transport.mock.calls[4][2]).toEqual(current);
  });
});
