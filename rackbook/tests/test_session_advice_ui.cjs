const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
function node(tag){return {tag,children:[],events:{},attrs:{},style:{},value:'',isConnected:true,
  append(...items){this.children.push(...items)},replaceChildren(...items){this.children=items},
  setAttribute(k,v){this.attrs[k]=v},addEventListener(k,v){this.events[k]=v},reportValidity(){return true}};}
const calls=[];let serial=0,failed=false;
const id=()=>`00000000-0000-4000-8000-${String(++serial).padStart(12,'0')}`;
const row={id:'11111111-1111-4111-8111-111111111111',model_version:'provisional-session-v1',title:'Pull Up',action:'reduce_set',
  message:'Consider one fewer set.',proposed:{working_sets:2,reps:null,target_rpe:null},confidence:'tentative',reasons:['Current check-in and training history'],limitations:['Intent only'],suppressed:false,decision:null,
  evidence:{comparable_exposures:2,history_workouts:12,checkins:[{date:'2026-11-05',tiredness:3,perceived_recovery:2}]}};
const c=vm.createContext({document:{createElement:node},trainingUrl:p=>'/training'+p,trainingUUID:id,
  fetch:async(url,options)=>{const body=JSON.parse(options.body);calls.push({url,body});assert.ok(url.startsWith('/training/session-advice'));
    if(failed)throw Error('offline');
    if(url.endsWith('/decisions'))row.decision={id:body.id,action:body.action,reason:body.reason,dose:body.modification || row.proposed};
    return {ok:true,json:async()=>structuredClone(row)};}});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../static/session-advice.js'),'utf8')+';this.advice=SessionAdvice;',c);
const walk=n=>[n,...n.children.flatMap(walk)],text=n=>[n.textContent,...n.children.map(text)].join(' ');
const button=(box,name)=>walk(box).find(n=>n.tag==='button'&&n.textContent===name);
const input=(box,name)=>walk(box).find(n=>n.attrs['aria-label']===name);
const flush=()=>new Promise(resolve=>setImmediate(resolve));
const ex={id:'movement',template_id:'pullup',title:'Pull Up',ref:{autoWeights:false},sets:[
  {type:'normal',reps:'5',rpe:'6',kg:'12.5',done:false},
  {type:'normal',reps:'5',rpe:'7',kg:'12.5',done:false},
  {type:'normal',reps:'3',rpe:'8',kg:'12.5',done:false}]};
const draft={client_workout_id:'22222222-2222-4222-8222-222222222222',title:'Workout',startedAt:new Date().toISOString(),exercises:[ex]};
const baseline=JSON.stringify(ex.sets),box=node('section');let saves=0;
(async()=>{
  c.advice.mount(draft,ex,box,()=>saves++);await flush();await flush();
  assert.equal(calls[0].body.automatic_weights,false);assert.equal(draft.advisory_links[0].decision_id,null);
  button(box,'Accept').events.click();await flush();
  assert.equal(row.decision.action,'accept');assert.equal(JSON.stringify(ex.sets),baseline);
  button(box,'Modify').events.click();input(box,'Intended working sets for Pull Up').value='2';
  input(box,'Intended reps (optional) for Pull Up').value='4';
  input(box,'Optional recommendation reason for Pull Up').value='Time available';
  button(box,'Record modification').events.click();await flush();
  assert.equal(row.decision.action,'modify');assert.equal(row.decision.dose.reps,4);
  assert.match(text(box),/Recorded intent: 2 working sets, 4 reps/);
  assert.equal(String(input(box,'Intended reps (optional) for Pull Up').value),'4');
  assert.equal(JSON.stringify(ex.sets),baseline,'Modify records intent without editing any workout prescription');
  button(box,'Dismiss').events.click();await flush();
  assert.equal(row.decision.action,'dismiss');assert.equal(box.children[0].open,false);
  box.children[0].open=true;button(box,'Not now').events.click();await flush();
  assert.equal(row.decision.action,'not_now');assert.equal(box.children[0].open,false);
  assert.equal(draft.advisory_links[0].decision_id,row.decision.id);
  assert.equal(JSON.stringify(ex.sets),baseline);assert.ok(saves>=5);
  const before=calls.length;failed=true;button(box,'Accept').events.click();await flush();
  assert.equal(calls.length,before+1,'An uncertain response must not automatically repost a decision');
  assert.match(text(box),/offline/);assert.equal(JSON.stringify(ex.sets),baseline);
  draft.frozenSave={};const frozen=node('section');c.advice.mount(draft,ex,frozen,()=>{});
  assert.match(text(frozen),/frozen/);assert.equal(calls.length,before+1);
  console.log('Accept/Modify/Dismiss/Not now preserve programming, capture intent, persist links and never repost on errors.');
})().catch(e=>{console.error(e);process.exitCode=1});
