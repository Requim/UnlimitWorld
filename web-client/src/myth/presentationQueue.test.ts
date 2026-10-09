import { describe, expect, it, vi } from "vitest";

import type { GameEvent } from "../api/types";
import { deferred } from "../test/deferred";
import { PresentationQueue, type PresentationBatch } from "./presentationQueue";

describe("PresentationQueue", () => {
  it("依次播放三事件并按中间快照回写，最后事件前不完成", async () => {
    const gates = [deferred<void>(), deferred<void>(), deferred<void>()];
    const adapter = vi.fn((_: GameEvent, __: AbortSignal) => gates[adapter.mock.calls.length - 1].promise);
    const states: number[] = [];
    const complete = vi.fn();
    const queue = new PresentationQueue(adapter, {
      onStateAfter: (state) => states.push(state.enemy.hp), onComplete: complete,
    });
    const playing = queue.enqueue(batch("run-1", 1, [event(17), event(11), event(0)]));

    expect(adapter).toHaveBeenCalledTimes(1);
    await resolve(gates[0]);
    expect(states).toEqual([17]);
    expect(adapter).toHaveBeenCalledTimes(2);
    expect(complete).not.toHaveBeenCalled();
    await resolve(gates[1]);
    expect(states).toEqual([17, 11]);
    expect(complete).not.toHaveBeenCalled();
    await resolve(gates[2]);
    await playing;
    expect(states).toEqual([17, 11, 0]);
    expect(complete).toHaveBeenCalledTimes(1);
  });

  it("忽略精确重放、过期 revision 与重附着后的已开始事件", async () => {
    const first = deferred<void>();
    const oldAdapter = vi.fn().mockReturnValue(first.promise);
    const newAdapter = vi.fn().mockResolvedValue(undefined);
    const queue = new PresentationQueue(oldAdapter);
    const original = batch("run-1", 3, [event(15), event(9)]);
    const abandoned = queue.enqueue(original);
    queue.replaceAdapter(newAdapter);

    await queue.enqueue(original);
    await queue.enqueue(batch("run-1", 2, [event(19)]));
    first.resolve();
    await abandoned;

    expect(oldAdapter).toHaveBeenCalledTimes(1);
    expect(newAdapter).toHaveBeenCalledTimes(1);
    expect(newAdapter).toHaveBeenCalledWith(original.events[1], expect.any(AbortSignal));
  });

});

describe("PresentationQueue lifecycle", () => {
  it("换局使旧 adapter 完成和回调失效且不能释放新批次锁", async () => {
    const oldGate = deferred<void>();
    const newGate = deferred<void>();
    const adapter = vi.fn()
      .mockReturnValueOnce(oldGate.promise)
      .mockReturnValueOnce(newGate.promise);
    const states: number[] = [];
    const busy: boolean[] = [];
    const queue = new PresentationQueue(adapter, {
      onStateAfter: (state) => states.push(state.enemy.hp), onBusyChange: (value) => busy.push(value),
    });
    const oldPlaying = queue.enqueue(batch("old-run", 1, [event(10)]));
    const newPlaying = queue.enqueue(batch("new-run", 1, [event(7)]));

    oldGate.resolve();
    await oldPlaying;
    expect(states).toEqual([]);
    expect(queue.busy).toBe(true);
    newGate.resolve();
    await newPlaying;
    expect(states).toEqual([7]);
    expect(busy.at(-1)).toBe(false);
  });

  it.each(["cancel", "dispose"] as const)("%s 立即解锁且忽略不合作 adapter 的迟到完成", async (method) => {
    const gate = deferred<void>();
    const state = vi.fn();
    const complete = vi.fn();
    const queue = new PresentationQueue(vi.fn().mockReturnValue(gate.promise), {
      onStateAfter: state, onComplete: complete,
    });
    const playing = queue.enqueue(batch("run-1", 1, [event(12)]));

    queue[method]();
    expect(queue.busy).toBe(false);
    gate.resolve();
    await playing;
    expect(state).not.toHaveBeenCalled();
    expect(complete).not.toHaveBeenCalled();
  });
});

