import { useCallback, useEffect, useRef, useState, type RefObject } from "react";

import { ActionQueue } from "../api/actionQueue";
import { ApiError, createRun, getCatalog, getRun, isUnknownActionOutcome, sendAction } from "../api/client";
import type { ActionInput, ArchetypeId, Catalog, GameEvent, RunMode, RunView } from "../api/types";
import { clearSession, loadSession, saveSession, type StoredSession } from "../state/storage";

type SessionStatus = "loading" | "ready" | "unauthorized" | "error";
type RetryMode = "action" | "sync" | null;

/** 会话门面；输入类型化命令，返回异步完成，失败写入 error；retryMode 区分原动作重试与只读同步。 */
export interface GameSession {
  catalog: Catalog | null;
  run: RunView | null;
  events: GameEvent[];
  status: SessionStatus;
  busy: boolean;
  error: string | null;
  uncertain: boolean;
  retryMode: RetryMode;
  startRun: (archetype: ArchetypeId) => Promise<void>;
  perform: (action: ActionInput) => Promise<void>;
  retryAction: () => Promise<void>;
  /** 只读 GET 当前权威局面；不清除 unknown 动作编号，失败保留凭据并进入同步重试。 */
  resync: () => Promise<void>;
  resetSession: () => void;
}

/** 返回指定模式的匿名会话与命令；默认经典档，模式变化或卸载会使旧请求失效但不删除凭证。 */
export function useGameSession(mode: RunMode = "classic"): GameSession {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [run, setRun] = useState<RunView | null>(null);
  const [events, setEvents] = useState<GameEvent[]>([]);
  const [status, setStatus] = useState<SessionStatus>("loading");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [retryMode, setRetryMode] = useState<RetryMode>(null);
  const sessionRef = useRef<StoredSession | null>(null);
  const generationRef = useRef(0);
  const queueRef = useRef(new ActionQueue(sendAction));
  const operationRef = useRef<SessionOperation | null>(null);
  const recoveryRef = useRef<RetryMode>(null);
  const syncResumeRef = useRef<RetryMode>(null);
  const setRecovery = useCallback((mode: RetryMode) => {
    recoveryRef.current = mode;
    setRetryMode(mode);
  }, []);

  const applyResponse = useCallback((nextRun: RunView, nextEvents: GameEvent[], recovery: RetryMode = null) => {
    setRun(nextRun);
    setEvents(nextEvents);
    setError(null);
    setRecovery(recovery);
    setStatus("ready");
  }, [setRecovery]);

  const commandState: CommandState = {
    mode, sessionRef, generationRef, queueRef, operationRef, recoveryRef, syncResumeRef, run, applyResponse,
    setCatalog, setRun, setEvents, setStatus, setBusy, setError, setRecovery,
  };
  useEffect(() => {
    void initializeSession(commandState);
    return () => invalidateGeneration(commandState);
  }, [mode]);
  const startRun = useStartRunCommand(commandState);
  const perform = usePerformCommand(commandState);
  const retryAction = useRetryCommand(commandState);
  const resync = useResyncCommand(commandState);
  const resetSession = useResetCommand(commandState);

  return { catalog, run, events, status, busy, error, uncertain: retryMode !== null, retryMode,
    startRun, perform, retryAction, resync, resetSession };
}

interface SessionOperation { generation: number }

interface CommandState {
  mode: RunMode;
  sessionRef: RefObject<StoredSession | null>;
  generationRef: RefObject<number>;
  queueRef: RefObject<ActionQueue>;
  operationRef: RefObject<SessionOperation | null>;
  recoveryRef: RefObject<RetryMode>;
  syncResumeRef: RefObject<RetryMode>;
  run: RunView | null;
  applyResponse: (run: RunView, events: GameEvent[], recovery?: RetryMode) => void;
  setCatalog: (value: Catalog) => void;
  setRun: (value: RunView | null) => void;
  setEvents: (value: GameEvent[]) => void;
  setStatus: (value: SessionStatus) => void;
  setBusy: (value: boolean) => void;
  setError: (value: string | null) => void;
  setRecovery: (mode: RetryMode) => void;
}

function useStartRunCommand(state: CommandState) {
  return useCallback(async (archetype: ArchetypeId) => {
    invalidateGeneration(state);
    const operation = beginOperation(state);
    state.setRecovery(null);
    try {
      const requestedMode = state.mode === "classic" ? undefined : state.mode;
      const response = await createRun(archetype, state.sessionRef.current?.accessToken, requestedMode);
      if (!isCurrentOperation(state, operation)) return;
      if (!validateResponseMode(state, response.run)) return;
      const session = { accessToken: response.access_token, runId: response.run.run_id };
      saveSession(session, state.mode);
      state.sessionRef.current = session;
      state.applyResponse(response.run, response.events);
    } catch (cause) {
      if (isCurrentOperation(state, operation)) handleFailure(cause, state, null, true);
    } finally {
      finishOperation(state, operation);
    }
  }, [state]);
}

function usePerformCommand(state: CommandState) {
  return useCallback(async (action: ActionInput) => {
    const session = state.sessionRef.current;
    if (!session || !state.run || state.operationRef.current || state.recoveryRef.current) return;
    const operation = beginOperation(state);
    try {
      const response = await state.queueRef.current.submit(session.runId, session.accessToken, state.run.revision, action);
      if (response && isCurrentOperation(state, operation)) acceptResponse(state, response.run, response.events);
    } catch (cause) {
      if (isCurrentOperation(state, operation)) await recoverActionFailure(cause, state, operation, session);
    } finally {
      finishOperation(state, operation);
    }
  }, [state]);
}

