import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import { ApiError } from "./api/client";
import * as client from "./api/client";

vi.mock("./api/client", async () => {
  const actual = await vi.importActual<typeof import("./api/client")>("./api/client");
  return { ...actual, getCatalog: vi.fn(), createRun: vi.fn(), getRun: vi.fn() };
});

const catalog = {
  cards: [], relics: [], enemies: [],
  archetypes: [
    { id: "sword", name: "御剑", description: "积攒剑意", starter_card_id: "charge_sword" },
    { id: "fire", name: "业火", description: "燃烧换收益", starter_card_id: "fire_seed" },
    { id: "talisman", name: "符箓", description: "护盾反制", starter_card_id: "golden_bell" },
  ],
} as Awaited<ReturnType<typeof client.getCatalog>>;

const run = {
  run_id: "run-1", revision: 0, archetype: "sword", phase: "map", layer: 0,
  player: { hp: 60, max_hp: 60, block: 0, wrath: 0, stones: 60, reflect: 0 },
  deck: [], relics: [], combat: null, reward: null, choices: [], shop: null,
  map: { current_node_id: null, nodes: [
    { id: "L1N0", layer: 1, lane: 0, kind: "combat", available: true, completed: false, links_from: [] },
  ] },
  history: [], epitaph: null,
} as Awaited<ReturnType<typeof client.createRun>>["run"];

describe("App", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.mocked(client.getCatalog).mockResolvedValue(catalog);
    vi.mocked(client.createRun).mockResolvedValue({ run, events: [], access_token: "token" });
  });

  it("首屏提供三流派并进入真实地图局面", async () => {
    render(<App />);
    expect(await screen.findByTestId("create-sword")).toBeInTheDocument();
    expect(screen.getByTestId("create-fire")).toBeInTheDocument();
    expect(screen.getByTestId("create-talisman")).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("create-sword"));

    await waitFor(() => expect(screen.getByTestId("game-root")).toHaveAttribute("data-phase", "map"));
    expect(screen.getByTestId("map-node-L1N0")).toBeEnabled();
  });

  it("恢复凭证失效时提供明确清理入口", async () => {
    localStorage.setItem("tiandao.cardRogue.session.v1", JSON.stringify({ accessToken: "bad", runId: "gone" }));
    vi.mocked(client.getRun).mockRejectedValue(new ApiError(401, "凭证无效"));

    render(<App />);

    expect(await screen.findByTestId("reset-session")).toBeInTheDocument();
  });

  it("目录加载失败时不永久停在加载页", async () => {
    vi.mocked(client.getCatalog).mockRejectedValueOnce(new TypeError("Failed to fetch"));

    render(<App />);

    expect(await screen.findByTestId("reload-client")).toBeInTheDocument();
  });
});
