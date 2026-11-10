// Run with node rackbook/tests/test_week_text_ui.cjs; no browser/network/Hevy writes.
// Week text helpers: the "#" search window, inserting a picked movement, and callout labels.
const assert = require('node:assert/strict'), fs = require('node:fs'), path = require('node:path');
const root = path.join(__dirname, '..');
const WeekText = require(path.join(root, 'static', 'week-text.js'));

// "#" search opens at the start of a line and closes once sets begin.
const text = 'Week 1 Day 1\n#squ';
assert.deepEqual(WeekText.hashQuery(text, text.length), { start: 13, query: 'squ' });
assert.deepEqual(WeekText.hashQuery('Week 1 Day 1\n#', 14), { start: 13, query: '' });
assert.equal(WeekText.hashQuery('#Squat (Barbell) 3x5', 20), null, 'sets started');
assert.equal(WeekText.hashQuery('#Lateral Raise myo 1', 20), null, 'myo started');
assert.equal(WeekText.hashQuery('Week 1 Day 1', 12), null, 'no hash');
assert.equal(WeekText.hashQuery('note #squ', 9), null, 'hash must start the line');
assert.deepEqual(WeekText.hashQuery('  #3-board', 10), { start: 2, query: '3-board' }, 'numbers in names keep the search open');

// Picking replaces the typed query with the exact title and a space, keeping what follows.
const picked = WeekText.insertMovement('Week 1 Day 1\n#squ\n#bench 5x4', 17, { start: 13, query: 'squ' }, 'squat, low bar w/ belt');
assert.equal(picked.text, 'Week 1 Day 1\n#squat, low bar w/ belt \n#bench 5x4');
assert.equal(picked.caret, 13 + '#squat, low bar w/ belt '.length);
const mid = WeekText.insertMovement('#ben 5x4', 4, { start: 0, query: 'ben' }, 'Bench Press (Barbell)');
assert.equal(mid.text, '#Bench Press (Barbell) 5x4');

// Labels write planned sets back in the notation.
const s = (o) => Object.assign({ reps: 5, rpe: null, ts: false, amrap: false, backoff: false, ddp: false, myo: false, drops: null, drops_open: false }, o);
assert.equal(WeekText.setsText([s({ reps: 3, rpe: 8, ts: true }), s({ rpe: 7, backoff: true }), s({ rpe: 7, backoff: true })], 90), '1x3@8 TS, 2x5@7 BO TM90');
assert.equal(WeekText.setsText([s({ reps: 3, rpe: 6 }), s({ reps: 3, rpe: 7 }), s({ reps: 3, rpe: 8 })]), '3x3@6,7,8');
assert.equal(WeekText.setsText([s({ rpe: 8 }), s({ rpe: 8 }), s({ rpe: 8, amrap: true })]), '3x5+@8');
assert.equal(WeekText.setsText([s({ reps: 10, rpe: 9 }), s({ reps: 10, rpe: 9, drops_open: true })]), '2x10@9 DS');
assert.equal(WeekText.setsText([s({ reps: 10, drops: 2 })]), '1x10 DS2');
assert.equal(WeekText.setsText([s({ reps: 4, rpe: 6, ddp: true }), s({ reps: 4, rpe: 6, ddp: true })]), '2x4@6 DDP');
assert.equal(WeekText.setsText([s({ reps: 15, reps_max: 20, rpe: 9, myo: true })]), 'myo 15-20@9');
assert.equal(WeekText.hasCallouts({ sets: [s({ ts: true })] }), false, 'TS alone already shows on the page');
assert.equal(WeekText.hasCallouts({ tm_pct: 85, sets: [s({})] }), true);
assert.equal(WeekText.hasCallouts({ sets: [s({ ddp: true })] }), true);

// Pages load the helper from /training and use it.
const builder = fs.readFileSync(path.join(root, 'mesocycles.html'), 'utf8'), log = fs.readFileSync(path.join(root, 'log.html'), 'utf8');
for (const html of [builder, log]) assert.match(html, /<script src="\/training\/static\/week-text\.js\?v=1"><\/script>/);
assert.match(builder, /api\('\/api\/week-text\/preview'/);
assert.match(builder, /api\('\/api\/week-text\/drafts'/);
assert.match(log, /planCallouts: WeekText\.setsText\(ex\.sets, ex\.tm_pct\)/);
console.log('Week text search, insertion, labels and page wiring passed.');
