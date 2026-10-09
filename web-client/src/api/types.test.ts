import { expect, it } from "vitest";

import type { CreateRunInput } from "./types";

it("允许创建经典局时省略 mode", () => {
  const request: CreateRunInput = { archetype: "sword" };

  expect(request).toEqual({ archetype: "sword" });
});
