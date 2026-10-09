import type { ActionInput, Catalog, GameEvent, RunView } from "../api/types";
import type { AssetState } from "../game/useAssets";
import { CombatView } from "./CombatView";
import { EndView } from "./EndView";
import { MapView } from "./MapView";
import { EventView, RestView, RewardView, ShopView, UpgradeView } from "./NodeViews";

type RunPhase = RunView["phase"];

interface PhaseRouterProps {
  phase: RunPhase;
  run?: RunView;
  catalog?: Catalog;
  events?: GameEvent[];
  assets?: AssetState;
  busy?: boolean;
  reducedMotion?: boolean;
  onAction?: (action: ActionInput) => void;
  onRetryAssets?: () => void;
  onNewRun?: () => void;
}

const PHASE_LABELS: Record<RunPhase, string> = {
  map: "九层命途",
  combat: "斗法",
  battle_won: "胜负已定",
  reward: "择取机缘",
  event: "因果奇遇",
  shop: "黑市",
  rest: "歇脚",
  rest_upgrade: "点化卡牌",
  completed: "飞升功成",
  game_over: "道消身陨",
};

/** 渲染阶段出口；输入服务端 phase，未知值由 TypeScript 阻止。 */
export function PhaseRouter(props: PhaseRouterProps) {
  const { phase, run, catalog } = props;
  if (!run || !catalog) return <section data-testid={`phase-${phase}`}>{PHASE_LABELS[phase]}</section>;
  const common = { run, catalog, busy: props.busy ?? false, onAction: props.onAction ?? noopAction };
  if (phase === "map") return <MapView {...common} />;
  if (phase === "combat") return <CombatView {...common} events={props.events ?? []}
    assets={props.assets ?? EMPTY_ASSETS} reducedMotion={props.reducedMotion ?? false}
    onRetryAssets={props.onRetryAssets ?? noop} />;
  if (phase === "reward") return <RewardView {...common} />;
  if (phase === "event") return <EventView {...common} />;
  if (phase === "shop") return <ShopView {...common} />;
  if (phase === "rest") return <RestView {...common} />;
  if (phase === "rest_upgrade") return <UpgradeView {...common} />;
  if (phase === "completed" || phase === "game_over") {
    return <EndView run={run} busy={props.busy ?? false} onNewRun={props.onNewRun ?? noop} />;
  }
  return <section className="phase-error" data-testid={`phase-${phase}`}>战斗已结束，正在等待权威奖励局面。</section>;
}

const EMPTY_ASSETS: AssetState = { status: "loading", manifest: null, message: null };
const noop = () => undefined;
const noopAction = (_action: ActionInput) => undefined;
