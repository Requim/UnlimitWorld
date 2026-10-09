import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AssetProvider } from "../game/AssetContext";
import type { AssetState } from "../game/useAssets";
import { makeCatalog } from "../test/fixtures";
import { StartScreen } from "./StartScreen";

const catalog = makeCatalog({ archetypes: [
  { id: "sword", name: "御剑", description: "积攒剑意", starter_card_id: "charge_sword" },
  { id: "fire", name: "业火", description: "燃烧换收益", starter_card_id: "fire_seed" },
  { id: "talisman", name: "符箓", description: "护盾反制", starter_card_id: "golden_bell" },
] });
const ready: AssetState = { status: "ready", message: null, manifest: {
  version: 1, status: "ready", characters: {}, enemies: {}, backgrounds: {},
  cards: { myriad_swords: "/assets/cards/myriad_swords.webp",
    burn_heaven: "/assets/cards/burn_heaven.webp", golden_bell: "/assets/cards/golden_bell.webp" },
} };

describe("opening artwork", () => {
  it("三流派使用真实 manifest 插画且点击仍提交正确流派", () => {
    const start = vi.fn();
    render(<AssetProvider state={ready}>
      <StartScreen catalog={catalog} busy={false} onStart={start} />
    </AssetProvider>);
    expect(screen.getByAltText("御剑")).toHaveAttribute("src", "/assets/cards/myriad_swords.webp");
    expect(screen.getByAltText("业火")).toHaveAttribute("src", "/assets/cards/burn_heaven.webp");
    expect(screen.getByAltText("符箓")).toHaveAttribute("src", "/assets/cards/golden_bell.webp");
    fireEvent.click(screen.getByTestId("create-fire"));
    expect(start).toHaveBeenCalledWith("fire");
  });

  it("插画加载失败时提供重试且不意外新开局", () => {
    const start = vi.fn(), retry = vi.fn();
    render(<AssetProvider state={ready} retry={retry}>
      <StartScreen catalog={catalog} busy={false} onStart={start} />
    </AssetProvider>);
    fireEvent.error(screen.getByAltText("御剑"));
    fireEvent.click(screen.getByTestId("retry-opening-art"));
    expect(retry).toHaveBeenCalledOnce();
    expect(start).not.toHaveBeenCalled();
  });

  it("美术未就绪时不发送假图片请求且仍可开局", () => {
    const start = vi.fn();
    render(<StartScreen catalog={catalog} busy={false} onStart={start} />);
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId("create-talisman"));
    expect(start).toHaveBeenCalledWith("talisman");
  });
});
