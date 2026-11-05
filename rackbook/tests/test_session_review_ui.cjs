const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../static/session-review.js'),'utf8');
function node(tag){return {tag,children:[],events:{},isConnected:true,textContent:'',
  append(...items){this.children.push(...items)},replaceChildren(...items){this.children=items},
  addEventListener(k,fn){this.events[k]=fn}};}
let response,fail=false;
const c=vm.createContext({document:{createElement:node,getElementById:()=>null},trainingUrl:p=>'/training'+p,
  fetch:async()=>{if(fail)throw Error('offline');return {ok:true,json:async()=>response}}});
vm.runInContext(source+';this.capture=SessionCapture;this.ui=SessionReviewUI;',c);
const draft={title:'Day',exercises:[{id:'ex',template_id:'sq',title:'Squat',ref:{ls:true,basis:'e1rm'},sets:[
  {type:'normal',reps:'5',rpe:'6',kg:'100',ts:true,done:false},
  {type:'normal',reps:'5',rpe:'6',kg:'95',done:false}]}]};
const chart=new Map([['6|5',.75],['7|5',.8]]);
c.capture.start(draft,'plan',chart,3);
const snapshot=JSON.stringify(draft.prescription),ex=draft.exercises[0],s=ex.sets[0];
s.reps='4';s.rpe='7';s.kg='97.5';s.arpe='7';s.actualSource='entered';s.autoSuggestion=100;s.manual=true;
c.capture.complete(ex,s);
assert.equal(s.review.suggested_weight_kg,100);
assert.equal(s.review.manual_weight,true);
assert.equal(c.capture.evidence(s,.8).rpe_source,'entered');
assert.equal(c.capture.evidence(s,.8).actual_percentage,.8);
ex.sets.pop();chart.set('7|5',.9);
assert.equal(JSON.stringify(draft.prescription),snapshot,'Edits/deletions and later table changes must not rewrite the loaded prescription');
s.actualSource='copied_target';assert.equal(c.capture.evidence(s,.8).rpe_source,'copied_target');
s.arpe='';assert.equal(c.capture.evidence(s,null).rpe_source,'unrated');
const restored=JSON.parse(JSON.stringify(draft));
assert.equal(restored.prescription.exercises[0].sets.length,2);
assert.equal(restored.exercises[0].sets[0].review.set_id,restored.prescription.exercises[0].sets[0].id);
const text=n=>[n.textContent,...n.children.map(text)].join(' ');
(async()=>{
  const box=node('section');response={available:false,reason:'No captured prescription'};
  await c.ui.show('old',box);assert.match(text(box),/No captured prescription/);
  fail=true;await c.ui.show('new',box);assert.match(text(box),/saved workout is unaffected/);
  fail=false;response={available:true,review:{prescription_source:'plan',movements:[{title:'<script>unsafe</script>',completed_sets:2,planned_sets:3,omitted_sets:1,added_sets:0,completed_reps:10,planned_reps:15,opening_e1rm_kg:125,last_e1rm_kg:120,change_pct:-4,sets:[],notes:[]}],notes:['Descriptive only']}};
  await c.ui.show('new',box);assert.match(text(box),/3 originally planned/);assert.match(text(box),/1 omitted/);assert.match(text(box),/Descriptive only/);
  assert.equal(box.children[2].children[0].textContent,'<script>unsafe</script>','Titles render as text');
  const transfer=vm.createContext({structuredClone});
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../static/draft-transfer.js'),'utf8')+';this.t=DraftTransfer;',transfer);
  restored.startedAt='2026-11-04T10:00:00Z';restored.exercises[0].sets[0].done=true;
  transfer.t.validateWorkout(restored);
  const broken=structuredClone(restored);broken.prescription.rpe_chart[0].percentage=0;
  assert.throws(()=>transfer.t.validateWorkout(broken));
  console.log('Frozen prescription, evidence provenance, deleted sets, reload/transfer and descriptive review UI passed.');
})().catch(e=>{console.error(e);process.exitCode=1});
