import type { GameEvent } from "../api/types";

type PresentationState = NonNullable<GameEvent["state_after"]>;

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
  private controller: AbortController | null = null;
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
    if (this.activeRunId !== batch.runId) this.switchRun(batch.runId);
    if (batch.revision < this.highestRevision) return false;
    if (this.presenting && batch.revision === this.highestRevision) return false;
    if (batch.revision > this.highestRevision) {
      if (this.presenting) this.invalidatePlayback();
      this.highestRevision = batch.revision;
    }
    return true;
  }

  private switchRun(runId: string): void {
    if (this.activeRunId) this.retiredRuns.add(this.activeRunId);
    this.invalidatePlayback();
    this.activeRunId = runId;
    this.highestRevision = -1;
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
        await this.adapter(event, token.signal);
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

  private beginPlayback(): AbortController {
    const controller = new AbortController();
    this.controller = controller;
    this.setBusy(true);
    return controller;
  }

  private releasePlayback(controller: AbortController): boolean {
    if (!this.isCurrent(controller)) return false;
    this.controller = null;
    this.setBusy(false);
    return this.controller === null;
  }

  private invalidatePlayback(): void {
    this.controller?.abort();
    this.controller = null;
    this.setBusy(false);
  }

  private isCurrent(controller: AbortController): boolean {
    return this.controller === controller && !controller.signal.aborted;
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
