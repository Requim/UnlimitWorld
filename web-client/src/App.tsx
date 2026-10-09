import { AlertTriangle, LoaderCircle, RefreshCw, RotateCcw } from "lucide-react";
import { useState } from "react";

import { DeckDrawer, SettingsDrawer } from "./components/Drawers";
import { GameHud } from "./components/GameHud";
import { PhaseRouter } from "./components/phaseRouter";
import { StartScreen } from "./components/StartScreen";
import { useAssets } from "./game/useAssets";
import { useEventAudio } from "./game/audio";
import { useGameSession } from "./hooks/useGameSession";
import { loadSettings, saveSettings, type GameSettings } from "./state/storage";

/** 组装客户端会话与全部游戏视图；不持有战斗规则或可伪造局面。 */
export default function App() {
  const session = useGameSession();
  const [assets, retryAssets] = useAssets();
  const [settings, setSettings] = useState(loadSettings);
  const [drawer, setDrawer] = useState<"deck" | "settings" | null>(null);
  const [choosingNewRun, setChoosingNewRun] = useState(false);
  const updateSettings = (next: GameSettings) => { setSettings(next); saveSettings(next); };
  useEventAudio(session.events, settings);
  if (session.status === "error" && !session.catalog) return <LoadErrorScreen message={session.error} />;
  if (session.status === "loading" || !session.catalog) return <LoadingScreen />;
  if (session.status === "unauthorized") return <UnauthorizedScreen message={session.error} onReset={session.resetSession} />;
  if (!session.run || choosingNewRun) {
    return <StartScreen catalog={session.catalog} busy={session.busy}
      onStart={(archetype) => { setChoosingNewRun(false); void session.startRun(archetype); }} />;
  }
  return (
    <main className={settings.reducedMotion ? "game-shell reduced-motion" : "game-shell"}
      data-phase={session.run.phase} data-revision={session.run.revision} data-testid="game-root">
      <GameHud run={session.run} onDeck={() => setDrawer("deck")} onSettings={() => setDrawer("settings")} />
      <PhaseRouter phase={session.run.phase} run={session.run} catalog={session.catalog} events={session.events}
        assets={assets} busy={session.busy} reducedMotion={settings.reducedMotion} onAction={session.perform}
        onRetryAssets={retryAssets} onNewRun={() => setChoosingNewRun(true)} />
      <RequestStatus busy={session.busy} error={session.error} uncertain={session.uncertain}
        onRetry={() => void session.retryAction()} />
      {drawer === "deck" && <DeckDrawer run={session.run} catalog={session.catalog} onClose={() => setDrawer(null)} />}
      {drawer === "settings" && <SettingsDrawer settings={settings} onChange={updateSettings} onClose={() => setDrawer(null)} />}
      {drawer && <button className="drawer-backdrop" aria-label="关闭面板" onClick={() => setDrawer(null)} />}
    </main>
  );
}

function LoadingScreen() {
  return <main className="system-screen"><LoaderCircle className="spin" /><h1>正在接通天道</h1><p>读取目录与本机匿名档案</p></main>;
}

function UnauthorizedScreen({ message, onReset }: { message: string | null; onReset: () => void }) {
  return <main className="system-screen"><AlertTriangle /><h1>档案凭证已失效</h1><p>{message ?? "无法恢复这局游戏"}</p>
    <button data-testid="reset-session" onClick={onReset}><RotateCcw /> 清除凭证并新开一局</button></main>;
}

function LoadErrorScreen({ message }: { message: string | null }) {
  return <main className="system-screen"><AlertTriangle /><h1>天道暂时失联</h1><p>{message ?? "目录加载失败"}</p>
    <button data-testid="reload-client" onClick={() => window.location.reload()}><RefreshCw /> 重新连接</button></main>;
}

function RequestStatus({ busy, error, uncertain, onRetry }: { busy: boolean; error: string | null; uncertain: boolean; onRetry: () => void }) {
  if (busy) return <div className="request-toast"><LoaderCircle className="spin" /> 天道正在落笔</div>;
  if (!error) return null;
  return <div className="request-toast error"><AlertTriangle /><span>{error}</span>
    {uncertain && <button data-testid="retry-action" onClick={onRetry}><RefreshCw /> 重试原动作</button>}</div>;
}
