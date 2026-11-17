// Log page day preview (#107): a Preview day button under the Workout day picker opens a read-only list of the
// picked day's movements and sets; picking another day redraws the card, so the list starts closed again.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const WeekText = require('../static/week-text.js');
const log = fs.readFileSync(path.join(__dirname, '..', 'log.html'), 'utf8');

const start = log.indexOf('  function dayPreview(session)');
const end = log.indexOf('  async function loadPlannedStart()');
assert.ok(start > 0 && end > start, 'day preview helper is present');
function el(tag, cls, text) {
  return { tag, className: cls, textContent: text, hidden: false, children: [], attrs: {}, events: {},
    append(...xs) { this.children.push(...xs); }, setAttribute(k, v) { this.attrs[k] = v; },
    addEventListener(n, fn) { this.events[n] = fn; } };
}
const ctx = vm.createContext({ el, WeekText });
vm.runInContext(log.slice(start, end), ctx);

const [toggle, list] = ctx.dayPreview({ name: 'Day 2 Lower', exercises: [
  { title: 'Squat (Barbell)', notes: '', tm_pct: null, sets: [
    { reps: 3, rpe: 8, ts: true }, { reps: 5, rpe: 7, backoff: true }, { reps: 5, rpe: 7, backoff: true }] },
  { title: 'Romanian Deadlift (Barbell)', notes: 'Pause at the knee', sets: [
    { reps: 8, rpe: 7 }, { reps: 8, rpe: 7 }, { reps: 8, rpe: 7 }] },
  { title: 'Leg Curl', notes: '', sets: [] }] });

assert.equal(toggle.tag, 'button');
assert.equal(toggle.textContent, 'Preview day');
assert.equal(toggle.attrs['aria-expanded'], 'false');
assert.equal(toggle.attrs['aria-controls'], list.id);
assert.equal(list.hidden, true, 'the list starts closed');
toggle.events.click();
assert.equal(list.hidden, false, 'Preview day opens it');
assert.equal(toggle.textContent, 'Hide preview');
assert.equal(toggle.attrs['aria-expanded'], 'true');
toggle.events.click();
assert.equal(list.hidden, true, 'Hide preview closes it');
assert.equal(toggle.textContent, 'Preview day');

assert.equal(list.tag, 'ul');
assert.equal(list.attrs['aria-label'], 'Day 2 Lower preview');
assert.equal(list.children.length, 3, 'one row per movement');
const [squat, rdl, curl] = list.children;
assert.equal(squat.children[0].textContent, 'Squat (Barbell)');
assert.equal(squat.children[1].textContent, '1x3@8 TS, 2x5@7 BO', 'sets use the week-text shorthand');
assert.equal(squat.children.length, 2, 'no note line without a note');
assert.equal(rdl.children[1].textContent, '3x8@7');
assert.equal(rdl.children[2].textContent, 'Pause at the knee', 'movement notes show');
assert.equal(curl.children[1].textContent, 'No sets yet');
assert.ok(list.children.every((li) => li.children.every((c) => c.tag === 'div')), 'the list itself has nothing to tap or edit');

assert.ok(log.includes('if (selected.exercises.length) workoutDetails.append(...dayPreview(selected));'),
  'the button shows under the Workout day picker, above Load selected workout');
assert.ok(log.includes('#plannedStart .day-preview + button {margin-top:8px}'), 'Load keeps its gap below the list');
console.log('Log day preview button (#107) passed');
