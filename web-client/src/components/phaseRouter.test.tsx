import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PhaseRouter } from "./phaseRouter";

describe("PhaseRouter", () => {
  const phases = [
    "map", "combat", "battle_won", "reward", "event", "shop", "rest",
    "rest_upgrade", "completed", "game_over",
  ] as const;

  it.each(phases)("为 %s 提供真实界面出口", (phase) => {
    render(<PhaseRouter phase={phase} />);
    expect(screen.getByTestId(`phase-${phase}`)).toBeInTheDocument();
  });
});
