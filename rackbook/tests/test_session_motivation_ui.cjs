const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
function node(tag){return {tag,children:[],events:{},style:{},value:'',disabled:false,required:false,
  append(...items){this.children.push(...items)},replaceChildren(...items){this.children=items},addEventListener(k,v){this.events[k]=v},setAttribute(){},reportValidity(){return this.value!==''}};}
const calls=[];
const ctx=vm.createContext({document:{createElement:node},Option:function(text,value){return {text,value}},Date,trainingUrl:p=>'/training'+p,
  fetch:async(url,options)=>{calls.push({url,body:JSON.parse(options.body)});return {ok:true,json:async()=>({recorded:true,weekly_review_eligible:false})};}});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../static/session-motivation.js'),'utf8')+';this.ui=SessionMotivation;',ctx);
const draft={client_workout_id:'session',startedAt:new Date().toISOString(),exercises:[{sets:[{type:'warmup',done:true},{type:'normal',kg:'100',reps:'5',rpe:'7',done:false}]}]};
const baseline=JSON.stringify(draft.exercises),box=node('div');let saves=0;
const find=id=>box.children.find(n=>n.id===id),mount=()=>ctx.ui.mount(draft,box,()=>saves++);
(async()=>{
  mount();assert.equal(find('motivation-level').value,'');assert.ok(find('motivation-level').required);assert.equal(ctx.ui.ready(draft),false);
  assert.equal(find('motivation-reason'),undefined);assert.ok(find('confirmMotivation').disabled);
  find('motivation-level').value='0';find('motivation-level').events.change();
  find('motivation-note').value='Tired but excited';find('motivation-note').events.input();
  assert.equal(ctx.ui.ready(draft),false);await find('confirmMotivation').events.click();
  assert.equal(ctx.ui.ready(draft),true);assert.equal(calls.length,1);assert.equal(calls[0].url,'/training/session-checkins');
  assert.equal(calls[0].body.motivation.level,0);assert.equal(calls[0].body.motivation.note,'Tired but excited');
  assert.equal(draft.motivation.reason,undefined);assert.equal(JSON.stringify(draft.exercises),baseline);
  await find('confirmMotivation').events.click();assert.equal(calls.length,1);
  mount();assert.equal(ctx.ui.ready(draft),true);
  draft.exercises[0].sets[1].done=true;draft.exercises[0].trialStarted=true;
  find('motivation-note').value='Updated after first set';find('motivation-note').events.input();
  assert.equal(ctx.ui.ready(draft),false);assert.equal(draft.motivation.timing,'after_working_sets');
  await find('confirmMotivation').events.click();assert.equal(ctx.ui.ready(draft),true);
  draft.frozenSave={};mount();assert.ok(find('motivation-level').disabled&&find('motivation-note').disabled&&find('confirmMotivation').disabled);
  const frozen=JSON.stringify(draft.motivation);find('motivation-level').value='4';find('motivation-level').events.change();assert.equal(JSON.stringify(draft.motivation),frozen);
  await ctx.ui.ensureSaved(draft);assert.equal(calls.length,2);
  delete draft.frozenSave;mount();find('motivation-level').value='';find('motivation-level').events.change();assert.equal(ctx.ui.ready(draft),false);
  console.log('Required motivation: explicit zero, optional note, no reason, confirmation, unchanged workout data, late timing, frozen saves and no duplicate confirmation passed.');
})().catch(e=>{console.error(e);process.exitCode=1;});
