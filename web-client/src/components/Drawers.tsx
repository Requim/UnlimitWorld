import { Check, Volume2, VolumeX, X } from "lucide-react";

import type { Catalog, RunView } from "../api/types";
import type { GameSettings } from "../state/storage";
import { CardTile } from "./CardTile";

interface DrawerBaseProps { onClose: () => void }

/** 展示当前权威牌组；无编辑副作用。 */
export function DeckDrawer({ run, catalog, onClose }: DrawerBaseProps & { run: RunView; catalog: Catalog }) {
  return (
    <aside className="drawer" aria-label="当前牌组">
      <DrawerHeader title={`牌组 · ${run.deck.length} 张`} onClose={onClose} />
      <div className="deck-grid">{run.deck.map((card) => <CardTile key={card.uid} card={card} catalog={catalog} />)}</div>
    </aside>
  );
}

interface SettingsDrawerProps extends DrawerBaseProps {
  settings: GameSettings;
  onChange: (settings: GameSettings) => void;
}

/** 编辑本地音频与动态设置；不上传设置，不修改游戏局面。 */
export function SettingsDrawer({ settings, onChange, onClose }: SettingsDrawerProps) {
  const patch = (next: Partial<GameSettings>) => onChange({ ...settings, ...next });
  return (
    <aside className="drawer settings-drawer" aria-label="游戏设置">
      <DrawerHeader title="设置" onClose={onClose} />
      <label className="setting-row">
        <span>{settings.muted ? <VolumeX /> : <Volume2 />} 音量</span>
        <input aria-label="音量" disabled={settings.muted} max="1" min="0" step="0.05" type="range"
          value={settings.volume} onChange={(event) => patch({ volume: Number(event.target.value) })} />
      </label>
      <Toggle label="静音" checked={settings.muted} onChange={(muted) => patch({ muted })} />
      <Toggle label="减少动态效果" checked={settings.reducedMotion}
        onChange={(reducedMotion) => patch({ reducedMotion })} />
    </aside>
  );
}

function DrawerHeader({ title, onClose }: { title: string; onClose: () => void }) {
  return <header className="drawer-header"><h2>{title}</h2><button onClick={onClose} title="关闭"><X /></button></header>;
}

function Toggle({ label, checked, onChange }: { label: string; checked: boolean; onChange: (value: boolean) => void }) {
  return (
    <button className="setting-row setting-toggle" aria-pressed={checked} onClick={() => onChange(!checked)}>
      <span>{label}</span><i className={checked ? "toggle on" : "toggle"}>{checked && <Check size={14} />}</i>
    </button>
  );
}
