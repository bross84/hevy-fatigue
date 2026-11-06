const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
function node(tag){return {tag,children:[],events:{},style:{},value:'',disabled:false,
  append(...items){this.children.push(...items)},replaceChildren(...items){this.children=items},addEventListener(k,v){this.events[k]=v}};}
const ctx=vm.createContext({document:{createElement:node},Option:function(text,value){return {text,value}},Date});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../static/session-motivation.js'),'utf8')+';this.ui=SessionMotivation;',ctx);
const draft={exercises:[{sets:[{type:'warmup',done:true},{type:'normal',kg:'100',reps:'5',rpe:'7',done:false}]}]};
const baseline=JSON.stringify(draft.exercises),box=node('div');let saves=0;
const find=id=>box.children.find(n=>n.id===id);
const mount=()=>ctx.ui.mount(draft,box,()=>saves++);
mount();assert.equal(find('motivation-level').value,'');assert.ok(find('motivation-reason').disabled);assert.equal(saves,0);
find('motivation-level').value='0';find('motivation-level').events.change();
assert.equal(draft.motivation.level,0);assert.equal(draft.motivation.timing,'before_working_sets');
find('motivation-reason').value='stale';find('motivation-reason').events.change();
find('motivation-note').value='Same movements since August';find('motivation-note').events.input();
assert.equal(draft.motivation.reason,'stale');assert.equal(JSON.stringify(draft.exercises),baseline);
const saved=JSON.parse(JSON.stringify(draft));ctx.ui.mount(saved,box,()=>{});
assert.equal(find('motivation-level').value,'0');assert.equal(find('motivation-note').value,'Same movements since August');
mount();draft.exercises[0].sets[1].done=true;
find('motivation-level').value='3';find('motivation-level').events.change();
assert.equal(draft.motivation.timing,'after_working_sets');
draft.exercises[0].sets[1].done=false;draft.exercises[0].trialStarted=true;
find('motivation-reason').value='life_stress';find('motivation-reason').events.change();
assert.equal(draft.motivation.timing,'after_working_sets');
const frozen=JSON.stringify(draft.motivation);draft.frozenSave={motivation:JSON.parse(frozen)};mount();
assert.ok(find('motivation-level').disabled && find('motivation-reason').disabled && find('motivation-note').disabled);
find('motivation-level').value='4';find('motivation-level').events.change();assert.equal(JSON.stringify(draft.motivation),frozen);
delete draft.frozenSave;mount();find('motivation-level').value='';find('motivation-level').events.change();
assert.equal(draft.motivation,undefined);assert.equal(find('motivation-reason').value,'');assert.equal(find('motivation-note').value,'');
console.log('Motivation UI: optional/zero, reason/note, draft restore, separate workout data, late timing, frozen save and clear passed.');
