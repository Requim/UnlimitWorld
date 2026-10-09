import test from 'node:test';
import assert from 'node:assert/strict';
import { chooseCard, chooseNode } from '../tools/playtest-policy.mjs';

const definitions = [
  { id: 'guard', target: 'self', cost: 1, upgraded_cost: 1 },
  { id: 'flying_sword', target: 'enemy', cost: 1, upgraded_cost: 1 },
  { id: 'focus', target: 'none', cost: 1, upgraded_cost: 1 },
];

function battle(energy, block, intent) {
  return {
    player: { block },
    combat: {
      energy, thunder_count: 0, thunder_damage: 8, lightning_redirect: false,
      enemy: { intent }, hand: [
        { uid: 'g', card_id: 'guard', upgraded: false },
        { uid: 's', card_id: 'flying_sword', upgraded: false },
      ],
    },
  };
}

test('policy guards an exposed attack but attacks during defense', () => {
  const attack = battle(3, 0, { kind: 'attack', value: 8, hits: 1 });
  const defense = battle(3, 0, { kind: 'defend', value: 5, hits: 1 });
  assert.equal(chooseCard(attack, definitions).uid, 'g');
  assert.equal(chooseCard(defense, definitions).uid, 's');
});

test('policy never chooses an unaffordable card', () => {
  assert.equal(chooseCard(battle(0, 0, { kind: 'attack', value: 4, hits: 1 }), definitions), null);
});

test('policy only chooses currently available map nodes', () => {
  const run = { layer: 3, map: { nodes: [
    { id: 'locked', kind: 'shop', available: false },
    { id: 'rest', kind: 'rest', available: true },
  ] } };
  assert.equal(chooseNode(run).id, 'rest');
});

test('policy prefers the planned shop when accessible', () => {
  const run = { layer: 3, map: { nodes: [
    { id: 'rest', kind: 'rest', available: true },
    { id: 'shop', kind: 'shop', available: true },
  ] } };
  assert.equal(chooseNode(run).id, 'shop');
});
