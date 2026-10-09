import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

import App from "./App";
import * as client from "./api/client";
import { ApiError } from "./api/client";
import { makeCatalog, makeRun } from "./test/fixtures";
import { SESSION_KEY } from "./state/storage";

vi.mock("./api/client", async () => {
  const actual = await vi.importActual<typeof import("./api/client")>("./api/client");
  return { ...actual, getCatalog: vi.fn(), createRun: vi.fn(), getRun: vi.fn(), sendAction: vi.fn() };
});

const run = makeRun({ revision: 0 });
const saved = { runId: run.run_id, accessToken: "saved-token" };

beforeEach(() => {
  vi.resetAllMocks();
  localStorage.clear();
  vi.mocked(client.getCatalog).mockResolvedValue(makeCatalog());
  vi.mocked(client.createRun).mockResolvedValue({ run, events: [], access_token: "token" });
});

it("已保存档案恢复失败显示真实错误与 reload，禁止误入新局", async () => {
  localStorage.setItem(SESSION_KEY, JSON.stringify(saved));
  vi.mocked(client.getRun).mockRejectedValue(new TypeError("档案读取断网"));
  render(<App />);

  expect(await screen.findByTestId("reload-client")).toBeInTheDocument();
  expect(screen.getByText("档案读取断网")).toBeInTheDocument();
  expect(screen.queryByTestId("create-sword")).not.toBeInTheDocument();
  expect(JSON.parse(localStorage.getItem(SESSION_KEY)!)).toEqual(saved);
});

it("首局创建失败不会吞掉错误", async () => {
  vi.mocked(client.createRun).mockRejectedValue(new ApiError(503, "开局服务暂不可用"));
  render(<App />);
  fireEvent.click(await screen.findByTestId("create-sword"));

  expect(await screen.findByText("开局服务暂不可用")).toBeInTheDocument();
});

it.each([new SyntaxError("截断结果"), new ApiError(502, "代理失败")])(
  "未知动作结果保持锁与同编号重试 %s", async (cause) => {
    vi.mocked(client.sendAction).mockRejectedValueOnce(cause)
      .mockResolvedValueOnce({ run: { ...run, revision: 1 }, events: [] });
    render(<App />);
    fireEvent.click(await screen.findByTestId("create-sword"));
    await screen.findByTestId("game-root");
    fireEvent.click(screen.getByTestId("map-node-L1N0"));
    fireEvent.click(await screen.findByTestId("retry-action"));
    await waitFor(() => expect(screen.getByTestId("game-root")).toHaveAttribute("data-revision", "1"));
    expect(client.sendAction).toHaveBeenCalledTimes(2);
    expect(vi.mocked(client.sendAction).mock.calls[1][2]).toEqual(vi.mocked(client.sendAction).mock.calls[0][2]);
  },
);

it("409 后 GET 失败保留旧局面锁，仅显式重试同步而非重发动作", async () => {
  vi.mocked(client.sendAction).mockRejectedValue(new ApiError(409, "局面已更新"));
  vi.mocked(client.getRun).mockRejectedValueOnce(new TypeError("同步断网"))
    .mockResolvedValueOnce({ run: { ...run, revision: 3 }, events: [] });
  render(<App />);
  fireEvent.click(await screen.findByTestId("create-sword"));
  await screen.findByTestId("game-root");
  fireEvent.click(screen.getByTestId("map-node-L1N0"));

  const retry = await screen.findByTestId("retry-action");
  expect(retry).toHaveTextContent("同步权威局面");
  expect(screen.getByTestId("map-node-L1N0")).toBeDisabled();
  fireEvent.click(retry);
  await waitFor(() => expect(screen.getByTestId("game-root")).toHaveAttribute("data-revision", "3"));
  expect(client.sendAction).toHaveBeenCalledTimes(1);
  expect(client.getRun).toHaveBeenCalledTimes(2);
});
