import { describe, expect, it, vi } from "vitest";

import { ActionQueue, type ActionTransport } from "./actionQueue";

describe("ActionQueue", () => {
  it("不确定网络失败后拒绝覆盖未决动作并以原 action_id 恢复", async () => {
    const transport = vi.fn()
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockResolvedValueOnce({ run: { revision: 2 }, events: [] });
    const queue = new ActionQueue(transport as ActionTransport);

    await expect(queue.submit("run-1", "token", 1, { kind: "end_turn" })).rejects.toThrow();
    const original = transport.mock.calls[0][2];
    await expect(queue.submit("run-1", "token", 1, { kind: "taunt" })).rejects.toThrow("仍有结果未知的动作");
    await queue.retry();

    expect(transport).toHaveBeenCalledTimes(2);
    expect(transport.mock.calls[1][2]).toEqual(original);
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
