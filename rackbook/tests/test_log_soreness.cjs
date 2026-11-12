// Pre-workout pattern soreness: one check-in for the day, never one per exercise card.
const inlineScriptMatches = require('./helpers/html-scripts.cjs');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const html = fs.readFileSync(require('node:path').join(__dirname, '..', 'log.html'), 'utf8');
for (const match of inlineScriptMatches(html)) new vm.Script(match[1]);
function element(tag, cls, text) {
  return {tag, className:cls, text, style:{}, children:[], attrs:{}, append(...items) {this.children.push(...items);},
    replaceChildren(...items) {this.children=items;}, setAttribute(k,v) {this.attrs[k]=v;},
    addEventListener(event, fn) {this[event]=fn;}};
}
// A pause-squat and curl day: none of these titles is one of the four tracked main lifts.
const pause={id:'ps',title:'Pause Squat (Barbell)'}, curl={id:'cu',title:'Bicep Curl (Dumbbell)'};
let saves=0;
const plain=value=>JSON.parse(JSON.stringify(value));
const panel=element('div');
const context = vm.createContext({draft:{exercises:[pause,curl]}, el:element, saveDraft:()=>saves++,
  $:id=>({sessionSoreness:panel})[id], cardEls:new Map()});
vm.runInContext(html.slice(html.indexOf('  // One pre-workout check-in per pattern'), html.indexOf('  const saveDialog =')), context);
vm.runInContext(html.slice(html.indexOf('  let sorenessPatterns ='), html.indexOf('  function renderWorkout()')), context);

assert.equal(typeof context.renderSoreness, 'undefined', 'Exercise cards no longer carry their own soreness question');
assert.ok(!html.includes('movement-soreness'), 'No per-exercise soreness box is built');

context.renderSessionSoreness();
const groups=panel.children.filter(c=>c.tag==='fieldset');
assert.deepEqual(groups.map(g=>g.children[0].text), ['Squat','Press','Hinge'], 'Every workout asks the same three patterns');
const buttons=i=>groups[i].children[1].children;
const pain=i=>groups[i].children[2].children[0];
const refresh=()=>{ groups.splice(0, groups.length, ...panel.children.filter(c=>c.tag==='fieldset')); };
assert.deepEqual(buttons(0).map(b=>b.text), ['None','Mild','Moderate','Severe']);
assert.ok(groups.every((_,i)=>buttons(i).every(b=>b.attrs['aria-pressed']==='false')), 'Blank until answered');

buttons(0)[2].click(); refresh();
assert.deepEqual(plain(context.draft.soreness.squat), {level:2, pain:false});
assert.equal(buttons(0)[2].attrs['aria-pressed'],'true');
buttons(1)[1].click(); refresh();
assert.equal(context.draft.soreness.bench_press.level,1,'Press stores in the existing bench/press slot');
pain(2).checked=true; pain(2).change(); refresh();
assert.deepEqual(plain(context.draft.soreness.deadlift), {level:null, pain:true}, 'Hinge stores in the existing deadlift slot; pain alone is not zero soreness');
buttons(0)[2].click(); refresh();
assert.equal(context.draft.soreness.squat.level,null,'Tapping the chosen answer again clears it');
assert.equal(saves,4);

// Saved ratings no longer depend on which exercise titles are in the workout.
assert.deepEqual(plain(context.sessionSorenessPayload(context.draft.soreness)),
  {bench_press:{level:1,pain:false}, deadlift:{level:null,pain:true}}, 'Cleared or untouched patterns are left out, never sent as zero');
assert.equal(context.sessionSorenessPayload({}), null);
assert.equal(context.sessionSorenessPayload({squat:{level:null,pain:false}}), null);
assert.equal(context.sessionSorenessPayload({elbow:{level:2,pain:false}}), null, 'Only the three stored patterns are sent');

// A frozen (save-in-progress) workout cannot change its check-in.
context.draft.frozenSave={};
context.renderSessionSoreness(); refresh();
assert.ok(groups.every((_,i)=>buttons(i).every(b=>b.disabled===true) && pain(i).disabled===true));
assert.equal(panel.inert,true);
buttons(1)[3].click(); pain(0).checked=true; pain(0).change();
assert.equal(context.draft.soreness.bench_press.level,1,'Taps during a save change nothing');
assert.equal(context.draft.soreness.squat.pain,false);
assert.equal(saves,4);
console.log('Day soreness check-in passed');
