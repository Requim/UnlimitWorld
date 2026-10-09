import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { mkdir, writeFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { parseArgs } from 'node:util';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { chooseCard, chooseNode } from './playtest-policy.mjs';
import { captureStaticCanvas, verifyStaticCanvasUpdate } from './playtest-canvas.mjs';
import { ensureCardSelected } from './playtest-selection.mjs';

const require = createRequire(new URL('../web-client/package.json', import.meta.url));
const { chromium, expect } = require('@playwright/test');
const SESSION_KEY = 'tiandao.cardRogue.session.v1';
const ROOT = '[data-phase][data-revision]';
const recoveries = new WeakMap();

/** Read the browser's normal anonymous session for QA; never print or mutate its token. */
async function readSession(page) {
  const session = await page.evaluate((key) => JSON.parse(localStorage.getItem(key)), SESSION_KEY);
  assert.ok(session?.accessToken && session?.runId, 'No persisted anonymous session');
  return session;
}

/** Fetch a public authority snapshot using the browser token; throws on HTTP errors. */
async function readRun(page, baseUrl) {
  const session = await readSession(page);
  const response = await page.request.get(`${baseUrl}/api/v2/runs/${session.runId}`, {
    headers: { Authorization: `Bearer ${session.accessToken}` },
  });
  assert.equal(response.status(), 200, `Snapshot HTTP ${response.status()}`);
  return (await response.json()).run;
}

async function waitRevision(page, revision) {
  await expect(page.locator(ROOT)).toHaveAttribute('data-revision', String(revision), { timeout: 10000 });
}

async function clickAdvance(page, baseUrl, testId) {
  const before = await readRun(page, baseUrl);
  await page.getByTestId(testId).click();
  await expect.poll(async () => {
    const current = await page.locator(ROOT).getAttribute('data-revision');
    if (current === String(before.revision + 1)) return 'advanced';
    return await page.getByTestId('retry-action').isVisible() ? 'retry' : 'waiting';
  }, { timeout: 10000 }).not.toBe('waiting');
  if (await page.locator(ROOT).getAttribute('data-revision') !== String(before.revision + 1)) {
    await page.getByTestId('retry-action').click();
    recoveries.set(page, (recoveries.get(page) ?? 0) + 1);
  }
  await waitRevision(page, before.revision + 1);
  return readRun(page, baseUrl);
}

async function startRun(page, baseUrl, archetype) {
  await page.goto(baseUrl);
  await page.getByTestId(`create-${archetype}`).click();
  await expect(page.locator(ROOT)).toHaveAttribute('data-phase', 'map');
  return readRun(page, baseUrl);
}

async function castCard(page, baseUrl, run, card, definitions) {
  const definition = definitions.find((item) => item.id === card.card_id);
  const tile = page.getByTestId(`hand-card-${card.uid}`);
  await ensureCardSelected(tile);
  await expect(tile).toHaveClass(/(^|\s)selected(\s|$)/);
  const target = definition.target === 'enemy' ? 'enemy-target' : 'cast-selected';
  return clickAdvance(page, baseUrl, target);
}

async function combatStep(page, baseUrl, run, definitions) {
  const card = chooseCard(run, definitions);
  if (card) return castCard(page, baseUrl, run, card, definitions);
  if (run.combat.taunt_preview.available) return clickAdvance(page, baseUrl, 'taunt');
  return clickAdvance(page, baseUrl, 'end-turn');
}

async function rewardStep(page, baseUrl, run, skipped) {
  if (!skipped && run.layer >= 5) {
    return { run: await clickAdvance(page, baseUrl, 'skip-reward'), skipped: true };
  }
  const desired = ['myriad_swords', 'sword_draw', 'charge_sword', 'flurry', 'flying_sword'];
  const ranks = run.reward.cards.map((card) => desired.indexOf(card.card_id));
  const best = ranks.reduce((result, rank, index) => rank >= 0 && rank < result.rank
    ? { rank, index } : result, { rank: Infinity, index: 0 });
  return { run: await clickAdvance(page, baseUrl, `reward-${best.index}`), skipped };
}

async function shopStep(page, baseUrl, run) {
  const relic = run.shop.items.find((item) => item.kind === 'relic' && !item.purchased);
  if (relic && run.player.stones >= relic.price) {
    return clickAdvance(page, baseUrl, `shop-buy-${relic.id}`);
  }
  if (!run.shop.removal_used && run.player.stones >= run.shop.removal_price) {
    const candidate = run.deck.find((card) => card.card_id === 'guard') ?? run.deck[0];
    const removal = page.getByTestId(`remove-${candidate.uid}`);
    if (!(await removal.isVisible())) await page.getByRole('button', { name: /移除.*卡牌|移除一张|移除服务/ }).click();
    return clickAdvance(page, baseUrl, `remove-${candidate.uid}`);
  }
  const card = run.shop.items.find((item) => item.kind === 'card' && !item.purchased);
  if (card && run.player.stones >= card.price) {
    return clickAdvance(page, baseUrl, `shop-buy-${card.id}`);
  }
  return clickAdvance(page, baseUrl, 'leave-shop');
}

async function nodeStep(page, baseUrl, run) {
  if (run.phase === 'map') return clickAdvance(page, baseUrl, `map-node-${chooseNode(run).id}`);
  if (run.phase === 'shop') return shopStep(page, baseUrl, run);
  if (run.phase === 'event') {
    const choice = run.player.hp < 42 ? 'heal' : run.choices[0].id;
    return clickAdvance(page, baseUrl, `event-${choice}`);
  }
  if (run.phase === 'rest') return clickAdvance(page, baseUrl, 'rest-upgrade');
  if (run.phase === 'rest_upgrade') {
    const card = run.deck.find((item) => !item.upgraded && item.card_id === 'flying_sword')
      ?? run.deck.find((item) => !item.upgraded);
    return clickAdvance(page, baseUrl, `upgrade-${card.uid}`);
  }
  throw new Error(`Unsupported playable phase: ${run.phase}`);
}

async function capture(page, out, name) {
  const filename = path.join(out, `${name}.png`);
  await page.screenshot({ path: filename, fullPage: true });
  return filename;
}

async function runJourney(page, baseUrl, definitions, out) {
  let run = await startRun(page, baseUrl, 'sword');
  const phases = new Set();
  let skipped = false;
  for (let step = 0; step < 600; step++) {
    if (!phases.has(run.phase)) await capture(page, out, `desktop-${run.phase}`);
    phases.add(run.phase);
    if (['completed', 'game_over'].includes(run.phase)) break;
    if (run.phase === 'combat') run = await combatStep(page, baseUrl, run, definitions);
    else if (run.phase === 'reward') {
      ({ run, skipped } = await rewardStep(page, baseUrl, run, skipped));
    } else run = await nodeStep(page, baseUrl, run);
  }
  assert.equal(run.phase, 'completed', `Normal UI route ended at ${run.phase}, layer ${run.layer}`);
  assert.equal(run.layer, 9);
  assert.ok(run.epitaph);
  const previous = await readSession(page);
  await page.getByTestId('new-run').click();
  await page.getByTestId('create-fire').click();
  await expect(page.locator(ROOT)).toHaveAttribute('data-phase', 'map');
  const next = await readSession(page);
  assert.ok(next.accessToken === previous.accessToken, 'New run lost local causal profile');
  assert.notEqual(next.runId, previous.runId);
  return {
    terminal: run.phase, layer: run.layer, hp: run.player.hp,
    phases: [...phases], skippedReward: skipped, recoveredNetworkActions: recoveries.get(page) ?? 0,
  };
}

async function assertLayout(page, viewport) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
  assert.equal(overflow, false, `Body overflow at ${viewport.width}x${viewport.height}`);
  const clipped = await page.locator('button:visible').evaluateAll((buttons) =>
    buttons.filter((button) => button.scrollWidth > button.clientWidth + 2)
      .map((button) => button.getAttribute('data-testid') ?? button.textContent));
  assert.deepEqual(clipped, [], 'Button content overflows');
}

