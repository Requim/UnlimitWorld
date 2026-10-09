import { beforeEach, describe, expect, it } from "vitest";

import {
  DEFAULT_SETTINGS,
  loadSession,
  loadSettings,
  saveSession,
  saveSettings,
} from "./storage";

describe("storage", () => {
  beforeEach(() => localStorage.clear());

  it("只恢复格式正确的匿名档案会话", () => {
    saveSession({ accessToken: "secret", runId: "run-1" });
    expect(loadSession()).toEqual({ accessToken: "secret", runId: "run-1" });

    localStorage.setItem("tiandao.cardRogue.session.v1", "{bad json");
    expect(loadSession()).toBeNull();
  });

  it("校验并合并设置默认值", () => {
    saveSettings({ volume: 0.4, muted: true, reducedMotion: true });
    expect(loadSettings()).toEqual({ volume: 0.4, muted: true, reducedMotion: true });

    localStorage.setItem("tiandao.cardRogue.settings.v1", JSON.stringify({ volume: 8 }));
    expect(loadSettings()).toEqual(DEFAULT_SETTINGS);
  });
});
