import assert from 'node:assert/strict';

/** Capture two PNG buffers through capture; returns a stable frame or throws when autonomous rendering still moves. */
export async function captureStaticCanvas(capture) {
  const first = await capture();
  const second = await capture();
  assert.ok(first.equals(second), 'Canvas is not static under reduced motion');
  return first;
}

/** Compare a previous PNG with a stable newly captured frame; returns true, throws on frozen or moving output. */
export async function verifyStaticCanvasUpdate(before, capture) {
  const after = await captureStaticCanvas(capture);
  assert.ok(!before.equals(after), 'Canvas did not update after authority action');
  return true;
}