async function inspectCanvas(page) {
  const canvas = page.locator('canvas').first();
  await expect(canvas).toBeVisible();
  const bounds = await canvas.boundingBox();
  assert.ok(bounds.width > 100 && bounds.height > 100, 'Canvas has no usable stage');
  const screenshot = await canvas.screenshot({
    style: '.asset-notice, .enemy-target { visibility: hidden !important; }',
  });
  const pixels = screenshotPixels(screenshot);
  assert.ok(pixels.uniqueColors > 1, 'Canvas pixel probe is blank');
  return { width: bounds.width, height: bounds.height, ...pixels };
}

function screenshotPixels(png) {
  const root = fileURLToPath(new URL('..', import.meta.url));
  const executable = process.env.M5_QA_PYTHON ?? path.join(root,
    process.platform === 'win32' ? '.venv/Scripts/python.exe' : '.venv/bin/python');
  const output = execFileSync(executable, [path.join(root, 'tools/inspect_canvas.py')], {
    input: png, encoding: 'utf8',
  });
  return JSON.parse(output);
}

async function responsiveCase(browser, baseUrl, viewport, archetype, definitions, out) {
  const context = await browser.newContext({ viewport });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  try {
    let run = await startRun(page, baseUrl, archetype);
    await enableReducedMotion(page);
    await assertLayout(page, viewport);
    await capture(page, out, `${viewport.width}x${viewport.height}-map`);
    run = await clickAdvance(page, baseUrl, `map-node-${chooseNode(run).id}`);
    const canvas = await inspectCanvas(page);
    await assertLayout(page, viewport);
    await capture(page, out, `${viewport.width}x${viewport.height}-combat`);
    const card = chooseCard(run, definitions);
    const afterCard = await castCard(page, baseUrl, run, card, definitions);
    const actionChangedCanvas = await verifyCombatCanvasAdvance(page, baseUrl, afterCard);
    await page.reload();
    const resumed = await readRun(page, baseUrl);
    await waitRevision(page, resumed.revision);
    assert.ok(resumed.revision > run.revision, 'Refresh lost action');
    const settingsPersisted = await verifyDrawers(page, resumed, out, viewport);
    assert.deepEqual(errors, [], 'Browser runtime errors');
    return {
      viewport, archetype, canvas, actionChangedCanvas,
      refreshRevision: resumed.revision, settingsPersisted,
    };
  } catch (error) {
    await capture(page, out, `failed-${viewport.width}x${viewport.height}`);
    throw error;
  } finally { await context.close(); }
}

