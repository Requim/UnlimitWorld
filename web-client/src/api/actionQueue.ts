import type { ActionInput, ActionRequest, RunResponse } from "./types";
import { isUnknownActionOutcome } from "./client";

/** 发送已编号动作；输入局号、Bearer 与完整动作，失败保持原异常语义。 */
export type ActionTransport = (
  runId: string,
  token: string,
  action: ActionRequest,
) => Promise<RunResponse>;

interface PendingAction {
  runId: string;
  token: string;
  request: ActionRequest;
  generation: number;
}

/** 管理动作幂等编号；网络结果未知时保留原请求供显式重试。 */
export class ActionQueue {
  private generation = 0;
  private pending: PendingAction | null = null;

  public constructor(private readonly transport: ActionTransport) {}

  /** 输入局号/凭证/版本/动作，返回权威响应；未知结果保留请求，过期请求返回 null，明确拒绝抛原错误。 */
  public async submit(
    runId: string,
    token: string,
    revision: number,
    input: ActionInput,
  ): Promise<RunResponse | null> {
    if (this.pending) throw new Error("仍有结果未知的动作，请先重试或同步权威局面");
    const request = { ...input, action_id: crypto.randomUUID(), expected_revision: revision } as ActionRequest;
    this.pending = { runId, token, request, generation: this.generation };
    return this.sendPending();
  }

  /** 重试最近一次结果未知的动作；没有待重试动作时抛出错误。 */
  public async retry(): Promise<RunResponse | null> {
    if (!this.pending) throw new Error("没有可重试的动作");
    return this.sendPending();
  }

  /** 使旧局面的异步响应失效；创建或恢复不同局面时调用。 */
  public advanceGeneration(): void {
    this.generation += 1;
    this.pending = null;
  }

  private async sendPending(): Promise<RunResponse | null> {
    const pending = this.pending;
    if (!pending) throw new Error("没有待提交动作");
    try {
      const response = await this.transport(pending.runId, pending.token, pending.request);
      if (!this.ownsPending(pending)) return null;
      this.pending = null;
      return response;
    } catch (error) {
      if (!this.ownsPending(pending)) return null;
      if (!isUnknownActionOutcome(error)) this.pending = null;
      throw error;
    }
  }

  private ownsPending(pending: PendingAction): boolean {
    return pending.generation === this.generation && this.pending === pending;
  }
}
