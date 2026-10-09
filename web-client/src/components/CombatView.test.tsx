import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import { makeCards, makeCatalog, makeCombat, makeRun } from "../test/fixtures";
import { CombatView } from "./CombatView";

vi.mock("../scene/BattleStage", () => ({
  BattleStage: ({ children, info }: { children?: ReactNode; info?: ReactNode }) => <div>{info}{children}</div>,
}));

describe("CombatView card details", () => {
  it("选中手牌后展示完整规则文本", () => {
    const description = "造成十二点伤害，并获得两层剑意；若目标带有虚弱，再抽一张牌。";
    const catalog = makeCatalog({ cards: [{
      ...makeCatalog().cards[0], description, upgrade_text: "伤害提高并额外获得一层剑意。",
    }] });
    const hand = makeCards(1);
    hand[0].upgraded = true;
    const run = makeRun({ phase: "combat", combat: makeCombat(hand), deck: hand });
    render(<CombatView run={run} catalog={catalog} events={[]} assets={{ status: "pending", manifest: null, message: "待生成" }}
      busy={false} reducedMotion={false} onRetryAssets={vi.fn()} onAction={vi.fn()} />);

    fireEvent.click(screen.getByTestId("hand-card-card-0"));

    expect(screen.getByTestId("selected-card-rule")).toHaveTextContent(
      `${description} 升级：伤害提高并额外获得一层剑意。`,
    );
  });

  it("挑衅用结构字段展示完整摘要并保留权威全文", () => {
    const run = makeRun({ phase: "combat", combat: makeCombat(makeCards(1)) });
    render(<CombatView run={run} catalog={makeCatalog()} events={[]}
      assets={{ status: "pending", manifest: null, message: "待生成" }} busy={false}
      reducedMotion={false} onRetryAssets={vi.fn()} onAction={vi.fn()} />);

    expect(screen.getByTestId("taunt")).toHaveAttribute("title", run.combat?.taunt_preview.text);
    expect(screen.getByTestId("taunt-summary")).toHaveTextContent("灵力+1 · 天谴+8 · 敌攻+2/段");
  });
});
