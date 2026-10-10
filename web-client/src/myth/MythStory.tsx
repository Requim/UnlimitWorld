import type { ActionInput, RunView } from "../api/types";

/** 完整展示服务器剧情与代价；选择只提交 ID，不解析文字或计算开战属性。 */
export function MythStory({ run, busy, onAction }: {
  run: RunView; busy: boolean; onAction: (action: ActionInput) => void;
}) {
  if (!run.story) return <section className="myth-story"><h1>剧情档案缺失</h1></section>;
  return <section className="myth-story" data-testid="phase-story">
    <span className="myth-eyebrow">章莪山 · 灰烬为证</span>
    <h1>{run.story.title}</h1>
    <p className="myth-story-body">{run.story.body}</p>
    <div className="myth-story-choices">
      {run.story.choices.map((choice) => <button key={choice.id} disabled={busy}
        data-testid={`story-choice-${choice.id}`} onClick={() => onAction({ kind: "choose_event", choice_id: choice.id })}>
        <strong>{choice.label}</strong><span>{choice.consequence}</span>
      </button>)}
    </div>
  </section>;
}