async function enableReducedMotion(page) {
  await page.getByTestId('settings-open').click();
  const motion = page.getByRole('button', { name: '减少动态效果', exact: true });
  if (await motion.getAttribute('aria-pressed') !== 'true') await motion.click();
  await expect(motion).toHaveAttribute('aria-pressed', 'true');
  await page.getByTitle('关闭', { exact: true }).click();
}

async function verifyCombatCanvasAdvance(page, baseUrl, run) {
  assert.equal(run.phase, 'combat', 'First card unexpectedly ended combat');
  const card = page.getByTestId(`hand-card-${run.combat.hand[0].uid}`);
  await card.click();
  await card.click();
  await expect(page.getByTestId('selected-card-detail')).toBeHidden();
  const canvas = page.locator('canvas').first();
  const beforeBounds = await canvas.boundingBox();
  const before = await captureStaticCanvas(() => canvas.screenshot());
  assert.equal(run.combat.taunt_preview.available, true, 'Canvas probe has no normal taunt action');
  const advanced = await clickAdvance(page, baseUrl, 'taunt');
  assert.equal(advanced.phase, 'combat', 'Canvas action probe left combat');
  assert.equal(advanced.combat.taunt_used, true);
  assert.equal(advanced.combat.energy, run.combat.energy + run.combat.taunt_preview.energy_gain);
  assert.deepEqual(await canvas.boundingBox(), beforeBounds, 'Canvas geometry changed during update probe');
  return verifyStaticCanvasUpdate(before, () => canvas.screenshot());
}

