import { expect, it } from "vitest";

import type { CreateRunInput, RunMode } from "./types";

it("允许创建经典局时省略 mode", () => {
  const request: CreateRunInput = { archetype: "sword" };

  expect(request).toEqual({ archetype: "sword" });
});

it("RunMode 与正式创建请求 mode 保持同源", () => {
  const modes: RunMode[] = ["classic", "myth_bifang"];

  expect(modes).toEqual(["classic", "myth_bifang"]);
});
