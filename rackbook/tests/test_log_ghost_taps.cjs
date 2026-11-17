// After a bottom sheet closes, only taps where the sheet was are ignored for a moment (a double-tap
// would land there, e.g. on Finish workout). A panel's ✕ or a tick elsewhere must work at once, and a
// newly opened sheet's own buttons must never be ignored.
const inlineScriptMatches = require('./helpers/html-scripts.cjs');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const html = fs.readFileSync(require('node:path').join(__dirname, '..', 'log.html'), 'utf8');
for (const match of inlineScriptMatches(html)) new vm.Script(match[1]);

const start = html.indexOf('  let ghostUntil = 0');
const end = html.indexOf('  function openSheet(');
assert.ok(start > 0 && end > start, 'ghost-tap block is present');
let now = 1000, capture = null;
const context = vm.createContext({
  Date: { now: () => now },
  document: { addEventListener: (name, fn, useCapture) => { if (name === 'click' && useCapture) capture = fn; } },
});
vm.runInContext(html.slice(start, end), context);
assert.equal(typeof capture, 'function', 'a capturing click guard is installed');

function tap(x, y, trusted = true) {
  const e = { isTrusted: trusted, clientX: x, clientY: y, blocked: false,
    preventDefault() { this.blocked = true; }, stopPropagation() {} };
  capture(e); return e.blocked;
}
const sheetArea = { left: 0, right: 390, top: 500, bottom: 844 };

assert.equal(tap(200, 700), false, 'nothing is ignored before any sheet closes');
context.swallowGhostTaps(sheetArea);
assert.equal(tap(200, 700), true, 'a quick tap where the sheet was is ignored');
assert.equal(tap(370, 120), false, 'a panel ✕ above the sheet works at once');
assert.equal(tap(200, 499), false, 'just above the sheet works');
assert.equal(tap(200, 700, false), false, 'scripted clicks are never ignored');
now += 449; assert.equal(tap(200, 700), true, 'still ignored just inside the moment');
now += 1; assert.equal(tap(200, 700), false, 'works again after 0.45 s');

context.swallowGhostTaps(sheetArea);
context.swallowGhostTaps(null);
assert.equal(tap(200, 700), false, 'opening a new sheet clears the guard so its buttons work');

const openSheet = html.slice(end, html.indexOf('const scrim = el("div", "scrim");', end) + 40);
assert.match(openSheet, /swallowGhostTaps\(null\);/, 'openSheet clears the guard when a sheet opens');
assert.match(html, /const close = \(\) => \{ const area = sheet\.getBoundingClientRect\(\);[^}]*swallowGhostTaps\(area\);/,
  'closing a sheet guards only the area it covered');

console.log('log ghost taps ok');
