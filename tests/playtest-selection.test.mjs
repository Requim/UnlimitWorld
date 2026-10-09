import test from 'node:test';
import assert from 'node:assert/strict';
import { ensureCardSelected } from '../tools/playtest-selection.mjs';

function cardLocator(selected, prefix = 'card-tile') {
  return {
    selected, clicks: 0,
    async getAttribute() { return `${prefix}${this.selected ? ' selected' : ''}`; },
    async click() { this.selected = !this.selected; this.clicks += 1; },
  };
}

test('a card still selected after redraw must not be toggled off', async () => {
  const card = cardLocator(true);
  await ensureCardSelected(card);
  assert.equal(card.selected, true);
  assert.equal(card.clicks, 0);
});

test('an unselected hand card is selected with one normal click', async () => {
  const card = cardLocator(false);
  await ensureCardSelected(card);
  assert.equal(card.selected, true);
  assert.equal(card.clicks, 1);
});

test('an unrelated class containing selected is not selection state', async () => {
  const card = cardLocator(false, 'card-tile school-selected-example');
  await ensureCardSelected(card);
  assert.equal(card.selected, true);
  assert.equal(card.clicks, 1);
});