describe("PresentationQueue abort reentry", () => {
  it("abort listener 同步换局后保留新 controller、锁与回调", async () => {
    const oldGate = deferred<void>();
    const newGate = deferred<void>();
    const states: number[] = [];
    let queue!: PresentationQueue;
    let newPlaying!: Promise<void>;
    const adapter = vi.fn()
      .mockImplementationOnce((_: GameEvent, signal: AbortSignal) => {
        signal.addEventListener("abort", () => { newPlaying = queue.enqueue(batch("new-run", 1, [event(7)])); });
        return oldGate.promise;
      })
      .mockReturnValueOnce(newGate.promise);
    queue = new PresentationQueue(adapter, { onStateAfter: (state) => states.push(state.enemy.hp) });
    const oldPlaying = queue.enqueue(batch("old-run", 1, [event(15)]));

    queue.cancel();
    expect(queue.busy).toBe(true);
    oldGate.resolve();
    await oldPlaying;
    newGate.resolve();
    await newPlaying;
    expect(states).toEqual([7]);
    expect(queue.busy).toBe(false);
  });

  it("abort listener 同步入队更高 revision 时外层 revision 不得回退", async () => {
    const oldGate = deferred<void>();
    const latestGate = deferred<void>();
    const played: number[] = [];
    let queue!: PresentationQueue;
    let latestPlaying!: Promise<void>;
    const adapter = vi.fn()
      .mockImplementationOnce((playedEvent: GameEvent, signal: AbortSignal) => {
        played.push(playedEvent.state_after!.enemy.hp);
        signal.addEventListener("abort", () => { latestPlaying = queue.enqueue(batch("run-1", 3, [event(3)])); });
        return oldGate.promise;
      })
      .mockImplementationOnce((playedEvent: GameEvent) => {
        played.push(playedEvent.state_after!.enemy.hp);
        return latestGate.promise;
      });
    queue = new PresentationQueue(adapter);
    const oldPlaying = queue.enqueue(batch("run-1", 1, [event(10)]));

    await queue.enqueue(batch("run-1", 2, [event(6)]));
    await queue.enqueue(batch("run-1", 2, [event(5)]));
    expect(queue.busy).toBe(true);
    expect(played).toEqual([10, 3]);
    oldGate.resolve();
    await oldPlaying;
    latestGate.resolve();
    await latestPlaying;
    await queue.enqueue(batch("run-1", 2, [event(4)]));
    expect(adapter).toHaveBeenCalledTimes(2);
  });
});

describe("PresentationQueue error callbacks", () => {
  it("adapter 失败释放锁、通知同步入口并向调用方抛错", async () => {
    const cause = new Error("动画资源损坏");
    const onError = vi.fn();
    const queue = new PresentationQueue(vi.fn().mockRejectedValue(cause), { onError });

    await expect(queue.enqueue(batch("run-1", 1, [event(10)]))).rejects.toBe(cause);

    expect(queue.busy).toBe(false);
    expect(onError).toHaveBeenCalledWith(cause);
  });

  it.each(["cancel", "dispose", "replaceAdapter"] as const)(
    "busy(false) 同步 %s 时旧错误回调失效",
    async (method) => {
      const gate = deferred<void>();
      const cause = new Error("旧动画失败");
      const onError = vi.fn();
      let queue!: PresentationQueue;
      queue = new PresentationQueue(vi.fn().mockReturnValue(gate.promise), {
        onBusyChange: (busy) => {
          if (busy) return;
          if (method === "replaceAdapter") queue.replaceAdapter(vi.fn().mockResolvedValue(undefined));
          else queue[method]();
        },
        onError,
      });
      const playing = queue.enqueue(batch("run-1", 1, [event(10)]));

      gate.reject(cause);
      await expect(playing).rejects.toBe(cause);
      expect(queue.busy).toBe(false);
      expect(onError).not.toHaveBeenCalled();
    },
  );
});

describe("PresentationQueue callback reentry", () => {
  it("错误解锁回调同步换局时旧错误无权触发新世代同步", async () => {
    const next = deferred<void>();
    const cause = new Error("旧动画失败");
    const adapter = vi.fn().mockRejectedValueOnce(cause).mockReturnValueOnce(next.promise);
    const onError = vi.fn();
    let queue!: PresentationQueue;
    queue = new PresentationQueue(adapter, {
      onBusyChange: (busy) => {
        if (!busy && adapter.mock.calls.length === 1) void queue.enqueue(batch("new-run", 1, [event(8)]));
      },
      onError,
    });

    await expect(queue.enqueue(batch("old-run", 1, [event(10)]))).rejects.toBe(cause);

    expect(queue.busy).toBe(true);
    expect(onError).not.toHaveBeenCalled();
    next.resolve();
    await Promise.resolve();
    await Promise.resolve();
  });

  it("完成回调同步换局时旧 finally 无权释放新锁", async () => {
    const next = deferred<void>();
    const adapter = vi.fn().mockResolvedValueOnce(undefined).mockReturnValueOnce(next.promise);
    let queue!: PresentationQueue;
    const complete = vi.fn((finished: PresentationBatch) => {
      if (finished.runId === "old-run") void queue.enqueue(batch("new-run", 1, [event(8)]));
    });
    queue = new PresentationQueue(adapter, { onComplete: complete });

    await queue.enqueue(batch("old-run", 1, [event(10)]));

    expect(queue.busy).toBe(true);
    next.resolve();
    await Promise.resolve();
    await Promise.resolve();
    expect(queue.busy).toBe(false);
  });
});

function batch(runId: string, revision: number, events: GameEvent[]): PresentationBatch {
  return { runId, revision, events };
}

function event(enemyHp: number): GameEvent {
  return { kind: "damage", text: `敌方剩余 ${enemyHp}`, state_after: {
    player: { hp: 60, block: 0, wrath: 0, reflect: 0 },
    enemy: { hp: enemyHp, block: 0, burn: 0, weak: 0 }, turn: 1, energy: 2,
  } };
}

async function resolve(gate: ReturnType<typeof deferred<void>>): Promise<void> {
  gate.resolve();
  await Promise.resolve();
}
