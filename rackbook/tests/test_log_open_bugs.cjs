// Log page bug fixes from issues #105, #123 and #124:
// - a picker search with no matches re-downloads Hevy's exercise list once per opening, then searches again,
//   and offers a Refresh from Hevy button;
// - an exercise sheet (Targets, Note) sits on top of the phone keyboard instead of behind it;
// - the missing-key message points at dashboard Settings, where the key now lives.
const inlineScriptMatches = require('./helpers/html-scripts.cjs');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const html = fs.readFileSync(require('node:path').join(__dirname, '..', 'log.html'), 'utf8');
for (const match of inlineScriptMatches(html)) new vm.Script(match[1]);

// #124: the key message names the right place.
assert.ok(!html.includes('Save your Hevy key on the Recent page'), 'no message sends you to the Recent page for the key');
assert.ok(html.includes('Save your Hevy key in dashboard Settings first.'));

// #123: a focused box inside a pinned sheet lifts the sheet above the keyboard and scrolls inside it.
const start = html.indexOf('  function fitSheetAboveKeyboard(');
const end = html.indexOf('  document.addEventListener("focusin"');
assert.ok(start > 0 && end > start, 'sheet keyboard helpers are present');
const listeners = {}, pageScrolls = [];
const vv = { offsetTop: 0, height: 480, addEventListener: (name, fn) => { listeners[name] = fn; } };
const doc = { activeElement: null };
const ctx = vm.createContext({ document: doc, padInput: null, numberpad: { offsetHeight: 0 },
  window: { innerHeight: 844, visualViewport: vv, scrollBy: (o) => pageScrolls.push(o) },
  getComputedStyle: (node) => ({ position: node.fixed ? 'fixed' : 'static' }) });
vm.runInContext('let liftedSheet = null;\n' + html.slice(start, end), ctx);

const sheet = { fixed: true, style: { bottom: '', maxHeight: '' } };
const scrolledInside = [];
const box = { closest: (sel) => (sel === '.ex-panel' ? sheet : null), scrollIntoView: (o) => scrolledInside.push(o),
  getBoundingClientRect: () => ({ top: 700, bottom: 744 }) };
doc.activeElement = box;
ctx.liftIntoView(box);
assert.equal(sheet.style.bottom, '364px', 'the sheet sits on top of a 364px keyboard');
assert.equal(sheet.style.maxHeight, '456px', 'and fits in what is left of the screen');
assert.equal(scrolledInside.length, 1, 'the box is scrolled into view inside the sheet');
assert.equal(scrolledInside[0].behavior, 'instant', 'without an animation running into the next tap');
assert.equal(pageScrolls.length, 0, 'the page itself is not scrolled for a pinned sheet');

vv.height = 400; listeners.resize();
assert.equal(sheet.style.bottom, '444px', 'follows the keyboard when it changes height');
ctx.dropLiftedSheet();
assert.equal(sheet.style.bottom, '', 'the sheet goes back to the bottom when typing ends');
assert.equal(sheet.style.maxHeight, '');
vv.height = 300; listeners.resize();
assert.equal(sheet.style.bottom, '', 'a dropped sheet no longer follows the keyboard');

// A box that is not in a pinned sheet still uses the page scroll, as before.
const plain = { closest: () => null, getBoundingClientRect: () => ({ top: 600, bottom: 650 }) };
vv.height = 480; doc.activeElement = plain;
ctx.liftIntoView(plain);
assert.equal(pageScrolls.length, 1, 'set rows keep the existing page scroll');
assert.match(html, /function closePanel\(\) \{[^}]*dropLiftedSheet\(\);/, 'closing a sheet drops the lift');
assert.match(html, /typingTimer = setTimeout\(\(\) => \{[^}]*dropLiftedSheet\(\);/, 'leaving the box drops the lift');
assert.match(html, /matches\("#exercises input, #exercises \.ex-panel textarea"\)/, 'the Note box is lifted too');

// #105: the picker re-downloads once per opening when a search finds nothing.
const pStart = html.indexOf('  function squareCard(');
const pEnd = html.indexOf('  let swapTarget = null;');
assert.ok(pStart > 0 && pEnd > pStart, 'picker block is present');
function element(tag, cls, text) {
  return { tag, className: cls, text, children: [], append(...xs) { this.children.push(...xs); },
    replaceChildren(...xs) { this.children = xs; }, addEventListener(name, fn) { this['on' + name] = fn; } };
}
const results = element('div'), search = { value: '' }, syncnote = { hidden: true }, picker = { hidden: false };
const calls = [];
let hevyList = [{ id: 'a', title: 'Back Squat', cached_at: '2026-11-16 12:00:00' }];
const pctx = vm.createContext({
  el: element, $: (id) => ({ results, search, syncnote, picker })[id], say() {}, recentExercises: () => [],
  swapTarget: null, addExercise() {}, swapExercise() {}, Date,
  api: async (path, opts) => { calls.push((opts && opts.method) || 'GET'); if (path === '/exercises') return hevyList; return {}; },
});
vm.runInContext('let catalog = null, refreshTried = false, missRefreshed = false, catalogSyncing = false;\n'
  + html.slice(pStart, pEnd) + '\nthis.setCatalog = (c) => { catalog = c; }; this.getCatalog = () => catalog;'
  + '\nthis.resetMiss = () => { missRefreshed = false; };', pctx);
const texts = () => results.children.map((c) => c.text).filter(Boolean);
const refreshButton = () => results.children.find((c) => c.tag === 'button');
const settle = () => new Promise((r) => setImmediate(r));

(async () => {
  pctx.setCatalog(hevyList.slice());
  search.value = 'zercher';
  hevyList = [...hevyList, { id: 'z', title: 'Zercher Squat', cached_at: '2026-11-16 21:00:00' }];   // just made in Hevy
  pctx.renderResults();
  assert.deepEqual(texts(), ['No matches.', 'Checking Hevy…'], 'shows No matches while it checks');
  assert.equal(refreshButton().disabled, true, 'the Refresh button waits while a check runs');
  assert.equal(syncnote.hidden, false, 'the existing "Updating your exercise list" note shows');
  await settle(); await settle();
  assert.deepEqual(calls, ['POST', 'GET'], 'downloads the list from Hevy once');
  assert.equal(syncnote.hidden, true);
  assert.ok(texts().includes('Results (1)'), 'the new exercise is found without reopening anything');

  search.value = 'nothing like this';
  pctx.renderResults(); await settle(); await settle();
  assert.equal(calls.length, 2, 'only once per opening of the picker');
  assert.deepEqual(texts(), ['No matches.', 'Refresh from Hevy'], 'a Refresh from Hevy button under No matches');
  assert.equal(refreshButton().disabled, false);
  refreshButton().onclick(); await settle(); await settle();
  assert.equal(calls.length, 4, 'tapping Refresh from Hevy downloads the list again, any number of times');
  refreshButton().onclick(); await settle(); await settle();
  assert.equal(calls.length, 6);
  pctx.resetMiss();
  pctx.renderResults(); await settle(); await settle();
  assert.equal(calls.length, 8, 'opening the picker again allows one more automatic check');
  assert.match(html, /\$\("search"\)\.value = ""; missRefreshed = false;/, 'opening the picker resets the one check');

  console.log('Log open-bug fixes (#105 picker, #123 sheet keyboard, #124 key message) passed');
})().catch((err) => { console.error(err); process.exit(1); });
