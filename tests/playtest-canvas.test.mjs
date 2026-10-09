import test from 'node:test';
import assert from 'node:assert/strict';
import { verifyStaticCanvasUpdate } from '../tools/playtest-canvas.mjs';

test('frozen canvas fails instead of merely returning a false report flag', async () => {
  const image = Buffer.from('frozen-renderer');
  await assert.rejects(verifyStaticCanvasUpdate(image, async () => image), /Canvas did not update/);
});

test('autonomous animation cannot masquerade as an authority update', async () => {
  const before = Buffer.from('before');
  const frames = [Buffer.from('tween-frame-1'), Buffer.from('tween-frame-2')];
  await assert.rejects(verifyStaticCanvasUpdate(before, async () => frames.shift()), /Canvas is not static/);
});

test('a changed and stable reduced-motion frame passes the update contract', async () => {
  const after = Buffer.from('authority-rendered');
  assert.equal(await verifyStaticCanvasUpdate(Buffer.from('before'), async () => after), true);
});
