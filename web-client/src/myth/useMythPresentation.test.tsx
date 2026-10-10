import { act, renderHook, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import type { GameEvent } from "../api/types";
import { deferred } from "../test/deferred";
import { makeCombat, makeRun } from "../test/fixtures";
import type { PresentationAdapter } from "./presentationQueue";
import { useMythPresentation } from "./useMythPresentation";

const initial = makeRun({ mode: "myth_bifang", phase: "combat", combat: makeCombat(), revision: 1 });
const final = { ...initial, phase: "completed" as const, revision: 2 };
const hit: GameEvent = { kind: "damage", text: "命中", source: "player", visual: "sword",
  state_after: { player: initial.player, enemy: { hp: 8, block: 0, burn: 0, weak: 0 },
    energy: 2, turn: 1 } };

it("逐事件快照驱动 HUD，最后事件完成之前不切胜利", async () => {
  const first = deferred<void>();
  const last = deferred<void>();
  const adapter = vi.fn().mockReturnValueOnce(first.promise).mockReturnValueOnce(last.promise);
  const resync = vi.fn();
  const hook = renderHook(({ run, events }) => useMythPresentation(run, events, adapter, resync),
    { initialProps: { run: initial, events: [] as GameEvent[] } });
  hook.rerender({ run: final, events: [hit, { kind: "victory", text: "毕方退去", visual: "defeat" }] });
  await waitFor(() => expect(hook.result.current.busy).toBe(true));
  expect(hook.result.current.run?.phase).toBe("combat");
  expect(hook.result.current.run?.combat?.enemy.hp).toBe(20);
  await act(async () => first.resolve());
  expect(hook.result.current.run?.combat?.enemy.hp).toBe(8);
  expect(hook.result.current.run?.combat?.energy).toBe(2);
  expect(hook.result.current.run?.phase).toBe("combat");
  await act(async () => last.resolve());
  expect(hook.result.current.run?.phase).toBe("completed");
  expect(hook.result.current.busy).toBe(false);
});

it("旧局不合作 adapter 迟到不能覆盖新局或释放新演出锁", async () => {
  const old = deferred<void>();
  const next = deferred<void>();
  const adapter = vi.fn().mockReturnValueOnce(old.promise).mockReturnValueOnce(next.promise);
  const hook = renderHook(({ run, events }) => useMythPresentation(run, events, adapter, vi.fn()),
    { initialProps: { run: initial, events: [] as GameEvent[] } });
  hook.rerender({ run: final, events: [hit] });
  const other = { ...initial, run_id: "other", revision: 0 };
  hook.rerender({ run: other, events: [] });
  hook.rerender({ run: { ...other, revision: 1 }, events: [hit] });
  await act(async () => old.resolve());
  expect(hook.result.current.run?.run_id).toBe("other");
  expect(hook.result.current.busy).toBe(true);
  await act(async () => next.resolve());
  expect(hook.result.current.busy).toBe(false);
});

it("表现失败释放锁，保留权威结果并只调用只读恢复入口", async () => {
  const playback = deferred<void>();
  const resync = vi.fn().mockResolvedValue(undefined);
  const adapter = () => playback.promise;
  const hook = renderHook(({ run, events }) => useMythPresentation(run, events, adapter, resync),
    { initialProps: { run: initial, events: [] as GameEvent[] } });
  hook.rerender({ run: final, events: [hit] });
  await act(async () => playback.reject(new Error("纹理丢失")));
  expect(hook.result.current.busy).toBe(false);
  expect(hook.result.current.error).toContain("纹理丢失");
  expect(hook.result.current.run?.phase).toBe("completed");
  expect(resync).toHaveBeenCalledTimes(1);
});

it("非空 adapter 换引用不应取消在途演出或重复发布状态", async () => {
  const pending = deferred<void>();
  let signal: AbortSignal | undefined;
  const first = (_event: GameEvent, abort: AbortSignal) => { signal = abort; return pending.promise; };
  const second = vi.fn().mockResolvedValue(undefined);
  const hook = renderHook(({ adapter, run, events }) => useMythPresentation(run, events, adapter, vi.fn()),
    { initialProps: { adapter: first, run: initial, events: [] as GameEvent[] } });
  hook.rerender({ adapter: first, run: final, events: [hit] });
  await waitFor(() => expect(hook.result.current.busy).toBe(true));
  hook.rerender({ adapter: second, run: final, events: [hit] });
  expect(signal?.aborted).toBe(false);
  await act(async () => pending.resolve());
  expect(second).not.toHaveBeenCalled();
  expect(hook.result.current.run?.phase).toBe("completed");
});

it("资源重附着不重复攻击，卸载会 abort 且忽略迟到错误", async () => {
  const pending = deferred<void>();
  let signal: AbortSignal | undefined;
  const first = (event: GameEvent, abort: AbortSignal) => { void event; signal = abort; return pending.promise; };
  const second = vi.fn().mockResolvedValue(undefined);
  const resync = vi.fn();
  const hook = renderHook((props: { adapter: PresentationAdapter | null; run: typeof initial; events: GameEvent[] }) =>
    useMythPresentation(props.run, props.events, props.adapter, resync),
  { initialProps: { adapter: first as PresentationAdapter | null, run: initial, events: [] as GameEvent[] } });
  hook.rerender({ adapter: first, run: { ...initial, revision: 2 }, events: [hit] });
  hook.rerender({ adapter: null, run: { ...initial, revision: 2 }, events: [hit] });
  hook.rerender({ adapter: second, run: { ...initial, revision: 2 }, events: [hit] });
  await act(async () => pending.resolve());
  expect(signal?.aborted).toBe(true);
  expect(second).not.toHaveBeenCalled();
  expect(hook.result.current.busy).toBe(false);
  hook.rerender({ adapter: second, run: { ...initial, revision: 3 }, events: [hit] });
  hook.unmount();
  expect(resync).not.toHaveBeenCalled();
});
