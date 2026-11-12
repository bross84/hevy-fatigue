const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const html = fs.readFileSync(require('node:path').join(__dirname, '..', 'log.html'), 'utf8');
function el(tag, cls, text) {
  return {tag, cls, textContent:text, children:[], attrs:{}, style:{}, events:{},
    classList:{toggle(){}}, append(...items){this.children.push(...items);},
    setAttribute(k,v){this.attrs[k]=v;}, addEventListener(k,fn){this.events[k]=fn;}};
}
const noop=()=>{};
let saved=0, rests=0, redraws=0;
const context=vm.createContext({trainingUrl:path=>path.startsWith("/training/")?path:"/training"+path,el, unit:'kg', unitFor:()=> 'kg', exerciseUnitControl:()=>el('button'), trim:String, stepOf:()=>2.5, makeReorderable:noop,
  restLabel:String, restFor:()=>60, renderRefBar:()=>el('div'), renderSoreness:noop, renderTrial:noop, trialEnabled:false,
  queueStress:noop,fillStress:noop,paintNumbers:noop,matchMedia:()=>({matches:false}),kindOf:s=>s.type,KIND:{warmup:'W'},
  prepareKeypadInput:noop,primaryText:s=>s.kg,refText:()=>'',primaryInputs:new Map(),refCells:new Map(),
  rpeControl:()=>({reportValidity:()=>true}),setE1rm:()=>null,setE1Cells:new Map(),setStressCells:new Map(),
  makeSwipeable:noop,renderLoader:()=>el('div'),applyAuto:noop,saveDraft:()=>saved++,
  showRpe:noop,restStart:()=>rests++,closeNumberPad:noop,renderWorkout:()=>redraws++,setTimeout:noop});
vm.runInContext(fs.readFileSync(require('node:path').join(__dirname,'../static/session-review.js'),'utf8'),context);
vm.runInContext(html.slice(html.indexOf('  function exerciseComplete('), html.indexOf('  function tickClock()')),context);
const nodes=n=>[n,...(n.children||[]).flatMap(x=>typeof x==='object'?nodes(x):[])];
const ticks=card=>nodes(card).filter(n=>n.cls==='tick');
const toggle=card=>nodes(card).find(n=>n.attrs['aria-expanded']!==undefined);
const section=(card,cls)=>nodes(card).find(n=>n.cls===cls);
const set=done=>({type:'normal',kg:'100',reps:'5',rpe:'7',done});
const ex={title:'Squat',ref:{state:null},sets:[set(false),set(false)]};
let card=context.renderExercise(ex);
ticks(card)[1].events.click();
assert.equal(Boolean(ex.collapsed),false,'Checking last row first must not collapse unfinished work');
ticks(card)[0].events.click();
assert.equal(Boolean(ex.collapsed),false,'Completing all working sets leaves the card open');
assert.equal(section(card,'exright').hidden,false);
assert.equal(rests,2,'Completion still starts the rest timer');
toggle(card).events.click();
assert.equal(ex.collapsed,true,'Manual collapse remains available');
assert.equal(section(card,'exleft').hidden,true);
assert.equal(section(card,'exright').hidden,true);
assert.equal(toggle(card).textContent,'Reopen');
assert.equal(toggle(card).attrs['aria-expanded'],'false');
card=context.renderExercise(ex);
assert.equal(section(card,'exright').hidden,true,'Collapsed state survives redraw');
toggle(card).events.click();
assert.equal(ex.collapsed,false);
assert.equal(section(card,'exright').hidden,false);
card=context.renderExercise(ex);
assert.equal(section(card,'exright').hidden,false,'Reopened completed cards stay open');
ticks(card)[0].events.click();
assert.equal(ex.sets[0].done,false);
assert.equal(Boolean(ex.collapsed),false);
ticks(card)[0].events.click();
assert.equal(ex.collapsed,false,'Completing the exercise again leaves it open');
toggle(card).events.click();
assert.equal(ex.collapsed,true,'Manual collapse still works after completion');
toggle(card).events.click();
const add=nodes(card).find(n=>n.textContent==='+ Add set'); add.events.click();
assert.equal(ex.collapsed,false);
assert.equal(ex.sets.length,3);
assert.equal(ex.sets[2].done,false);
assert.equal(redraws,1);
assert.equal(context.exerciseComplete({sets:[]}),false);
assert.equal(context.exerciseComplete({sets:[{type:'warmup',done:true}]}),false);
assert.equal(context.exerciseComplete({sets:[set(true),{type:'warmup',done:false}]}),true);
console.log('Exercise completion, manual collapse, reopening, redraw persistence and add-set checks passed.');

