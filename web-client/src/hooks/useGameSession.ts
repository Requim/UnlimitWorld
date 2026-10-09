import { useCallback, useEffect, useRef, useState, type RefObject } from "react";

import { ActionQueue } from "../api/actionQueue";
import { ApiError, createRun, getCatalog, getRun, sendAction } from "../api/client";
import type { ActionInput, ArchetypeId, Catalog, GameEvent, RunView } from "../api/types";
import { clearSession, loadSession, saveSession, type StoredSession } from "../state/storage";

type SessionStatus = "loading" | "ready" | "unauthorized" | "error";

/** React UI 使用的会话门面；动作方法会访问真实 API 并可能产生网络错误状态。 */
export interface GameSession {
  catalog: Catalog | null;
  run: RunView | null;
  events: GameEvent[];
  status: SessionStatus;
  busy: boolean;
  error: string | null;
  uncertain: boolean;
  startRun: (archetype: ArchetypeId) => Promise<void>;
  perform: (action: ActionInput) => Promise<void>;
  retryAction: () => Promise<void>;
  resetSession: () => void;
}

/** 管理匿名档案、权威局面与动作提交；所有状态变更均来自 HTTP 响应。 */
export function useGameSession(): GameSession {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [run, setRun] = useState<RunView | null>(null);
  const [events, setEvents] = useState<GameEvent[]>([]);
  const [status, setStatus] = useState<SessionStatus>("loading");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [uncertain, setUncertain] = useState(false);
  const sessionRef = useRef<StoredSession | null>(loadSession());
  const generationRef = useRef(0);
  const queueRef = useRef(new ActionQueue(sendAction));

  useEffect(() => {
    void initializeSession({ setCatalog, setRun, setEvents, setStatus, setError }, sessionRef.current);
  }, []);

  const applyResponse = useCallback((nextRun: RunView, nextEvents: GameEvent[]) => {
    setRun(nextRun);
    setEvents(nextEvents);
    setError(null);
    setUncertain(false);
    setStatus("ready");
  }, []);

  const commandState = {
    sessionRef, generationRef, queueRef, run, busy, applyResponse,
    setRun, setEvents, setStatus, setBusy, setError, setUncertain,
  };
  const startRun = useStartRunCommand(commandState);
  const perform = usePerformCommand(commandState);
  const retryAction = useRetryCommand(commandState);
  const resetSession = useResetCommand(commandState);

  return { catalog, run, events, status, busy, error, uncertain, startRun, perform, retryAction, resetSession };
}

interface CommandState {
  sessionRef: RefObject<StoredSession | null>;
  generationRef: RefObject<number>;
  queueRef: RefObject<ActionQueue>;
  run: RunView | null;
  busy: boolean;
  applyResponse: (run: RunView, events: GameEvent[]) => void;
  setRun: (value: RunView | null) => void;
  setEvents: (value: GameEvent[]) => void;
  setStatus: (value: SessionStatus) => void;
  setBusy: (value: boolean) => void;
  setError: (value: string | null) => void;
  setUncertain: (value: boolean) => void;
}

function useStartRunCommand(state: CommandState) {
  return useCallback(async (archetype: ArchetypeId) => {
    const generation = ++state.generationRef.current;
    state.queueRef.current.advanceGeneration();
    state.setBusy(true);
    state.setError(null);
    try {
      const response = await createRun(archetype, state.sessionRef.current?.accessToken);
      if (generation !== state.generationRef.current) return;
      state.sessionRef.current = { accessToken: response.access_token, runId: response.run.run_id };
      saveSession(state.sessionRef.current);
      state.applyResponse(response.run, response.events);
    } catch (cause) {
      handleFailure(cause, state.setStatus, state.setError, state.setUncertain);
    } finally {
      if (generation === state.generationRef.current) state.setBusy(false);
    }
  }, [state]);
}

function usePerformCommand(state: CommandState) {
  return useCallback(async (action: ActionInput) => {
    const session = state.sessionRef.current;
    if (!session || !state.run || state.busy) return;
    state.setBusy(true);
    state.setError(null);
    try {
      const response = await state.queueRef.current.submit(session.runId, session.accessToken, state.run.revision, action);
      if (response) state.applyResponse(response.run, response.events);
    } catch (cause) {
      await recoverActionFailure(cause, session, state.applyResponse, state.setStatus, state.setError, state.setUncertain);
    } finally {
      state.setBusy(false);
    }
  }, [state]);
}

function useRetryCommand(state: CommandState) {
  return useCallback(async () => {
    state.setBusy(true);
    try {
      const response = await state.queueRef.current.retry();
      if (response) state.applyResponse(response.run, response.events);
    } catch (cause) {
      const session = state.sessionRef.current;
      if (session) await recoverActionFailure(cause, session, state.applyResponse, state.setStatus, state.setError, state.setUncertain);
    } finally {
      state.setBusy(false);
    }
  }, [state]);
}

function useResetCommand(state: CommandState) {
  return useCallback(() => {
    state.generationRef.current += 1;
    state.queueRef.current.advanceGeneration();
    clearSession();
    state.sessionRef.current = null;
    state.setRun(null);
    state.setEvents([]);
    state.setError(null);
    state.setUncertain(false);
    state.setStatus("ready");
  }, [state]);
}

interface InitializationSetters {
  setCatalog: (value: Catalog) => void;
  setRun: (value: RunView) => void;
  setEvents: (value: GameEvent[]) => void;
  setStatus: (value: SessionStatus) => void;
  setError: (value: string | null) => void;
}

async function initializeSession(setters: InitializationSetters, session: StoredSession | null): Promise<void> {
  try {
    const catalog = await getCatalog();
    setters.setCatalog(catalog);
    const response = session ? await getRun(session.runId, session.accessToken) : null;
    if (response) {
      setters.setRun(response.run);
      setters.setEvents(response.events);
    }
    setters.setStatus("ready");
  } catch (cause) {
    const unauthorized = cause instanceof ApiError && cause.status === 401;
    setters.setStatus(unauthorized ? "unauthorized" : "error");
    setters.setError(errorMessage(cause));
  }
}

async function recoverActionFailure(
  cause: unknown,
  session: StoredSession,
  apply: (run: RunView, events: GameEvent[]) => void,
  setStatus: (value: SessionStatus) => void,
  setError: (value: string | null) => void,
  setUncertain: (value: boolean) => void,
): Promise<void> {
  if (cause instanceof ApiError && cause.status === 409) {
    const snapshot = await getRun(session.runId, session.accessToken);
    apply(snapshot.run, snapshot.events);
    return;
  }
  handleFailure(cause, setStatus, setError, setUncertain);
}

function handleFailure(
  cause: unknown,
  setStatus: (value: SessionStatus) => void,
  setError: (value: string | null) => void,
  setUncertain: (value: boolean) => void,
): void {
  if (cause instanceof ApiError && cause.status === 401) setStatus("unauthorized");
  setUncertain(cause instanceof TypeError);
  setError(errorMessage(cause));
}

function errorMessage(cause: unknown): string {
  return cause instanceof Error ? cause.message : "请求失败，请稍后重试";
}
