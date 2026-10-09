import type { GameEvent, RunView } from "../api/types";

type Combat = NonNullable<RunView["combat"]>;

/** Phaser 场景需要的只读权威快照。 */
export interface BattleSnapshot {
  combat: Combat;
  events: GameEvent[];
  revision: number;
  reducedMotion: boolean;
}

/** 存活场景适配器；render 更新表现，destroy 释放 Phaser 资源。 */
export interface BattleSceneAdapter {
  render: (snapshot: BattleSnapshot, emitEffects: boolean) => void;
  destroy: () => void;
}

/** 缓冲异步创建期间的最新快照，并按 revision 去重表现事件。 */
export class BattleSceneRuntime {
  private adapter: BattleSceneAdapter | null = null;
  private lastEffectRevision: number | null = null;

  public constructor(private latest: BattleSnapshot) {}

  /** 附着新场景并立即渲染最新快照；会先销毁旧场景。 */
  public attach(adapter: BattleSceneAdapter): void {
    this.detach();
    this.adapter = adapter;
    this.flush();
  }

  /** 更新权威快照；同 revision 仍刷新数值，但不重复播放事件。 */
  public update(snapshot: BattleSnapshot): void {
    this.latest = snapshot;
    this.flush();
  }

  /** 销毁当前场景并重置事件去重游标。 */
  public detach(): void {
    this.adapter?.destroy();
    this.adapter = null;
    this.lastEffectRevision = null;
  }

  private flush(): void {
    if (!this.adapter) return;
    const emitEffects = this.latest.revision !== this.lastEffectRevision;
    this.adapter.render(this.latest, emitEffects);
    if (emitEffects) this.lastEffectRevision = this.latest.revision;
  }
}
