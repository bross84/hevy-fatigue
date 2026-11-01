/* Exercise the real recovery panel, not a stub of its state transitions. */
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),path=require('node:path');
function element(tag){return {tag,children:[],events:{},hidden:false,textContent:'',disabled:false,style:{},
  append(...nodes){this.children.push(...nodes)},prepend(node){this.children.unshift(node)},remove(){},setAttribute(){},
  addEventListener(name,fn){this.events[name]=fn}};}
const main=element('main'),storage=new Map(),sent=[];let response,posts=0,reloads=0,nextId=0,confirmCorrection=true;
const context=vm.createContext({
  document:{createElement:element,getElementById:()=>null,querySelector:()=>main},
  trainingUrl:p=>'/training'+p,trainingUUID:()=>`new-save-${++nextId}`,confirm:()=>confirmCorrection,
  localStorage:{setItem:(k,v)=>storage.set(k,v)},location:{reload(){reloads++}},
  fetch:async(url,options)=>{if(options?.method==='POST'){posts++;sent.push(options.body);}return {status:response.code||200,ok:!(response.code>=400),json:async()=>response.body};}
});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../rackbook/static/save-recovery.js'),'utf8')+';this.recovery=WorkoutSave',context);
const flush=()=>new Promise(resolve=>setImmediate(resolve));
const buttons=box=>box.children.filter(n=>n.tag==='button');
const button=(box,text)=>buttons(box).find(b=>b.textContent===text);
const draft=()=>({client_workout_id:'old-id',title:'Edited title',planned_session:{mesocycle_id:'missing',session_id:'day'},
  frozenSave:{client_workout_id:'old-id',title:'Frozen title',end_time:'original',exercises:[]}});
(async()=>{
  // Business validation is now durably rejected by the server. Correction is
  // explicit, changes identity, and the next freeze uses current edited data.
  response={body:{state:'rejected',status:'Rejected',failure_reason:'Plan no longer exists'}};
  const d=draft();context.recovery.panel(d,()=>{throw Error('Must not clear rejected draft')});await flush();
  let box=main.children[0],correct=button(box,'Correct rejected draft');assert.equal(correct.hidden,false);
  await correct.events.click();assert.equal(reloads,1);assert.equal(d.frozenSave,undefined);assert.notEqual(d.client_workout_id,'old-id');
  const fresh=context.recovery.freeze(d,{title:d.title,end_time:'corrected',exercises:[]});
  assert.equal(fresh.title,'Edited title');assert.equal(fresh.end_time,'corrected');
  assert.equal(posts,0,'Correction must not post or finalize');
  // Field-level FastAPI rejection happens before a journal can be prepared.
  // Only that explicit response permits correction after a 404 status check.
  const invalid=draft();context.recovery.noteFailure(invalid,{status:422,validationRejected:true,message:'Invalid notes'});
  response={code:404,body:{detail:'No journal entry'}};
  context.recovery.panel(invalid,()=>{});await flush();box=main.children[0];
  assert.equal(button(box,'Correct rejected draft').hidden,false);
  await button(box,'Correct rejected draft').events.click();assert.equal(invalid.validationRejected,undefined);
  // A timeout/unknown 422/404 never grants permission to reset an ambiguous ID.
  for(const error of [{status:502},{status:422,validationRejected:false}]){
    const uncertain=draft();context.recovery.noteFailure(uncertain,error);
    context.recovery.panel(uncertain,()=>{});await flush();
    assert.equal(button(main.children[0],'Correct rejected draft').hidden,true);
    assert.equal(uncertain.client_workout_id,'old-id');assert.ok(uncertain.frozenSave);
  }
  response={body:{state:'uncertain',status:'Verify in Hevy'}};
  const uncertain=draft();context.recovery.panel(uncertain,()=>{});await flush();
  assert.equal(button(main.children[0],'Correct rejected draft').hidden,true);
  assert.equal(button(main.children[0],'Link verified Hevy workout').hidden,false);
  // Prepared preflight failures can be resumed and are not offered reconciliation.
  response={body:{state:'prepared',status:'Not sent',failure_reason:'Writes disabled'}};
  const prepared=draft();let completed=0;context.recovery.panel(prepared,()=>completed++);await flush();
  assert.equal(button(main.children[0],'Resume prepared save').hidden,false);
  assert.equal(button(main.children[0],'Link verified Hevy workout').hidden,true);
  response={body:{state:'complete',status:'Saved'}};
  await button(main.children[0],'Resume prepared save').events.click();
  assert.equal(posts,1);assert.equal(completed,1);
  assert.equal(sent[0],JSON.stringify(prepared.frozenSave));assert.equal(prepared.client_workout_id,'old-id');
  // Failed storage cannot discard the frozen identity while unlocking a draft.
  const quota=draft();context.localStorage.setItem=()=>{throw Error('Quota')};
  assert.throws(()=>context.recovery.correct(quota),/Quota/);
  assert.equal(quota.client_workout_id,'old-id');assert.ok(quota.frozenSave);
  // A delayed status response from an old draft cannot clear a newly loaded
  // session while the logger's deep-link request is completing.
  const log=fs.readFileSync(path.join(__dirname,'../rackbook/log.html'),'utf8');
  let cleared=0;const current={client_workout_id:'new-session'};
  const recoveryContext=vm.createContext({draft:current,clearDraft(){cleared++},document:{getElementById:()=>null},
    show(){},$:()=>({querySelector:()=>({})}),WorkoutSave:{monitoring(){}}});
  vm.runInContext(log.slice(log.indexOf('  function completeRecoveredSave('),log.indexOf("  DraftTransfer.install('workout-draft');")),recoveryContext);
  recoveryContext.completeRecoveredSave({client_workout_id:'old-session',monitoring_refresh:'pending'});
  assert.equal(cleared,0);assert.equal(recoveryContext.draft,current);
  recoveryContext.completeRecoveredSave({client_workout_id:'new-session',monitoring_refresh:'pending'});
  assert.equal(cleared,1);
  console.log('Recovery UI: rejected correction, fresh identity/payload, model-validation recovery, ambiguous-save protection, prepared retry and storage failure passed.');
})().catch(e=>{console.error(e);process.exitCode=1});
