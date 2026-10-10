import { act, render, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import { deferred } from "../test/deferred";
import type { MythAssets, MythManifest } from "./mythAssets";
import { MythStage } from "./MythStage";

const moduleGate = vi.hoisted(() => {
  let release!: () => void;
  const promise = new Promise<void>((resolve) => { release = resolve; });
  return { promise, release, createMythGame: vi.fn() };
});

vi.mock("./createMythGame", async () => {
  await moduleGate.promise;
  return { createMythGame: moduleGate.createMythGame };
});

const manifest = {
  version: "bifang-v1", status: "animation-review",
  seeds: {
    hero: { url: "/assets/myth/seeds/hero.png", size: [2352, 3520] },
    bifang: { url: "/assets/myth/seeds/bifang.png", size: [2352, 3520] },
    scene: { url: "/assets/myth/seeds/zhang-e-mountain.webp", size: [3840, 2160] },
  },
  animations: {}, cards: {},
} satisfies MythManifest;

it("延迟载入 runtime 后使用最新的减少动态设置", async () => {
  const setReducedMotion = vi.fn();
  const present = vi.fn(async () => undefined);
  const runtime = { present, resize: vi.fn(), setReducedMotion, destroy: vi.fn() };
  moduleGate.createMythGame.mockImplementation((...args: unknown[]) => {
    (args[5] as (value: typeof runtime) => void)(runtime);
    return runtime;
  });
  const assets: MythAssets = { status: "ready", manifest, error: null };
  const props = { assets, enabled: true, onTarget: vi.fn(), onRetry: vi.fn(), onAdapter: vi.fn() };
  const view = render(<MythStage {...props} reducedMotion={false} />);
  view.rerender(<MythStage {...props} reducedMotion />);

  await act(async () => moduleGate.release());

  await waitFor(() => expect(moduleGate.createMythGame).toHaveBeenCalled());
  expect(moduleGate.createMythGame.mock.calls[0][4]).toBe(true);
  expect(setReducedMotion).toHaveBeenCalledWith(true);
  expect(props.onAdapter).toHaveBeenCalledWith(present);
});
