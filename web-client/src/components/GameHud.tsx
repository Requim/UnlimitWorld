import { AudioLines, BookOpen, Heart, Settings, Shield, Sparkles, Zap } from "lucide-react";

import type { RunView } from "../api/types";

interface GameHudProps {
  run: RunView;
  onDeck: () => void;
  onSettings: () => void;
}

/** 显示战斗关键资源和工具入口；只读，不修改权威局面。 */
export function GameHud({ run, onDeck, onSettings }: GameHudProps) {
  const hpPercent = Math.max(0, Math.round(run.player.hp / run.player.max_hp * 100));
  return (
    <header className="game-hud">
      <div className="brand-lockup"><span className="mini-seal">道</span><b>天道不正经</b></div>
      <div className="hud-stats">
        <div className="hp-stat" title="生命">
          <Heart size={16} aria-hidden="true" />
          <span className="hp-track"><i style={{ width: `${hpPercent}%` }} /></span>
          <b>{run.player.hp}/{run.player.max_hp}</b>
        </div>
        <Stat icon={<Shield size={15} />} label="护盾" value={run.player.block} />
        <Stat icon={<Zap size={15} />} label="天谴" value={run.player.wrath} danger />
        <Stat icon={<Sparkles size={15} />} label="灵石" value={run.player.stones} />
        <span className="layer-mark">第 {Math.max(1, run.layer)} / 9 层</span>
      </div>
      <div className="hud-tools">
        <button data-testid="deck-open" onClick={onDeck} title="查看牌组"><BookOpen /></button>
        <button data-testid="settings-open" onClick={onSettings} title="设置"><Settings /></button>
      </div>
    </header>
  );
}

interface StatProps {
  icon: React.ReactNode;
  label: string;
  value: number;
  danger?: boolean;
}

function Stat({ icon, label, value, danger = false }: StatProps) {
  return <span className={danger ? "hud-stat danger" : "hud-stat"} title={label}>{icon}<b>{value}</b></span>;
}
