const ROUTE = ['combat', 'event', 'elite', 'shop', 'combat', 'elite', 'event', 'rest', 'boss'];

/** Select an available next node from a public run; returns a node, with no mutation. */
export function chooseNode(run) {
  const available = run.map.nodes.filter((node) => node.available);
  return available.find((node) => node.kind === ROUTE[run.layer]) ?? available[0];
}

/** Rank affordable public hand cards for QA; returns an instance or null, never resolves rules. */
export function chooseCard(run, definitions) {
  const cards = run.combat.hand.map((card) => {
    const definition = definitions.find((item) => item.id === card.card_id);
    if (!definition) throw new Error(`Unknown catalog card: ${card.card_id}`);
    const cost = card.upgraded ? definition.upgraded_cost : definition.cost;
    return { card, definition, cost, rank: rankCard(run, card, definition) };
  });
  const affordable = cards.filter((item) => item.cost <= run.combat.energy);
  affordable.sort((first, second) => second.rank - first.rank);
  return affordable[0]?.card ?? null;
}

function rankCard(run, card, definition) {
  if (['focus', 'swift_script'].includes(card.card_id)) return 110;
  if (card.card_id === 'borrow_fire') return 105;
  const intent = run.combat.enemy.intent;
  const incoming = intent.kind === 'defend' ? 0 : intent.value * intent.hits;
  const bolts = Math.max(0, run.combat.thunder_count - Number(run.combat.lightning_redirect));
  const exposed = incoming + bolts * run.combat.thunder_damage > run.player.block;
  if (definition.target === 'self' && exposed) return 90;
  if (card.card_id === 'lightning_talisman' && bolts > 0) return 100;
  if (definition.target === 'enemy') return card.card_id === 'flying_sword' ? 60 : 70;
  return 20;
}