async function networkRecovery(browser, baseUrl) {
  const context = await browser.newContext();
  const page = await context.newPage();
  try {
    let run = await startRun(page, baseUrl, 'sword');
    run = await clickAdvance(page, baseUrl, `map-node-${chooseNode(run).id}`);
    const requests = [];
    await page.route('**/api/v2/runs/*/actions', async (route) => {
      requests.push(route.request().postDataJSON());
      if (requests.length !== 1) return route.continue();
      await route.fetch();
      await route.abort('failed');
    });
    await page.getByTestId('taunt').click();
    await expect(page.getByTestId('retry-action')).toBeVisible();
    await expect(page.getByTestId('end-turn')).toBeDisabled();
    const applied = await readRun(page, baseUrl);
    await page.getByTestId('retry-action').click();
    await waitRevision(page, applied.revision);
    assert.deepEqual(requests[1], requests[0], 'Retry changed action id or payload');
    assert.deepEqual(await readRun(page, baseUrl), applied, 'Retry applied twice');
    await page.unroute('**/api/v2/runs/*/actions');
    await realConflict(page, baseUrl, applied);
    await realUnauthorized(page, baseUrl);
    return { lostResponseRetry: true, revisionConflict: true, unauthorizedRecovery: true };
  } finally { await context.close(); }
}

async function realConflict(page, baseUrl, run) {
  const session = await readSession(page);
  const response = await page.request.post(`${baseUrl}/api/v2/runs/${session.runId}/actions`, {
    headers: { Authorization: `Bearer ${session.accessToken}` },
    data: { kind: 'end_turn', action_id: crypto.randomUUID(), expected_revision: run.revision },
  });
  assert.equal(response.status(), 200);
  const authoritative = (await response.json()).run;
  await page.getByTestId('end-turn').click();
  await waitRevision(page, authoritative.revision);
  assert.deepEqual(await readRun(page, baseUrl), authoritative, 'Conflict secretly submitted twice');
}

async function realUnauthorized(page, baseUrl) {
  const previous = await readSession(page);
  const pattern = /\/api\/v2\/runs\/[^/]+$/;
  await page.route(pattern, (route) => route.continue({
    headers: { ...route.request().headers(), authorization: 'Bearer invalid-test-token' },
  }));
  await page.reload();
  await expect(page.getByTestId('reset-session')).toBeVisible();
  await page.unroute(pattern);
  await page.getByTestId('reset-session').click();
  await page.getByTestId('create-talisman').click();
  await expect(page.locator(ROOT)).toHaveAttribute('data-phase', 'map');
  const next = await readSession(page);
  assert.ok(next.accessToken !== previous.accessToken, 'Reset did not create a fresh profile');
  assert.equal((await readRun(page, baseUrl)).archetype, 'talisman');
}

async function deathCase(browser, baseUrl, definitions, out) {
  const context = await browser.newContext();
  const page = await context.newPage();
  try {
    let run = await startRun(page, baseUrl, 'talisman');
    run = await clickAdvance(page, baseUrl, `map-node-${chooseNode(run).id}`);
    for (let turn = 0; turn < 100 && run.phase === 'combat'; turn++) {
      run = await clickAdvance(page, baseUrl, 'end-turn');
    }
    assert.equal(run.phase, 'game_over');
    assert.equal(run.player.hp, 0);
    assert.ok(run.epitaph);
    await capture(page, out, 'desktop-game-over');
    const karma = await verifyLocalKarma(page, baseUrl, definitions, run.epitaph);
    return { terminal: run.phase, hp: run.player.hp, revision: run.revision, localKarma: karma };
  } finally { await context.close(); }
}

