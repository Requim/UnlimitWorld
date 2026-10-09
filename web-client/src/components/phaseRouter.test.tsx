import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { PhaseRouter } from "./phaseRouter";
import { makeCards, makeCatalog, makeCombat, makeRun } from "../test/fixtures";

vi.mock("../scene/BattleStage", () => ({ BattleStage: () => <div data-testid="battle-stage" /> }));

describe("PhaseRouter", () => {
  const catalog = makeCatalog();

  it("真实地图局面渲染可用节点命令", () => {
    render(<PhaseRouter phase="map" run={makeRun()} catalog={catalog} onAction={vi.fn()} />);
    expect(screen.getByTestId("map-node-L1N0")).toBeEnabled();
  });

  it("长牌组升级阶段首尾卡牌都保留可操作 selector", () => {
    const deck = makeCards(18);
    render(<PhaseRouter phase="rest_upgrade" run={makeRun({ phase: "rest_upgrade", deck })}
      catalog={catalog} onAction={vi.fn()} />);
    expect(screen.getByTestId("upgrade-card-0")).toBeEnabled();
    expect(screen.getByTestId("upgrade-card-17")).toBeEnabled();
  });

  it("长手牌战斗渲染首尾卡、敌方目标与回合命令", () => {
    const combat = makeCombat(makeCards(14));
    render(<PhaseRouter phase="combat" run={makeRun({ phase: "combat", combat })}
      catalog={catalog} onAction={vi.fn()} />);
    expect(screen.getByTestId("hand-card-card-0")).toBeEnabled();
    expect(screen.getByTestId("hand-card-card-13")).toBeEnabled();
    expect(screen.getByTestId("enemy-target")).toBeDisabled();
    expect(screen.getByTestId("end-turn")).toBeEnabled();
  });
});
