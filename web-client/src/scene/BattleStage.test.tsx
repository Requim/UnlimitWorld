import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { makeCombat } from "../test/fixtures";
import { BattleStage } from "./BattleStage";
import { createBattleGame } from "./createBattleGame";

vi.mock("./createBattleGame", () => ({ createBattleGame: vi.fn() }));

const assets = { status: "pending", manifest: null, message: "美术待生成" } as const;
let resize: () => void;

beforeEach(() => {
  vi.mocked(createBattleGame).mockReset();
  vi.stubGlobal("ResizeObserver", class {
    constructor(callback: ResizeObserverCallback) {
      resize = () => callback([], this as unknown as ResizeObserver);
    }
    observe() {}
    disconnect() {}
  });
});
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

describe("BattleStage", () => {
  it("画布坐标框随可用区域缩放并在资源重试后保持投影", async () => {
    const adapter = { render: vi.fn(), destroy: vi.fn() };
    vi.mocked(createBattleGame).mockReturnValue(adapter);
    let bounds = { width: 1440, height: 400 };
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(
      () => ({ ...bounds, x: 0, y: 0, top: 0, left: 0, right: bounds.width, bottom: bounds.height, toJSON() {} }),
    );
    const view = render(<BattleStage assets={assets} combat={makeCombat()} events={[]}
      revision={1} reducedMotion={false} onRetry={vi.fn()} />);
    expect(screen.getByTestId("battle-viewport")).toHaveStyle({ width: "1000px", height: "400px" });
    await waitFor(() => expect(adapter.render).toHaveBeenCalled());

    bounds = { width: 390, height: 500 };
    act(() => resize());
    expect(screen.getByTestId("battle-viewport")).toHaveStyle({ width: "390px", height: "156px" });
    view.rerender(<BattleStage assets={{ ...assets, status: "ready" }} combat={makeCombat()} events={[]}
      revision={1} reducedMotion={true} onRetry={vi.fn()} />);
    expect(screen.getByTestId("battle-viewport")).toHaveStyle({ width: "390px", height: "156px" });
    await waitFor(() => expect(adapter.render).toHaveBeenCalled());
  });

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
