const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const html = fs.readFileSync(path.join(__dirname, '..', 'log.html'), 'utf8');
const source = html.slice(html.indexOf('  // Swapping gives the new movement'), html.indexOf('  function squareCard('));
assert.ok(source.includes('function swapExercise('), 'swapExercise is present');

function harness(draft) {
  const picker = {hidden: false}, said = [], loaded = [];
  let n = 0, saved = 0, redraws = 0;
  const context = vm.createContext({
    draft, $: id => (id === 'picker' ? picker : null), uid: () => 'new-' + (++n),
    refFromServer: id => ({basis: 'e1rm', from: id}), cardEls: new Map(),
    saveDraft: () => saved++, renderWorkout: () => redraws++, loadState: ex => loaded.push(ex.template_id),
    say: text => said.push(text),
  });
  vm.runInContext(source, context);
  return {swap: (ex, e) => context.swapExercise(ex, e), picker, said, loaded, counts: () => ({saved, redraws})};
}
const set = (extra = {}) => ({type: 'normal', kg: '120', reps: '4', rpe: '7', done: false, manual: true, review_id: 'r', ...extra});

// Nothing ticked: the new movement takes the original's place, with a new identity and blank weights.
{
  const original = {id: 'sq-1', template_id: 'sq', title: 'Squat', planCallouts: '1x1@8 TS',
    sets: [set({ts: true, reps: '1', rpe: '8'}), set(), set({type: 'warmup'})]};
  const other = {id: 'bp-1', template_id: 'bp', title: 'Bench', sets: [set()]};
  const draft = {exercises: [original, other]};
  const h = harness(draft);
  h.swap(original, {id: 'fsq', title: 'Front Squat'});
  assert.equal(h.picker.hidden, true);
  assert.deepEqual(draft.exercises.map(e => e.title), ['Front Squat', 'Bench']);
  const swapped = draft.exercises[0];
  assert.notEqual(swapped.id, 'sq-1', 'The swapped movement never reuses the prescribed identity');
  assert.equal(swapped.template_id, 'fsq');
  assert.equal(swapped.swappedFrom, 'Squat');
  assert.equal(swapped.planCallouts, '1x1@8 TS');
  assert.equal(JSON.stringify(swapped.ref), JSON.stringify({basis: 'e1rm', from: 'fsq'}));
  assert.equal(swapped.sets.length, 2, 'Unticked warm-ups of the old lift are dropped');
  for (const s of swapped.sets) {
    assert.equal(s.kg, ''); assert.equal(s.manual, false); assert.equal(s.done, false);
    assert.equal(s.review_id, undefined, 'Moved sets lose the original review identity');
  }
  assert.deepEqual(swapped.sets.map(s => [s.reps, s.rpe, Boolean(s.ts)]), [['1', '8', true], ['4', '7', false]]);
  assert.deepEqual(h.loaded, ['fsq']);
  assert.deepEqual(h.counts(), {saved: 1, redraws: 1});
}

// Ticked sets stay with the original; the rest move to a new card right after it.
{
  const done = set({done: true, review: {set_id: 'r', exercise_id: 'sq-1'}});
  const original = {id: 'sq-1', template_id: 'sq', title: 'Squat', sets: [done, set(), set()]};
  const draft = {exercises: [original, {id: 'bp-1', template_id: 'bp', title: 'Bench', sets: [set()]}]};
  harness(draft).swap(original, {id: 'fsq', title: 'Front Squat'});
  assert.deepEqual(draft.exercises.map(e => e.title), ['Squat', 'Front Squat', 'Bench']);
  assert.deepEqual(original.sets, [done], 'The completed set and its evidence are untouched');
  assert.equal(draft.exercises[1].sets.length, 2);
}

// Every set ticked: the new movement still gets one blank set to fill in.
{
  const original = {id: 'sq-1', template_id: 'sq', title: 'Squat', sets: [set({done: true})]};
  const draft = {exercises: [original]};
  harness(draft).swap(original, {id: 'fsq', title: 'Front Squat'});
  assert.equal(draft.exercises.length, 2);
  assert.equal(JSON.stringify(draft.exercises[1].sets), JSON.stringify([{type: 'normal', kg: '', reps: '', rpe: '', done: false, manual: false}]));
}

// Picking the same movement, or swapping during save recovery, changes nothing.
{
  const original = {id: 'sq-1', template_id: 'sq', title: 'Squat', sets: [set()]};
  const draft = {exercises: [original]};
  const h = harness(draft);
  h.swap(original, {id: 'sq', title: 'Squat'});
  assert.equal(draft.exercises[0], original);
  draft.frozenSave = {};
  h.swap(original, {id: 'fsq', title: 'Front Squat'});
  assert.equal(draft.exercises[0], original);
  assert.equal(h.said.length, 1);
  assert.deepEqual(h.counts(), {saved: 0, redraws: 0});
}

console.log('Swap exercise checks passed.');
