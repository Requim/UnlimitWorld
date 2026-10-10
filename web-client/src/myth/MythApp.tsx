import { AlertTriangle, LoaderCircle, RefreshCw, RotateCcw, Settings } from "lucide-react";
import { useCallback, useState } from "react";

import { SettingsDrawer } from "../components/Drawers";
import { useGameSession } from "../hooks/useGameSession";
import { loadSettings, saveSettings, type GameSettings } from "../state/storage";
import { MythBattle } from "./MythBattle";
import { MythStart } from "./MythStart";
import { MythStory } from "./MythStory";
import { useMythAssets } from "./mythAssets";
import type { PresentationAdapter } from "./presentationQueue";
import { useMythPresentation } from "./useMythPresentation";

/** 独立神话样板入口；经典会话与素材不由此组件加载。 */
export default function MythApp() {
  const session = useGameSession("myth_bifang");
  const [assets, retryAssets] = useMythAssets();
  const [adapter, setAdapter] = useState<PresentationAdapter | null>(null);
  const [settings, setSettings] = useState(loadSettings);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const attachAdapter = useCallback((next: PresentationAdapter | null) => setAdapter(() => next), []);
  const presentation = useMythPresentation(session.run, session.events, adapter, session.resync);
  const run = presentation.run;
  const networkLocked = session.busy || session.uncertain;
  const stageLocked = run?.phase === "combat" && adapter === null;
  const commandLocked = networkLocked || presentation.busy || stageLocked;
  const updateSettings = (next: GameSettings) => { setSettings(next); saveSettings(next); };
  if (session.status === "unauthorized") return <RecoveryScreen message={session.error} onReset={session.resetSession} />;
  if (session.status === "error" && !run) return <LoadError message={session.error} />;
  if (session.status === "loading" || !session.catalog) return <LoadingScreen />;
  if (!run) return <MythStart catalog={session.catalog} busy={session.busy} onStart={session.startRun} />;
  return <main className={settings.reducedMotion ? "myth-shell reduced-motion" : "myth-shell"}
    data-network-busy={networkLocked} data-phase={run.phase} data-presentation-busy={presentation.busy}
    data-revision={run.revision} data-testid="myth-root">
    <MythHeader run={run} onSettings={() => setSettingsOpen(true)} />
    <MythPhase run={run} catalog={session.catalog} assets={assets} busy={commandLocked}
      reducedMotion={settings.reducedMotion} onAction={session.perform} onAdapter={attachAdapter}
      onRetryAssets={retryAssets} onReset={session.resetSession} />
    <RequestStatus session={session} presentationError={presentation.error} presentationBusy={presentation.busy} />
    {settingsOpen && <SettingsDrawer settings={settings} onChange={updateSettings} onClose={() => setSettingsOpen(false)} />}
    {settingsOpen && <button className="drawer-backdrop" aria-label="关闭面板" onClick={() => setSettingsOpen(false)} />}
  </main>;
}

type Session = ReturnType<typeof useGameSession>;

function MythPhase(props: {
  run: NonNullable<Session["run"]>; catalog: NonNullable<Session["catalog"]>;
  assets: ReturnType<typeof useMythAssets>[0]; busy: boolean; reducedMotion: boolean;
  onAction: Session["perform"]; onAdapter: (adapter: PresentationAdapter | null) => void;
  onRetryAssets: () => void; onReset: () => void;
}) {
  if (props.run.phase === "event") return <MythStory run={props.run} busy={props.busy} onAction={props.onAction} />;
  if (props.run.phase === "combat") return <MythBattle {...props} />;
  if (["completed", "game_over", "battle_won"].includes(props.run.phase)) {
    return <MythEnding run={props.run} busy={props.busy} onReset={props.onReset} />;
  }
  return <section className="myth-system"><AlertTriangle /><h1>样板局面暂不可展示</h1>
    <p>服务端阶段：{props.run.phase}</p><button onClick={props.onReset}><RotateCcw /> 返回流派选择</button></section>;
}

function MythHeader({ run, onSettings }: { run: NonNullable<Session["run"]>; onSettings: () => void }) {
  const hp = Math.max(0, run.player.hp / run.player.max_hp * 100);
  return <header className="myth-header"><div className="myth-brand"><span>山海异案</span><b>章莪山 · 毕方</b></div>
    <div className="myth-player-stats"><span>生命 <i><u style={{ width: `${hp}%` }} /></i><b>{run.player.hp}/{run.player.max_hp}</b></span>
      <span>护盾 <b>{run.player.block}</b></span><span className="wrath">天谴 <b>{run.player.wrath}</b></span></div>
    <button data-testid="settings-open" title="设置" onClick={onSettings}><Settings /></button></header>;
}

function MythEnding({ run, busy, onReset }: { run: NonNullable<Session["run"]>; busy: boolean; onReset: () => void }) {
  const won = run.phase !== "game_over";
  return <section className={`myth-ending ${won ? "victory" : "defeat"}`} data-testid={`phase-${run.phase}`}>
    <span>{won ? "案卷焚尽，证词尚存" : "章莪山记下了这一笔"}</span>
    <h1>{run.epitaph ?? (won ? "毕方收翼退入火云，仍坚持自己只负责预告。" : "修士倒下前，仍没弄清灰烬该由谁签字。")}</h1>
    <button data-testid="new-run" disabled={busy} onClick={onReset}><RotateCcw /> 重新审案</button></section>;
}

function RequestStatus({ session, presentationError, presentationBusy }: {
  session: Session; presentationError: string | null; presentationBusy: boolean;
}) {
  if (session.busy) return <div className="myth-toast"><LoaderCircle className="spin" /> 天道正在落笔</div>;
  if (presentationBusy) return <div className="myth-toast"><LoaderCircle className="spin" /> 正在播放权威结算</div>;
  const error = presentationError ?? session.error;
  if (!error) return null;
  const retry = presentationError ? session.resync : session.retryAction;
  return <div className="myth-toast error"><AlertTriangle /><span>{error}</span>
    {(presentationError || session.retryMode) && <button data-testid={presentationError ? "retry-presentation" : "retry-action"}
      onClick={() => void retry()}><RefreshCw />{session.retryMode === "action" ? "重试原动作" : "同步权威局面"}</button>}</div>;
}

function LoadingScreen() {
  return <main className="myth-system"><LoaderCircle className="spin" /><h1>正在翻检章莪山案卷</h1></main>;
}

function RecoveryScreen({ message, onReset }: { message: string | null; onReset: () => void }) {
  return <main className="myth-system"><AlertTriangle /><h1>样板凭证已失效</h1><p>{message}</p>
    <button data-testid="reset-session" onClick={onReset}><RotateCcw /> 清除本地样板档案</button></main>;
}

function LoadError({ message }: { message: string | null }) {
  return <main className="myth-system"><AlertTriangle /><h1>章莪山暂时失联</h1><p>{message}</p>
    <button data-testid="reload-client" onClick={() => window.location.reload()}><RefreshCw /> 重新连接</button></main>;
}
