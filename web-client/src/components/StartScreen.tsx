import type { ArchetypeId, Catalog } from "../api/types";

interface StartScreenProps {
  catalog: Catalog;
  busy: boolean;
  onStart: (archetype: ArchetypeId) => void;
}

/** 渲染三流派真实开局入口；点击后请求服务端创建权威局面。 */
export function StartScreen({ catalog, busy, onStart }: StartScreenProps) {
  return (
    <main className="start-screen">
      <header className="start-title">
        <span className="seal">天道</span>
        <div><h1>天道不正经</h1><p>九层天关，抽牌问道</p></div>
      </header>
      <section className="archetype-grid" aria-label="选择流派">
        {catalog.archetypes.map((archetype, index) => (
          <button
            className={`archetype archetype-${archetype.id}`}
            data-testid={`create-${archetype.id}`}
            disabled={busy}
            key={archetype.id}
            onClick={() => onStart(archetype.id)}
          >
            <span className="archetype-number">0{index + 1}</span>
            <strong>{archetype.name}</strong>
            <p>{archetype.description}</p>
            <span className="choose-label">以此入道</span>
          </button>
        ))}
      </section>
      <p className="start-note">匿名档案仅保存在本浏览器。旧战报会化作下一局的本机因果。</p>
    </main>
  );
}
