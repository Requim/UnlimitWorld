import { describe, expect, it, vi } from "vitest";

import { ActionQueue, type ActionTransport } from "./actionQueue";

describe("ActionQueue", () => {
  it("不确定网络失败后使用同一个 action_id 重试", async () => {
    const transport = vi.fn()
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockResolvedValueOnce({ run: { revision: 2 }, events: [] });
    const queue = new ActionQueue(transport as ActionTransport);

    await expect(queue.submit("run-1", "token", 1, { kind: "end_turn" })).rejects.toThrow();
    await queue.retry();

    expect(transport).toHaveBeenCalledTimes(2);
    expect(transport.mock.calls[0][2]).toEqual(transport.mock.calls[1][2]);
  });

  it("收到更新世代后丢弃旧局面的迟到响应", async () => {
    let resolveRequest!: (value: { run: { revision: number }; events: never[] }) => void;
    const transport = vi.fn(() => new Promise((resolve) => { resolveRequest = resolve; }));
    const queue = new ActionQueue(transport as ActionTransport);
    const pending = queue.submit("run-1", "token", 1, { kind: "end_turn" });

    queue.advanceGeneration();
    resolveRequest({ run: { revision: 2 }, events: [] });

    await expect(pending).resolves.toBeNull();
  });
});
