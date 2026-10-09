import { RotateCcw, Skull, Trophy } from "lucide-react";

import type { RunView } from "../api/types";

interface EndViewProps {
  run: RunView;
  busy: boolean;
  onNewRun: () => void;
}

/** 渲染胜负战报与同档案重开入口；不会自行刷新或篡改结算。 */
export function EndView({ run, busy, onNewRun }: EndViewProps) {
  const won = run.phase === "completed";
  return (
    <section className={won ? "end-view victory" : "end-view defeat"} data-testid={`phase-${run.phase}`}>
      {won ? <Trophy /> : <Skull />}
      <span>{won ? "九层已破" : "道消身陨"}</span>
      <h2>{run.epitaph ?? (won ? "监天朱笔，今日改写。" : "此身虽殒，因果尚存。")}</h2>
      <dl><div><dt>抵达层数</dt><dd>{run.layer} / 9</dd></div><div><dt>最终牌组</dt><dd>{run.deck.length} 张</dd></div><div><dt>法宝</dt><dd>{run.relics.length} 件</dd></div></dl>
      <button data-testid="new-run" disabled={busy} onClick={onNewRun}><RotateCcw /> 再入一局</button>
    </section>
  );
}