// Exercise the rendered Rx/actual controls with the real next-set calculation.
Object.assign(context, {
  LB_PER_KG: 2.20462262185, num: Number,
  lbOfKg: kg => kg * 2.20462262185,
  pctFor: rpe => ({5: .7, 6: .75, 7: .8})[rpe],
  plannedKg: lb => Math.round(lb / 2.20462262185 / 2.5) * 2.5,
  showWeight: noop,
  rpeControl: (value, change, name) => ({name, value, change, reportValidity:()=>true}),
  showRpe: (control, value) => { control.value = value; },
});
vm.runInContext(html.slice(html.indexOf('  function setE1rm('), html.indexOf('  function refreshCard(')), context);
const rxSet = () => ({type:'normal',kg:'100',reps:'5',rpe:'6',done:false,manual:false});
const adaptive = {title:'Squat',ref:{ls:true,basis:'e1rm'},sets:[rxSet(),rxSet(),{...rxSet(),manual:true}]};
card = context.renderExercise(adaptive);
const rx = nodes(card).filter(n=>n.name==='RPErx');
const act = nodes(card).filter(n=>n.name==='RPEact');
assert.equal(rx.length, 3); assert.equal(act.length, 3);
act[0].change('5');
assert.equal(adaptive.sets[0].kg,'100','Entering actual effort never changes the performed load');
ticks(card)[0].events.click();
assert.equal(adaptive.sets[0].rpe,'6','Prescription survives actual effort entry');
assert.equal(adaptive.sets[0].arpe,'5');
assert.ok(Number(adaptive.sets[1].kg)>100,'Easier actual effort raises the next load');
assert.equal(adaptive.sets[2].kg,'100','Manual weights remain fixed');
act[0].change('7');
assert.ok(Number(adaptive.sets[1].kg)<100,'Harder actual effort lowers the next load');
assert.equal(adaptive.sets[0].kg,'100','Completed weight remains fixed');
const nextWeight = adaptive.sets[1].kg;
rx[0].change('5');
assert.equal(adaptive.sets[1].kg,nextWeight,'Changing Rx cannot replace completed actual effort');
// Restore prescription, then check undo/redo and redraw preserve both values.
rx[0].change('6'); ticks(card)[0].events.click(); ticks(card)[0].events.click();
card = context.renderExercise(adaptive);
assert.equal(nodes(card).find(n=>n.name==='RPErx').value,'6');
assert.equal(nodes(card).find(n=>n.name==='RPEact').value,'7');
ticks(card)[1].events.click();
assert.equal(adaptive.sets[1].arpe,'6','On-target completion retains the existing no-extra-tap default');
adaptive.ref.ts={found:true,e1rm_lb:330};
adaptive.ref.ls=false;
assert.equal(context.baseFor(adaptive,1),330,'LS off keeps the existing pinned e1RM basis');
act[0].change('5');
assert.equal(context.baseFor(adaptive,1),330,'Actual RPE cannot enable LS when the toggle is off');
adaptive.ref.basis='tm';adaptive.ref.tmPct=.95;
assert.equal(context.baseFor(adaptive,1),330*.95,'LS off also preserves the TM basis');
adaptive.ref.ls=true;
assert.equal(context.baseFor(adaptive,1),context.setE1rm(adaptive.sets[0]),'LS on uses previous actual effort again');
console.log('Separate Rx/actual controls, easier/harder adjustments, manual/done weights and undo/redraw passed.');
