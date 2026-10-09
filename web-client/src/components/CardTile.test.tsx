import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AssetProvider } from "../game/AssetContext";
import { makeCatalog } from "../test/fixtures";
import { CardTile } from "./CardTile";

describe("CardTile artwork", () => {
  it("ready manifest 消费真实卡面路径并显式报告图片加载失败", () => {
    render(<AssetProvider state={{ status: "ready", message: null, manifest: {
      version: 1, status: "ready", characters: {}, enemies: {}, backgrounds: {},
      cards: { flying_sword: "/cards/flying_sword.webp" },
    } }}><CardTile card={{ uid: "one", card_id: "flying_sword", upgraded: false }} catalog={makeCatalog()} /></AssetProvider>);
    const image = screen.getByTestId("card-art-flying_sword");
    expect(image).toHaveAttribute("src", "/cards/flying_sword.webp");

    fireEvent.error(image);
    expect(screen.getByText("卡面加载失败")).toBeInTheDocument();
  });
});