function useRetryCommand(state: CommandState) {
  return useCallback(async () => {
    const session = state.sessionRef.current;
    const mode = state.recoveryRef.current;
    if (!session || !mode || state.operationRef.current) return;
    const operation = beginOperation(state);
    try {
      if (mode === "sync") await synchronizeSession(state, operation, session, state.syncResumeRef.current);
      else {
        const response = await state.queueRef.current.retry();
        if (response && isCurrentOperation(state, operation)) acceptResponse(state, response.run, response.events);
      }
    } catch (cause) {
      if (isCurrentOperation(state, operation)) await recoverActionFailure(cause, state, operation, session);
    } finally {
      finishOperation(state, operation);
    }
  }, [state]);
}

function useResyncCommand(state: CommandState) {
  return useCallback(async () => {
    const session = state.sessionRef.current;
    if (!session || state.operationRef.current) return;
    const operation = beginOperation(state);
    const resume = recoveryAfterSync(state);
    try {
      await synchronizeSession(state, operation, session, resume);
    } finally {
      finishOperation(state, operation);
    }
  }, [state]);
}

function useResetCommand(state: CommandState) {
  return useCallback(() => {
    invalidateGeneration(state);
    clearSession(state.mode);
    state.sessionRef.current = null;
    state.setRun(null);
    state.setEvents([]);
    state.setError(null);
    state.setRecovery(null);
    state.setBusy(false);
    state.setStatus("ready");
  }, [state]);
}

async function initializeSession(state: CommandState): Promise<void> {
  invalidateGeneration(state);
  resetVisibleSession(state);
  const operation = beginOperation(state);
  const session = loadSession(state.mode);
  state.sessionRef.current = session;
  state.setStatus("loading");
  try {
    const catalog = await getCatalog();
    if (!isCurrentOperation(state, operation)) return;
    state.setCatalog(catalog);
    const response = session ? await getRun(session.runId, session.accessToken) : null;
    if (!isCurrentOperation(state, operation)) return;
    if (response) acceptResponse(state, response.run, response.events);
    else state.setStatus("ready");
  } catch (cause) {
    if (isCurrentOperation(state, operation)) handleFailure(cause, state, null, true);
  } finally {
    finishOperation(state, operation);
  }
}

function resetVisibleSession(state: CommandState): void {
  state.syncResumeRef.current = null;
  state.setRun(null);
  state.setEvents([]);
  state.setError(null);
  state.setRecovery(null);
}

async function recoverActionFailure(
  cause: unknown,
  state: CommandState,
  operation: SessionOperation,
  session: StoredSession,
): Promise<void> {
  if (cause instanceof ApiError && cause.status === 409) {
    state.setRecovery("sync");
    await synchronizeSession(state, operation, session, null);
    return;
  }
  handleFailure(cause, state, isUnknownActionOutcome(cause) ? "action" : null);
}

async function synchronizeSession(
  state: CommandState,
  operation: SessionOperation,
  session: StoredSession,
  resume: RetryMode,
): Promise<void> {
  try {
    const snapshot = await getRun(session.runId, session.accessToken);
    if (isCurrentOperation(state, operation)) acceptResponse(state, snapshot.run, snapshot.events, resume);
  } catch (cause) {
    if (isCurrentOperation(state, operation)) {
      state.syncResumeRef.current = resume;
      handleFailure(cause, state, "sync");
    }
  }
}

function acceptResponse(
  state: CommandState,
  run: RunView,
  events: GameEvent[],
  recovery: RetryMode = null,
): boolean {
  if (!validateResponseMode(state, run, recovery)) return false;
  state.syncResumeRef.current = null;
  state.applyResponse(run, events, recovery);
  return true;
}

function validateResponseMode(state: CommandState, run: RunView, recovery: RetryMode = null): boolean {
  if ((run.mode ?? "classic") === state.mode) return true;
  state.syncResumeRef.current = recovery;
  state.setStatus("error");
  state.setRecovery(state.sessionRef.current ? "sync" : null);
  state.setError("局面模式与当前入口不匹配，请同步正确档案或重新开局");
  return false;
}

function recoveryAfterSync(state: CommandState): RetryMode {
  if (state.recoveryRef.current === "action") return "action";
  if (state.recoveryRef.current === "sync") return state.syncResumeRef.current;
  return null;
}

function handleFailure(cause: unknown, state: CommandState, mode: RetryMode, fatal = false): void {
  const unauthorized = cause instanceof ApiError && cause.status === 401;
  if (unauthorized) state.setStatus("unauthorized");
  else if (fatal) state.setStatus("error");
  state.setRecovery(unauthorized ? null : mode);
  state.setError(cause instanceof Error ? cause.message : "请求失败，请稍后重试");
}

function beginOperation(state: CommandState): SessionOperation {
  const operation = { generation: state.generationRef.current };
  state.operationRef.current = operation;
  state.setBusy(true);
  state.setError(null);
  return operation;
}

function isCurrentOperation(state: CommandState, operation: SessionOperation): boolean {
  return state.generationRef.current === operation.generation && state.operationRef.current === operation;
}

function finishOperation(state: CommandState, operation: SessionOperation): void {
  if (!isCurrentOperation(state, operation)) return;
  state.operationRef.current = null;
  state.setBusy(false);
}

function invalidateGeneration(state: CommandState): void {
  state.generationRef.current += 1;
  state.operationRef.current = null;
  state.queueRef.current.advanceGeneration();
}
