import { Flame, ScrollText, Swords } from "lucide-react";

import type { ArchetypeId, Catalog } from "../api/types";

const ICONS = { sword: Swords, fire: Flame, talisman: ScrollText } as const;

interface Props { catalog: Catalog; busy: boolean; onStart: (archetype: ArchetypeId) => Promise<void> }

/** 展示三流派真实建局入口；点击只提交流派，模式由样板会话固定为 myth_bifang。 */
export function MythStart({ catalog, busy, onStart }: Props) {
  return <main className="myth-start" data-testid="myth-start">
    <img src="/assets/myth/seeds/zhang-e-mountain.webp" alt="裸玉石峰与断裂巨环构成的章莪山" />
    <div className="myth-start-shade" />
    <header><span>天道异案 · 其一</span><h1>章莪山 · 毕方</h1><p>选一门本事，去给一堆已经烧完的卷宗作证。</p></header>
    <section className="myth-archetypes" aria-label="选择流派">
      {catalog.archetypes.map((archetype) => {
        const Icon = ICONS[archetype.id];
        return <button key={archetype.id} data-testid={`create-${archetype.id}`} disabled={busy}
          className={`myth-archetype ${archetype.id}`} onClick={() => void onStart(archetype.id)}>
          <Icon /><span><b>{archetype.name}</b><small>{archetype.description}</small></span><em>入山</em>
        </button>;
      })}
    </section>
  </main>;
}
