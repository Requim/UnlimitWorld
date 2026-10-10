import { expect, it, vi } from "vitest";

import { isTerminalMythClip, waitForMythAnimation } from "./mythClipPlayback";

class FakeActor {
  played: string[] = [];
  listeners = new Map<string, () => void>();

  play(key: string) { this.played.push(key); return this; }
  once(event: string, listener: () => void) { this.listeners.set(event, listener); return this; }
  off(event: string, listener: () => void) {
    if (this.listeners.get(event) === listener) this.listeners.delete(event);
    return this;
  }
  emit(event: string) { this.listeners.get(event)?.(); }
}

it("动作等待全部真实帧的精确完成事件，不使用固定时长提前结束", async () => {
  const actor = new FakeActor();
  const tracked = new Set<() => void>();
  const pending = waitForMythAnimation(actor, "hero_sword", new AbortController().signal,
    (cancel) => { tracked.add(cancel); return () => tracked.delete(cancel); });
  const settled = vi.fn();
  void pending.then(settled);
  actor.emit("animationcomplete");
  await Promise.resolve();
  expect(settled).not.toHaveBeenCalled();
  expect(actor.played).toEqual(["hero_sword"]);
  expect(tracked.size).toBe(1);
  actor.emit("animationcomplete-hero_sword");
  await expect(pending).resolves.toBe("completed");
  expect(actor.listeners.size).toBe(0);
  expect(tracked.size).toBe(0);
});

it("AbortSignal 与 destroy 取消都会解绑旧完成回调", async () => {
  const abort = new AbortController();
  const actor = new FakeActor();
  let destroy: () => void = () => undefined;
  const aborted = waitForMythAnimation(actor, "hero_sword", abort.signal,
    (cancel) => { destroy = cancel; return () => { destroy = () => undefined; }; });
  abort.abort();
  await expect(aborted).resolves.toBe("cancelled");
  expect(actor.listeners.size).toBe(0);

  const second = new FakeActor();
  const destroyed = waitForMythAnimation(second, "hero_sword", new AbortController().signal,
    (cancel) => { destroy = cancel; return () => { destroy = () => undefined; }; });
  destroy();
  await expect(destroyed).resolves.toBe("cancelled");
  expect(second.listeners.size).toBe(0);
});

it("倒地和退场保留终局末帧，其余动作恢复待机", () => {
  expect(isTerminalMythClip("hero_defeat")).toBe(true);
  expect(isTerminalMythClip("bifang_retreat")).toBe(true);
  expect(isTerminalMythClip("hero_hurt")).toBe(false);
  expect(isTerminalMythClip("hero_sword")).toBe(false);
});