async function verifyLocalKarma(page, baseUrl, definitions, epitaph) {
  const previous = await readSession(page);
  await page.getByTestId('new-run').click();
  await page.getByTestId('create-sword').click();
  await expect(page.locator(ROOT)).toHaveAttribute('data-phase', 'map');
  assert.ok((await readSession(page)).accessToken === previous.accessToken, 'New run changed profile token');
  let run = await readRun(page, baseUrl);
  for (let step = 0; step < 120 && run.phase !== 'event'; step++) {
    if (run.phase === 'combat') run = await combatStep(page, baseUrl, run, definitions);
    else if (run.phase === 'reward') run = await clickAdvance(page, baseUrl, 'skip-reward');
    else run = await nodeStep(page, baseUrl, run);
  }
  assert.equal(run.phase, 'event');
  const karma = run.choices.find((choice) => choice.id === 'karma');
  assert.ok(karma?.description.includes(epitaph), 'Same-profile death did not become local causal content');
  const stones = run.player.stones;
  run = await clickAdvance(page, baseUrl, 'event-karma');
  assert.equal(run.player.stones, stones + 25);
  return true;
}

async function restHealCase(browser, baseUrl, definitions) {
  const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const page = await context.newPage();
  try {
    let run = await startRun(page, baseUrl, 'fire');
    run = await clickAdvance(page, baseUrl, `map-node-${chooseNode(run).id}`);
    run = await clickAdvance(page, baseUrl, 'end-turn');
    for (let step = 0; step < 250 && run.phase !== 'rest'; step++) {
      if (run.phase === 'map') {
        const available = run.map.nodes.filter((node) => node.available);
        const desired = run.layer === 3 ? 'rest' : run.layer === 1 ? 'event' : 'combat';
        const node = available.find((item) => item.kind === desired) ?? available[0];
        run = await clickAdvance(page, baseUrl, `map-node-${node.id}`);
      } else if (run.phase === 'combat') run = await combatStep(page, baseUrl, run, definitions);
      else if (run.phase === 'reward') run = await clickAdvance(page, baseUrl, 'reward-0');
      else if (run.phase === 'event') run = await clickAdvance(page, baseUrl, `event-${run.choices[0].id}`);
      else throw new Error(`Unexpected heal-route phase ${run.phase}`);
    }
    assert.equal(run.phase, 'rest');
    assert.ok(run.player.hp < run.player.max_hp, 'Heal route did not incur test damage');
    const before = run.player.hp;
    run = await clickAdvance(page, baseUrl, 'rest-heal');
    assert.equal(run.player.hp, Math.min(before + 18, run.player.max_hp));
    assert.equal(run.phase, 'map');
    return { before, after: run.player.hp, layer: run.layer };
  } finally { await context.close(); }
}

