// Log page redesign (#110): moving between exercises, supersets, no-bar plates, the Target column and plate-free movements.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const html = fs.readFileSync(path.join(__dirname, '..', 'log.html'), 'utf8');
const layout = fs.readFileSync(path.join(__dirname, '..', 'static', 'logger-layout.js'), 'utf8');

// ── Where the next tick takes you ─────────────────────────────────────────────
const sets = (done, total) => Array.from({length: total}, (_, i) => ({type: 'normal', done: i < done}));
let draft;
// A stand-in page: init only wires listeners and fills panels, none of which these checks read.
const stub = () => ({addEventListener() {}, setAttribute() {}, getAttribute() {}, classList: {toggle() {}, remove() {}, add() {}},
  append() {}, prepend() {}, after() {}, focus() {}, contains: () => false, getBoundingClientRect: () => ({top: 0}),
  querySelector: () => null, querySelectorAll: () => [], replaceChildren() {}, hidden: false, open: false, style: {}, value: ''});
const layoutContext = vm.createContext({matchMedia: () => ({matches: false, addEventListener() {}}),
  document: {getElementById: stub, querySelector: () => stub(), addEventListener() {}, createElement: stub, activeElement: null}});
vm.runInContext(layout + ';this.LoggerLayout = LoggerLayout;', layoutContext);
layoutContext.LoggerLayout.init({getDraft: () => draft, getCard: () => null, save() {}, render() {}, unitFor: () => 'kg', format: String});
const afterSet = ex => layoutContext.LoggerLayout.afterSet(ex);

const a = {id: 'a', title: 'Squat', sets: sets(2, 3)}, b = {id: 'b', title: 'Press', sets: sets(0, 3)}, c = {id: 'c', title: 'Curl', sets: sets(3, 3)};
draft = {exercises: [a, b, c]};
assert.equal(afterSet(a), null, 'Sets left on this exercise: stay on it');
a.sets[2].done = true;
assert.deepEqual({...afterSet(a)}, {next: 'b', skipRest: false}, 'Last set done: go to the next exercise with sets left');
b.sets.forEach(s => { s.done = true; });
const d = {id: 'd', title: 'Row', sets: sets(1, 3)};
draft = {exercises: [d, a, b, c]};
assert.deepEqual({...afterSet(b)}, {next: 'd', skipRest: false}, 'Wraps round to an earlier exercise that was skipped');
d.sets.forEach(s => { s.done = true; });
assert.equal(afterSet(b), null, 'Everything done: nowhere to go');

// Superset: each set hands over to the partner; rest only once both have done the round.
const x = {id: 'x', title: 'Leg Curl', ss: 'y', sets: sets(1, 3)}, y = {id: 'y', title: 'EZ Curl', ss: 'x', sets: sets(0, 3)};
draft = {exercises: [x, y]};
assert.deepEqual({...afterSet(x)}, {next: 'y', skipRest: true}, 'First of the pair done: straight to the partner, no rest');
y.sets[0].done = true;
assert.deepEqual({...afterSet(y)}, {next: 'x', skipRest: false}, 'Round finished: rest, then back to the first');
y.sets.forEach(s => { s.done = true; });
x.sets.forEach(s => { s.done = true; });
assert.equal(afterSet(x), null);
const z = {id: 'z', title: 'Row', sets: sets(0, 2)};
y.sets[2].done = false;
draft = {exercises: [x, y, z]};
x.sets.forEach(s => { s.done = true; });
assert.deepEqual({...afterSet(x)}, {next: 'y', skipRest: true}, 'Last round: the partner\'s matching set comes straight after, no rest');
y.sets[2].done = true;
assert.deepEqual({...afterSet(y)}, {next: 'z', skipRest: false}, 'Pair finished: on to the next exercise');
console.log('Exercise advance and superset hand-off checks passed.');

// ── Plates: no bar loads the whole weight in one stack ───────────────────────
const ctx = vm.createContext({LB_PER_KG: 2.20462262185, lbOfKg: kg => kg * 2.20462262185, unitFor: () => 'kg', unit: 'kg', el() {}});
vm.runInContext(html.slice(html.indexOf('  const PLATES_KG ='), html.indexOf('  function setName(')), ctx);
const plan = (kg, barKg, chainKg = 0) => vm.runInContext('platePlan', ctx)(kg, {ref: {barKg, chainKg}});
assert.deepEqual(JSON.parse(JSON.stringify(plan(57.5, 20).counts)), [[15, 1], [2.5, 1], [1.25, 1]], 'A barbell splits per side');
const noBar = plan(30, 0);
assert.equal(noBar.noBar, true);
assert.deepEqual(JSON.parse(JSON.stringify(noBar.counts)), [[25, 1], [5, 1]], 'No bar: plates for the whole 30 kg');
assert.equal(plan(1, 0).short, 1, 'What cannot be loaded is reported, not split per side');
assert.equal(plan(20, 20).counts.length, 0, 'An empty bar still works');
console.log('No-bar plate plan checks passed.');

// ── Target column and plate-free movements ────────────────────────────────────
const t = vm.createContext({primaryText: s => (s.kg === '' ? '' : String(Number(s.kg))), trim: String, el() {}, closePanel() {}});
vm.runInContext(html.slice(html.indexOf('  // Dumbbell, cable and machine movements'), html.indexOf('  // The other exercise of a superset pair')), t);
const target = (s) => vm.runInContext('targetText', t)({}, s);
assert.equal(target({kg: '57.5', reps: '3', tReps: '3', rpe: '8'}), '57.5 × 3 @8');
assert.equal(target({kg: '60', autoSuggestion: 57.5, reps: '5', tReps: '3', rpe: '8'}), '57.5 × 3 @8', 'Shows the plan, not what was typed');
assert.equal(target({kg: '', reps: '', rpe: ''}), '', 'Nothing planned: blank');
assert.equal(target({kg: '15', reps: '15', tReps: '15', rpe: ''}), '15 × 15', 'No RPE target: no @');
const usesPlates = title => vm.runInContext('usesPlates', t)({title});
assert.equal(usesPlates('Overhead Press (Barbell)'), true);
assert.equal(usesPlates('Single Leg Press (Henny Strap)'), true, 'Strap movements load plates (with No bar)');
assert.equal(usesPlates('Bulgarian Split Squat (Dumbbell)'), false, 'Dumbbells: no plate strip');
assert.equal(usesPlates('Lat Pulldown (Cable)'), false);
assert.equal(usesPlates('Leg Extension (Machine)'), false);
console.log('Target column and plate-free movement checks passed.');
