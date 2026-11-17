// Log page day preview (#107): picking a planned day shows its movements and sets, read-only, before loading it.
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
  return { tag, className: cls, text, children: [], attrs: {},
    append(...xs) { this.children.push(...xs); }, setAttribute(k, v) { this.attrs[k] = v; } };
}
const ctx = vm.createContext({ el, WeekText });
vm.runInContext(log.slice(start, end), ctx);

const list = ctx.dayPreview({ name: 'Day 2 Lower', exercises: [
  { title: 'Squat (Barbell)', notes: '', tm_pct: null, sets: [
    { reps: 3, rpe: 8, ts: true }, { reps: 5, rpe: 7, backoff: true }, { reps: 5, rpe: 7, backoff: true }] },
  { title: 'Romanian Deadlift (Barbell)', notes: 'Pause at the knee', sets: [
    { reps: 8, rpe: 7 }, { reps: 8, rpe: 7 }, { reps: 8, rpe: 7 }] },
  { title: 'Leg Curl', notes: '', sets: [] }] });
assert.equal(list.tag, 'ul');
assert.equal(list.attrs['aria-label'], 'Day 2 Lower preview');
assert.equal(list.children.length, 3, 'one row per movement');
const [squat, rdl, curl] = list.children;
assert.equal(squat.children[0].text, 'Squat (Barbell)');
assert.equal(squat.children[1].text, '1x3@8 TS, 2x5@7 BO', 'sets use the week-text shorthand');
assert.equal(squat.children.length, 2, 'no note line without a note');
assert.equal(rdl.children[1].text, '3x8@7');
assert.equal(rdl.children[2].text, 'Pause at the knee', 'movement notes show');
assert.equal(curl.children[1].text, 'No sets yet');
assert.ok(!/button|addEventListener|input/.test(log.slice(start, end)), 'the preview has nothing to tap or edit');

assert.ok(log.includes('if (selected.exercises.length) workoutDetails.append(dayPreview(selected));'),
  'the preview shows under the Workout day picker, above Load selected workout');
console.log('Log day preview (#107) passed');
