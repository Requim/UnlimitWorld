import { describe, expect, it, vi } from "vitest";

import { BattleSceneRuntime, type BattleSnapshot } from "./battleRuntime";
import { makeCombat } from "../test/fixtures";

describe("BattleSceneRuntime", () => {
  it("同一敌人的后续 revision 更新存活场景且每 revision 只播一次事件", () => {
    const render = vi.fn();
    const runtime = new BattleSceneRuntime(snapshot(1, 20));
    runtime.attach({ render, destroy: vi.fn() });

    runtime.update(snapshot(2, 14));
    runtime.update(snapshot(2, 14));

    expect(render.mock.calls.map((call) => [call[0].revision, call[0].combat.enemy.hp, call[1]])).toEqual([
      [1, 20, true], [2, 14, true], [2, 14, false],
    ]);
  });

  it("异步场景附着时直接消费创建期间收到的最新 revision", () => {
    const render = vi.fn();
    const runtime = new BattleSceneRuntime(snapshot(1, 20));
    runtime.update(snapshot(2, 17));
    runtime.attach({ render, destroy: vi.fn() });

    expect(render).toHaveBeenCalledOnce();
    expect(render.mock.calls[0][0]).toEqual(expect.objectContaining({ revision: 2 }));
  });

  it("资源变化重附着场景时不重播同 revision 效果", () => {
    const firstRender = vi.fn();
    const secondRender = vi.fn();
    const runtime = new BattleSceneRuntime(snapshot(3, 11));
    runtime.attach({ render: firstRender, destroy: vi.fn() });

    runtime.attach({ render: secondRender, destroy: vi.fn() });

    expect(firstRender).toHaveBeenCalledWith(expect.objectContaining({ revision: 3 }), true);
    expect(secondRender).toHaveBeenCalledWith(expect.objectContaining({ revision: 3 }), false);
  });
});

function snapshot(revision: number, enemyHp: number): BattleSnapshot {
  const combat = makeCombat();
  combat.enemy.hp = enemyHp;
  return { combat, events: [{ kind: "damage", text: `伤害 ${20 - enemyHp}`, amount: 20 - enemyHp, target: "enemy" }], revision, reducedMotion: false };
}