async function verifyDrawers(page, run, out, viewport) {
  await page.getByTestId('deck-open').click();
  const deck = page.getByRole('complementary', { name: '当前牌组' });
  await expect(deck.locator('.card-tile')).toHaveCount(run.deck.length);
  await assertLayout(page, viewport);
  await capture(page, out, `${viewport.width}x${viewport.height}-deck`);
  await page.getByTitle('关闭', { exact: true }).click();
  await page.getByTestId('settings-open').click();
  const muted = page.getByRole('button', { name: '静音', exact: true });
  if (await muted.getAttribute('aria-pressed') === 'true') await muted.click();
  const volume = page.getByRole('slider', { name: '音量' });
  await volume.focus();
  await volume.press('Home');
  await volume.press('ArrowRight');
  await expect(volume).toHaveValue('0.05');
  await muted.click();
  await expect(volume).toBeDisabled();
  const motion = page.getByRole('button', { name: '减少动态效果', exact: true });
  if (await motion.getAttribute('aria-pressed') !== 'true') await motion.click();
  await page.reload();
  await waitRevision(page, run.revision);
  await page.getByTestId('settings-open').click();
  await expect(page.getByRole('slider', { name: '音量' })).toHaveValue('0.05');
  await expect(page.getByRole('button', { name: '静音', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByRole('button', { name: '减少动态效果', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await assertLayout(page, viewport);
  await capture(page, out, `${viewport.width}x${viewport.height}-settings`);
  return true;
}

/** Execute real HTTP/UI paths and write screenshots/report; exits nonzero on any technical failure. */
async function main() {
  const { values } = parseArgs({ options: {
    url: { type: 'string', default: 'http://127.0.0.1:5173' },
    out: { type: 'string', default: '.data/playtest' },
  } });
  const baseUrl = values.url.replace(/\/$/, '');
  const out = path.resolve(values.out);
  await mkdir(out, { recursive: true });
  const browser = await chromium.launch({ channel: process.env.PLAYWRIGHT_CHANNEL ?? 'chrome', headless: true });
  const report = {
    date: new Date().toISOString(), source: sourceRevision(), baseUrl,
    art: 'pending verification', status: 'passed', results: {},
  };
  try {
    const catalog = await readJson(`${baseUrl}/api/v2/catalog`);
    const manifest = await readJson(`${baseUrl}/assets/manifest.json`);
    report.art = manifest.status;
    await recordCase(report, 'journey', () => journeyCase(browser, baseUrl, catalog.cards, out));
    await runResponsive(browser, baseUrl, catalog.cards, out, report);
    await recordCase(report, 'network', () => networkRecovery(browser, baseUrl));
    await recordCase(report, 'death', () => deathCase(browser, baseUrl, catalog.cards, out));
    await recordCase(report, 'heal', () => restHealCase(browser, baseUrl, catalog.cards));
  } catch (error) {
    report.status = 'failed';
    report.error = diagnostic(error);
  } finally {
    await browser.close();
    process.exitCode = report.status === 'passed' ? 0 : 1;
    await writeFile(path.join(out, 'report.json'), JSON.stringify(report, null, 2), 'utf8');
    console.log(JSON.stringify(report, null, 2));
  }
}

async function recordCase(report, key, task) {
  try { report.results[key] = { status: 'passed', ...await task() }; }
  catch (error) {
    report.status = 'failed';
    report.results[key] = { status: 'failed', error: diagnostic(error) };
  }
}

async function readJson(url) {
  const response = await fetch(url);
  assert.equal(response.status, 200, `Read HTTP ${response.status}: ${url}`);
  return response.json();
}

function diagnostic(error) {
  return String(error.stack ?? error).replace(/(authorization:\s*bearer\s+)\S+/gi, '$1[redacted]');
}

function sourceRevision() {
  const cwd = fileURLToPath(new URL('..', import.meta.url));
  const options = { cwd, encoding: 'utf8' };
  return {
    commit: execFileSync('git', ['rev-parse', 'HEAD'], options).trim(),
    dirty: Boolean(execFileSync('git', ['status', '--porcelain'], options).trim()),
  };
}

async function journeyCase(browser, baseUrl, definitions, out) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();
  try { return await runJourney(page, baseUrl, definitions, out); }
  catch (error) {
    await capture(page, out, 'failed-journey');
    throw error;
  } finally { await context.close(); }
}

async function runResponsive(browser, baseUrl, definitions, out, report) {
  const cases = [
    [{ width: 1440, height: 900 }, 'sword'],
    [{ width: 390, height: 844 }, 'fire'],
    [{ width: 430, height: 932 }, 'talisman'],
    [{ width: 360, height: 740 }, 'sword'],
  ];
  for (const [viewport, archetype] of cases) {
    await recordCase(report, `viewport-${viewport.width}x${viewport.height}`,
      () => responsiveCase(browser, baseUrl, viewport, archetype, definitions, out));
  }
}

await main();
