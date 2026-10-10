import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

import * as client from "../api/client";
import type { Catalog } from "../api/types";
import { deferred } from "../test/deferred";
import { makeCatalog, makeCombat, makeRun } from "../test/fixtures";
import MythApp from "./MythApp";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return { ...actual, getCatalog: vi.fn(), createRun: vi.fn(), getRun: vi.fn(), sendAction: vi.fn() };
});

const archetypes: Catalog["archetypes"] = [
  { id: "sword", name: "御剑", description: "剑意", starter_card_id: "charge_sword" },
  { id: "fire", name: "业火", description: "燃烧", starter_card_id: "fire_seed" },
  { id: "talisman", name: "符箓", description: "反制", starter_card_id: "mirror" },
];
const storyRun = makeRun({ phase: "event", mode: "myth_bifang", story: {
  id: "bifang_trial", version: "bifang-v1", title: "章莪山·灰烬为证", body: "毕方烧掉卷宗，要求修士作证。",
  selected_choice: null, choices: [{ id: "borrow_fire", label: "借火验案", consequence: "天谴 +16；毕方初始燃烧 3" }],
} });

beforeEach(() => {
  vi.resetAllMocks();
  localStorage.clear();
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("种子尚未载入")));
  vi.mocked(client.getCatalog).mockResolvedValue(makeCatalog({ archetypes }));
  vi.mocked(client.createRun).mockResolvedValue({ run: storyRun, events: [], access_token: "myth-token" });
});

it("三流派创建独立模式，剧情完整后果来自服务端且不显示旧卡图", async () => {
  render(<MythApp />);
  await screen.findByTestId("create-sword");
  expect(screen.getByTestId("create-fire")).toBeInTheDocument();
  expect(screen.getByTestId("create-talisman")).toBeInTheDocument();
  fireEvent.click(screen.getByTestId("create-sword"));
  await screen.findByTestId("story-choice-borrow_fire");
  expect(client.createRun).toHaveBeenCalledWith("sword", undefined, "myth_bifang");
  expect(screen.getByText(storyRun.story!.body)).toBeInTheDocument();
  expect(screen.getByText(storyRun.story!.choices[0].consequence)).toBeInTheDocument();
  expect(document.querySelector('img[src^="/assets/cards"]')).toBeNull();
  expect(localStorage.getItem("tiandao.cardRogue.session.v1")).toBeNull();
});

it("未知剧情动作锁住选择但保留原编号重试和设置", async () => {
  vi.mocked(client.sendAction).mockRejectedValueOnce(new TypeError("响应丢失"))
    .mockResolvedValueOnce({ run: { ...storyRun, revision: 2 }, events: [] });
  render(<MythApp />);
  fireEvent.click(await screen.findByTestId("create-fire"));
  fireEvent.click(await screen.findByTestId("story-choice-borrow_fire"));
  await screen.findByTestId("retry-action");
  expect(screen.getByTestId("story-choice-borrow_fire")).toBeDisabled();
  expect(screen.getByTestId("settings-open")).toBeEnabled();
  fireEvent.click(screen.getByTestId("retry-action"));
  await waitFor(() => expect(client.sendAction).toHaveBeenCalledTimes(2));
  expect(vi.mocked(client.sendAction).mock.calls[1][2]).toEqual(vi.mocked(client.sendAction).mock.calls[0][2]);
});

it("战斗提交只锁网络命令，设置保持可用且局面只接受服务端 revision", async () => {
  const combatRun = makeRun({ mode: "myth_bifang", phase: "combat", combat: makeCombat(), revision: 1 });
  const response = deferred<Awaited<ReturnType<typeof client.sendAction>>>();
  vi.mocked(client.createRun).mockResolvedValue({ run: combatRun, events: [], access_token: "myth-token" });
  vi.mocked(client.sendAction).mockReturnValue(response.promise);
  render(<MythApp />);
  fireEvent.click(await screen.findByTestId("create-sword"));
  fireEvent.click(await screen.findByTestId("hand-card-card-0"));
  fireEvent.click(screen.getByTestId("enemy-target"));
  await waitFor(() => expect(screen.getByTestId("myth-root")).toHaveAttribute("data-network-busy", "true"));
  expect(screen.getByTestId("enemy-target")).toBeDisabled();
  expect(screen.getByTestId("settings-open")).toBeEnabled();
  const request = vi.mocked(client.sendAction).mock.calls[0][2];
  expect(request).toMatchObject({ kind: "play_card", card_uid: "card-0", target_id: "paper_soldier" });
  response.resolve({ run: { ...combatRun, revision: 2 }, events: [] });
  await waitFor(() => expect(screen.getByTestId("myth-root")).toHaveAttribute("data-revision", "2"));
});

it("401 显示样板凭证恢复并可返回流派选择", async () => {
  vi.mocked(client.createRun).mockRejectedValue(new client.ApiError(401, "凭证失效"));
  render(<MythApp />);
  fireEvent.click(await screen.findByTestId("create-talisman"));
  fireEvent.click(await screen.findByTestId("reset-session"));
  expect(await screen.findByTestId("create-sword")).toBeEnabled();
  expect(localStorage.getItem("tiandao.cardRogue.session.v1")).toBeNull();
});
