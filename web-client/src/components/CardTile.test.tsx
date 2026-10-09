import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AssetProvider } from "../game/AssetContext";
import { makeCatalog } from "../test/fixtures";
import { CardTile } from "./CardTile";

describe("CardTile artwork", () => {
  it("ready 卡图失败后提供统一资源重试入口", () => {
    const retry = vi.fn();
    render(<AssetProvider retry={retry} state={{ status: "ready", message: null, manifest: {
      version: 1, status: "ready", characters: {}, enemies: {}, backgrounds: {},
      cards: { flying_sword: "/cards/flying_sword.webp" },
    } }}><CardTile card={{ uid: "one", card_id: "flying_sword", upgraded: false }} catalog={makeCatalog()} /></AssetProvider>);
    const image = screen.getByTestId("card-art-flying_sword");
    expect(image).toHaveAttribute("src", "/cards/flying_sword.webp");

    fireEvent.error(image);
    fireEvent.click(screen.getByTestId("retry-card-art-flying_sword"));

    expect(retry).toHaveBeenCalledOnce();
  });
});
