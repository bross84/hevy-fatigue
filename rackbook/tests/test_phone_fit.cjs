// Phone fit (issues #120, #121, #122):
// - every page turns on iPhone safe areas, so bottom buttons clear the home-swipe strip;
// - boxes that made the iPhone zoom in use 16px text;
// - Log page messages show above the bottom bar during a workout, fade unless sticky, and have a ✕.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.join(__dirname, '..', '..');
const read = (p) => fs.readFileSync(path.join(root, p), 'utf8');

// #120
for (const page of ['rackbook/index.html', 'rackbook/log.html', 'rackbook/mesocycles.html', 'rackbook/progress.html',
  'rackbook/recent.html', 'rackbook/rpe_charts.html', 'rackbook/stress.html', 'rackbook/trial.html',
  'static/index.html', 'static/diagnostic.html', 'static/docs.html']) {
  const tag = read(page).match(/<meta name="viewport" content="([^"]+)"/);
  assert.ok(tag, page + ' has a viewport tag');
  assert.match(tag[1], /viewport-fit=cover/, page + ' turns on safe areas');
}

// #121
const meso = read('rackbook/mesocycles.html');
assert.match(meso, /label input,label textarea \{[^}]*font-size:16px/, 'Plans form boxes are 16px');
assert.match(meso, /#weekText \{font:16px\//, 'Write week as text box is 16px');
for (const page of ['rackbook/stress.html', 'rackbook/trial.html']) {
  const html = read(page);
  assert.match(html, /\.controls select \{[^}]*font-size: 16px/, page + ' dropdowns are 16px');
  assert.match(html, /\.stress-chart input \{[^}]*font:inherit;font-size:16px/, page + ' date boxes are 16px');
}
const progress = read('rackbook/progress.html');
assert.match(progress, /\.custom-range input \{ font-size:16px; \}/, 'Progress date boxes are 16px');
assert.match(progress, /#sessionSelect \{[^}]*font-size:16px/, 'Progress session dropdown is 16px');
assert.match(read('rackbook/index.html'), /\.field select \{[^}]*font-size: 16px;/, 'legacy settings boxes are 16px');
assert.match(read('static/index.html'), /\.ai-equipment-notes \{[^}]*font-size: 16px;/, 'equipment notes box is 16px');

// #122
const log = read('rackbook/log.html');
assert.match(log, /<div id="bar" class="bar" hidden>\s*<div id="barMsg" class="bar-msg" role="status" aria-live="polite" hidden><\/div>/,
  'a message spot sits at the top of the bottom bar and is announced');
const start = log.indexOf('  // Messages. During a workout');
const end = log.indexOf('  function show(name)');
assert.ok(start > 0 && end > start, 'message helper is present');
function element(tag, cls, text) {
  return { tag, className: cls, text, hidden: false, children: [], attrs: {},
    classList: { items: new Set(), add(c) { this.items.add(c); }, has(c) { return this.items.has(c); } },
    append(...xs) { this.children.push(...xs); }, replaceChildren(...xs) { this.children = xs; },
    setAttribute(k, v) { this.attrs[k] = v; }, addEventListener(n, fn) { this['on' + n] = fn; } };
}
const top = element('div'), dock = element('div'), bar = element('div');
dock.hidden = true;
let timers = [];
const ctx = vm.createContext({ el: element, $: (id) => ({ msg: top, barMsg: dock, bar })[id],
  setTimeout: (fn, ms) => { timers.push({ fn, ms }); return timers.length; }, clearTimeout() {} });
vm.runInContext(log.slice(start, end), ctx);
const runTimers = () => { const t = timers; timers = []; t.forEach((x) => x.fn()); };

bar.hidden = true;
ctx.say('No recent workouts yet.');
assert.equal(top.children.length, 1, 'before a workout, messages stay at the top');
assert.equal(dock.hidden, true);
assert.equal(timers.length, 0, 'and do not fade');

bar.hidden = false;
ctx.say('Warm-ups are done for Squat.');
assert.equal(top.children.length, 0, 'during a workout nothing shows at the top');
assert.equal(dock.hidden, false, 'it shows above the bottom bar');
const box = dock.children[0];
assert.equal(box.children[0].text, 'Warm-ups are done for Squat.');
const close = box.children[1];
assert.equal(close.attrs['aria-label'], 'Dismiss message');
assert.equal(timers[0].ms, 6000, 'an everyday message fades after 6 seconds');
runTimers();
assert.ok(box.classList.has('leaving'), 'it fades out');
runTimers();
assert.equal(dock.hidden, true, 'then it is gone');
assert.equal(ctx.shownMessage(), '');

ctx.say("This phone isn't keeping the workout.", { sticky: true });
assert.equal(timers.length, 0, 'a sticky warning never fades by itself');
dock.children[0].children[1].onclick();
assert.equal(dock.hidden, true, '✕ dismisses it');

ctx.say('First'); const firstTimers = timers; timers = [];
ctx.say('Second');
firstTimers.forEach((t) => t.fn()); firstTimers.length = 0;
timers = [];
assert.equal(ctx.shownMessage(), 'Second', 'an older message fading never removes a newer one');
const fadeLater = [];
ctx.say('Old'); fadeLater.push(...timers); timers = [];
ctx.say('New');
fadeLater[0].fn(); timers.forEach((t) => t.fn());
assert.equal(ctx.shownMessage(), 'New');

for (const sticky of ['say(DRAFT_NOT_KEPT, { sticky: true })', 'say(OTHER_TAB, { sticky: true })',
  "Save recovery is required.', { sticky: true })", 'Check save status before continuing.", { sticky: true })',
  'catch (err) { say(err.message, { sticky: true }); return; }']) {
  assert.ok(log.includes(sticky), 'kept until dismissed: ' + sticky);
}
assert.ok(!/buildEntry\(\); \} catch \(err\) \{[^}]*scrollTo/.test(log), 'a Finish error no longer jumps the page to the top');
assert.match(read('rackbook/static/logger-layout.css'), /main\[data-save-recovery\] #msg,\s*main\[data-save-recovery\] ~ #bar #barMsg,/,
  'on a phone, the save-recovery card replaces messages in both places, as before');

// #106: on a phone the plan cards fill the screen, so opening the editor takes you to it.
const plans = read('rackbook/mesocycles.html');
assert.match(plans, /function showEditor\(\)\{\$\('editor'\)\.scrollIntoView\(\{block:'start',behavior:'instant'\}\);\}/);
assert.match(plans, /function openPlan\(p\) \{[^\n]*renderEditor\(\);message\(''\);showEditor\(\);\}/, 'Edit plan scrolls to the editor');
assert.match(plans, /function newPlan\(\)\{[^\n]*renderEditor\(\);showEditor\(\);\}/, 'New microcycle scrolls to the editor');
assert.match(plans, /function duplicateMicrocycle\(p\)\{[^\n]*renderEditor\(\);showEditor\(\);\}/, 'Duplicate microcycle scrolls to the editor');
assert.match(plans, /renderEditor\(\);wtDone\(\);showEditor\(\);/, 'Write week as text scrolls to the editor');
assert.equal((plans.match(/showEditor\(\);/g) || []).length, 4, 'redraws while editing never jump the page');
console.log('Phone fit (#120 safe areas, #121 16px boxes, #122 messages above the bar, #106 Edit plan) passed');
