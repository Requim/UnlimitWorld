import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { makeCombat } from "../test/fixtures";
import { BattleStage } from "./BattleStage";
import { createBattleGame } from "./createBattleGame";

vi.mock("./createBattleGame", () => ({ createBattleGame: vi.fn() }));

const assets = { status: "pending", manifest: null, message: "美术待生成" } as const;

describe("BattleStage", () => {
  beforeEach(() => vi.mocked(createBattleGame).mockReset());

  it("同一敌人的新 revision 更新既有场景适配器", async () => {
    const adapter = { render: vi.fn(), destroy: vi.fn() };
    vi.mocked(createBattleGame).mockReturnValue(adapter);
    const combat = makeCombat();
    const view = render(<BattleStage assets={assets} combat={combat} events={[]}
      revision={1} reducedMotion={false} onRetry={vi.fn()} />);
    await waitFor(() => expect(adapter.render).toHaveBeenCalledWith(expect.objectContaining({ revision: 1 }), true));

    const nextCombat = makeCombat();
    nextCombat.enemy.hp = 13;
    view.rerender(<BattleStage assets={assets} combat={nextCombat}
      events={[{ kind: "damage", text: "造成 7 点伤害", amount: 7, target: "enemy" }]}
      revision={2} reducedMotion={false} onRetry={vi.fn()} />);

    await waitFor(() => expect(adapter.render).toHaveBeenCalledWith(
      expect.objectContaining({ revision: 2, combat: expect.objectContaining({ enemy: expect.objectContaining({ hp: 13 }) }) }), true,
    ));
    expect(createBattleGame).toHaveBeenCalledOnce();
  });

  it("资源重试立即清除旧 runtimeError 并调用重新加载", async () => {
    const onRetry = vi.fn();
    vi.mocked(createBattleGame).mockImplementation((...args) => {
      const onError = args.find((value) => typeof value === "function");
      if (typeof onError === "function") onError("位图加载失败");
      return { render: vi.fn(), destroy: vi.fn() };
    });
    render(<BattleStage assets={{ ...assets, status: "ready" }} combat={makeCombat()} events={[]}
      revision={1} reducedMotion={false} onRetry={onRetry} />);
    expect(await screen.findByText("位图加载失败")).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("retry-assets"));

    expect(onRetry).toHaveBeenCalledOnce();
    expect(screen.queryByText("位图加载失败")).not.toBeInTheDocument();
  });
});
