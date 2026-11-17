// The workout draft must never look safe when the phone isn't keeping it, and a ticked set
// must never disappear from one stray tap.
const inlineScriptMatches = require('./helpers/html-scripts.cjs');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const html = fs.readFileSync(require('node:path').join(__dirname, '..', 'log.html'), 'utf8');
for (const match of inlineScriptMatches(html)) new vm.Script(match[1]);

// --- Storage refused (full phone, private window): warn once, clear when it works again.
const start = html.indexOf('  // The draft lives only in this phone\'s storage.');
const end = html.indexOf('  function saveMotivationDraft() {');
assert.ok(start > 0 && end > start, 'draft storage block is present');
let refuse = true, stored = null, said = [], listeners = {};
const msg = { textContent: '' };
const context = vm.createContext({
  KEY: 'training.logDraft', draft: { exercises: [] },
  localStorage: { setItem(key, value) { if (refuse) throw new Error('QuotaExceededError'); stored = [key, value]; } },
  $: id => ({ msg })[id],
  say: text => { said.push(text); msg.textContent = text; },
  shownMessage: () => msg.textContent,
  window: { addEventListener: (name, fn) => { listeners[name] = fn; } },
});
vm.runInContext(html.slice(start, end), context);

assert.equal(context.storeDraft(), false, 'a refused save reports failure');
assert.equal(said.length, 1, 'the person is told the phone is not keeping the workout');
assert.match(said[0], /isn't keeping the workout/);
context.storeDraft(); context.storeDraft();
assert.equal(said.length, 1, 'the warning is shown once, not on every tap');
refuse = false;
assert.equal(context.storeDraft(), true, 'saving works again');
assert.equal(stored[0], 'training.logDraft');
assert.deepEqual(said.slice(1), [''], 'the warning clears once the draft is kept again');
msg.textContent = 'Something else'; refuse = true; context.storeDraft(); refuse = false; said.length = 0;
msg.textContent = 'An unrelated message';
context.storeDraft();
assert.deepEqual(said, [], 'recovery never clears somebody else\'s message');

// --- The same draft changed in another tab or the home-screen app.
said.length = 0;
const fakeStorage = context.localStorage;
listeners.storage({ key: 'training.logDraft', storageArea: fakeStorage });
assert.equal(said.length, 1);
assert.match(said[0], /another tab or window/);
listeners.storage({ key: 'training.unit', storageArea: fakeStorage });
assert.equal(said.length, 1, 'other settings changing elsewhere are ignored');

// --- saveDraft goes through the warning path (no silently ignored storage error left).
const saveDraft = html.slice(html.indexOf('  function saveDraft() {'), html.indexOf('  // The draft lives only'));
assert.ok(saveDraft.includes('storeDraft();'), 'saveDraft stores through storeDraft');
assert.ok(!/localStorage\.setItem\(KEY[^;]*\);\s*\}\s*catch\s*\(e\)\s*\{\s*\}/.test(saveDraft), 'no swallowed storage error in saveDraft');

// --- Remove last set asks first, and says when the set is already ticked.
const removeAt = html.indexOf('if (v === "last") {');
assert.ok(removeAt > 0, 'remove-last-set branch is present');
const removeBlock = html.slice(removeAt, html.indexOf('if (!confirm("Remove " + ex.title', removeAt));
assert.match(removeBlock, /if \(!confirm\(question\)\) return;/, 'nothing is removed unless confirmed');
assert.ok(removeBlock.indexOf('confirm(question)') < removeBlock.indexOf('ex.sets.pop()'), 'it asks before removing');
assert.match(removeBlock, /last\.done \? " It's already ticked as done\." : ""/);

console.log('log draft safety ok');
