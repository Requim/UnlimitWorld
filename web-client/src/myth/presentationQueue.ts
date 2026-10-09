import type { GameEvent } from "../api/types";

type PresentationState = NonNullable<GameEvent["state_after"]>;

interface PlaybackToken {
  controller: AbortController;
  generation: number;
}

/** 一次权威响应的纯表现输入；事件索引由数组顺序确定，不包含网络命令。 */
export interface PresentationBatch {
  runId: string;
  revision: number;
  events: GameEvent[];
}

/** 播放单个权威事件；AbortSignal 通知取消，拒绝会由队列向上抛出。 */
export type PresentationAdapter = (event: GameEvent, signal: AbortSignal) => Promise<void>;

/** 表现生命周期回调；仅当前世代可触发，错误回调用于请求权威 GET 同步。 */
export interface PresentationCallbacks {
  onStateAfter?: (state: PresentationState, event: GameEvent) => void;
  onComplete?: (batch: PresentationBatch) => void;
  onError?: (cause: unknown) => void;
  onBusyChange?: (busy: boolean) => void;
}

/** 顺序消费权威事件并按局号、revision、事件索引去重；不计算战斗结果或发网络请求。 */
export class PresentationQueue {
  private adapter: PresentationAdapter;
  private readonly seen = new Set<string>();
  private readonly retiredRuns = new Set<string>();
  private activeRunId: string | null = null;
  private highestRevision = -1;
  private token: PlaybackToken | null = null;
  private generation = 0;
  private disposed = false;
  private presenting = false;

  /** 注入单事件 adapter 与可选生命周期回调；构造时不启动播放或网络副作用。 */
  public constructor(adapter: PresentationAdapter, private readonly callbacks: PresentationCallbacks = {}) {
    this.adapter = adapter;
  }

  /** 当前是否持有表现锁；取消、失败或完成会及时释放。 */
  public get busy(): boolean { return this.presenting; }

  /** 提交权威事件批次；重复或过期批次直接忽略，adapter 失败会回调并原样抛出。 */
  public enqueue(batch: PresentationBatch): Promise<void> {
    if (this.disposed || this.retiredRuns.has(batch.runId)) return Promise.resolve();
    if (!this.activateBatch(batch)) return Promise.resolve();
    const pending = this.unseenEvents(batch);
    if (pending.length === 0) return Promise.resolve();
    return this.play(batch, pending);
  }

  /** 替换表现资源适配器；取消旧播放但保留已开始事件去重，避免重附着重复攻击。 */
  public replaceAdapter(adapter: PresentationAdapter): void {
    this.adapter = adapter;
    this.invalidatePlayback();
  }

  /** 取消当前播放；释放表现锁并使不合作 adapter 的迟到完成失效。 */
  public cancel(): void { this.invalidatePlayback(); }

  /** 永久停用队列；释放当前资源，后续批次均被忽略。 */
  public dispose(): void {
    this.disposed = true;
    this.invalidatePlayback();
  }

  private activateBatch(batch: PresentationBatch): boolean {
    if (this.activeRunId !== batch.runId) return this.activateRun(batch);
    if (batch.revision < this.highestRevision) return false;
    if (this.presenting && batch.revision === this.highestRevision) return false;
    if (batch.revision === this.highestRevision) return true;
    return this.activateRevision(batch);
  }

  private activateRun(batch: PresentationBatch): boolean {
    if (this.activeRunId) this.retiredRuns.add(this.activeRunId);
    this.activeRunId = batch.runId;
    this.highestRevision = batch.revision;
    return this.ownsActivation(batch, this.invalidatePlayback());
  }

  private activateRevision(batch: PresentationBatch): boolean {
    this.highestRevision = batch.revision;
    if (!this.presenting) return true;
    return this.ownsActivation(batch, this.invalidatePlayback());
  }

  private ownsActivation(batch: PresentationBatch, generation: number): boolean {
    return this.generation === generation
      && this.activeRunId === batch.runId
      && this.highestRevision === batch.revision
      && !this.presenting;
  }

  private unseenEvents(batch: PresentationBatch): Array<[number, GameEvent]> {
    return batch.events.flatMap((event, index) => this.seen.has(this.eventKey(batch, index)) ? [] : [[index, event]]);
  }

  private async play(batch: PresentationBatch, events: Array<[number, GameEvent]>): Promise<void> {
    const token = this.beginPlayback();
    try {
      for (const [index, event] of events) {
        if (!this.isCurrent(token)) return;
        this.seen.add(this.eventKey(batch, index));
        await this.adapter(event, token.controller.signal);
        if (!this.isCurrent(token)) return;
        if (event.state_after) this.callbacks.onStateAfter?.(event.state_after, event);
      }
      if (!this.isCurrent(token)) return;
      this.callbacks.onComplete?.(batch);
    } catch (cause) {
      if (!this.isCurrent(token)) return;
      if (this.releasePlayback(token)) this.callbacks.onError?.(cause);
      throw cause;
    } finally {
      this.releasePlayback(token);
    }
  }

  private beginPlayback(): PlaybackToken {
    const controller = new AbortController();
    const token = { controller, generation: ++this.generation };
    this.token = token;
    this.setBusy(true);
    return token;
  }

  private releasePlayback(token: PlaybackToken): boolean {
    if (!this.isCurrent(token)) return false;
    this.token = null;
    const releaseGeneration = ++this.generation;
    this.setBusy(false);
    return this.generation === releaseGeneration;
  }

  private invalidatePlayback(): number {
    const token = this.token;
    const invalidationGeneration = ++this.generation;
    token?.controller.abort();
    if (this.generation !== invalidationGeneration || this.token !== token) return invalidationGeneration;
    this.token = null;
    this.setBusy(false);
    return invalidationGeneration;
  }

  private isCurrent(token: PlaybackToken): boolean {
    return this.token === token
      && this.generation === token.generation
      && !token.controller.signal.aborted;
  }

  private setBusy(value: boolean): void {
    if (this.presenting === value) return;
    this.presenting = value;
    this.callbacks.onBusyChange?.(value);
  }

  private eventKey(batch: PresentationBatch, index: number): string {
    return `${batch.runId}:${batch.revision}:${index}`;
  }
}
