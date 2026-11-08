const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
function node(tag){return {tag,children:[],events:{},style:{},value:'',disabled:false,required:false,textContent:'',
  append(...items){this.children.push(...items)},replaceChildren(...items){this.children=items},addEventListener(k,v){this.events[k]=v},setAttribute(){},reportValidity(){return this.value!==''}};}
const text=n=>[n.textContent,...(n.children||[]).map(text)].join(' ');
const sleep=()=>new Promise(r=>setTimeout(r,10));
const source=fs.readFileSync(path.join(__dirname,'../static/session-motivation.js'),'utf8')+';this.ui=SessionMotivation;';

function scenario({offer=null,eligible=false,planned=false,reviewWeek}) {
  const reviews=[],fetched=[];
  const ctx=vm.createContext({document:{createElement:node},Option:function(t,v){return {text:t,value:v}},Date,trainingUrl:p=>'/training'+p,
    AICoach:{openUrl:id=>'/?coaching_conversation='+id,
      reviewWeek:async(plan,kind,session,onStatus,onPrepared)=>{
        reviews.push(kind+':'+plan);
        if(reviewWeek)return reviewWeek(plan,kind,onPrepared);
        onPrepared({id:'conversation-'+kind});return {id:'conversation-'+kind,turns:[{status:'complete',response:kind+' review text'}]};}},
    fetch:async(url,options)=>{
      if(url.startsWith('/api/ai/conversations/')){fetched.push(url);return {ok:true,json:async()=>({id:'conversation-end',turns:[{status:'complete',response:'saved'}]})};}
      return {ok:true,json:async()=>({recorded:true,weekly_review_eligible:eligible,closing_review:offer})};}});
  vm.runInContext(source,ctx);
  const draft={client_workout_id:'s'+Math.random(),startedAt:new Date().toISOString(),exercises:[{sets:[{type:'normal',kg:'100',reps:'5',rpe:'7',done:false}]}]};
  if(planned)draft.planned_session={mesocycle_id:'next-plan',session_id:'day1'};
  const box=node('div'),saves=[];
  const find=id=>box.children.find(n=>n.id===id);
  const mount=()=>ctx.ui.mount(draft,box,()=>saves.push(1));
  const confirm=async()=>{mount();find('motivation-level').value='1';find('motivation-level').events.change();await find('confirmMotivation').events.click();await sleep();};
  return {ctx,draft,box,find,mount,confirm,reviews,fetched};
}

(async()=>{
  // A workout with no plan still gets the review of the microcycle just finished.
  let s=scenario({offer:{plan_id:'done-plan',name:'Push and pull'}});
  await s.confirm();
  assert.deepEqual(s.reviews,['end:done-plan']);
  assert.equal(s.draft.closing_review_id,'conversation-end');
  const closing=s.find('microcycleClosingReview');
  assert.match(text(closing),/Finished microcycle · complete/);
  assert.match(text(closing),/end review text/);
  assert.match(text(closing),/No programming changes were applied/);
  assert.ok(closing.children.some(n=>n.tag==='a'&&n.href==='/?coaching_conversation=conversation-end'));
  // Mounting again in the same page load never asks again.
  s.mount();await sleep();assert.deepEqual(s.reviews,['end:done-plan']);

  // Day 1 of the next plan: the finished microcycle first, then the existing look-ahead review.
  s=scenario({offer:{plan_id:'done-plan'},eligible:true,planned:true});
  await s.confirm();
  assert.deepEqual(s.reviews,['end:done-plan','start:next-plan']);
  assert.equal(s.draft.weekly_review_id,'conversation-start');
  assert.equal(s.draft.closing_review_id,'conversation-end');

  // Nothing finished: only the existing opening review, exactly as before.
  s=scenario({eligible:true,planned:true});
  await s.confirm();
  assert.deepEqual(s.reviews,['start:next-plan']);
  assert.equal(s.draft.closing_review_id,undefined);
  assert.equal(text(s.find('microcycleClosingReview')).trim(),'');

  // No offer and no plan: no AI traffic at all.
  s=scenario({});
  await s.confirm();
  assert.deepEqual(s.reviews,[]);

  // A failed review never blocks the check-in or the look-ahead review, and is never resent.
  s=scenario({offer:{plan_id:'done-plan'},eligible:true,planned:true,
    reviewWeek:async(plan,kind,onPrepared)=>{if(kind==='end')throw Error('AI unavailable.');onPrepared({id:'conversation-start'});return {id:'conversation-start',turns:[{status:'complete',response:'ok'}]};}});
  await s.confirm();
  assert.ok(s.ctx.ui.ready(s.draft));
  assert.match(text(s.find('microcycleClosingReview')),/AI unavailable\. Logging can continue; no automatic resend\./);
  assert.deepEqual(s.reviews,['end:done-plan','start:next-plan']);
  s.mount();await sleep();assert.deepEqual(s.reviews,['end:done-plan','start:next-plan']);

  // Once training has started the review is not run now; an already-created one is only shown.
  s=scenario({offer:{plan_id:'done-plan'}});
  s.draft.exercises[0].sets[0].done=true;s.draft.exercises[0].trialStarted=true;
  await s.confirm();
  assert.deepEqual(s.reviews,[]);
  assert.match(text(s.find('microcycleClosingReview')),/Training has started, so the finished microcycle was not reviewed automatically/);
  s=scenario({offer:{plan_id:'done-plan'}});
  s.draft.exercises[0].sets[0].done=true;s.draft.exercises[0].trialStarted=true;s.draft.closing_review_id='conversation-end';
  await s.confirm();
  assert.deepEqual(s.reviews,[]);assert.deepEqual(s.fetched,['/api/ai/conversations/conversation-end']);
  assert.match(text(s.find('microcycleClosingReview')),/saved/);

  // After a reload the confirmed check-in is re-posted once and resumes the review.
  s=scenario({offer:{plan_id:'done-plan'}});
  s.draft.motivation={level:1,note:'',recorded_at:new Date().toISOString(),timing:'before_working_sets'};
  s.draft.checkin_confirmation={signature:JSON.stringify({motivation:s.draft.motivation,plan:null,start:s.draft.startedAt}),confirmed_at:new Date().toISOString()};
  s.mount();await sleep();
  assert.deepEqual(s.reviews,['end:done-plan']);
  s.mount();await sleep();assert.deepEqual(s.reviews,['end:done-plan']);

  // A frozen save never starts a review.
  s=scenario({offer:{plan_id:'done-plan'}});
  s.draft.frozenSave={};s.draft.motivation={level:1,note:'',recorded_at:new Date().toISOString(),timing:'before_working_sets'};
  await s.ctx.ui.ensureSaved(s.draft);s.mount();await sleep();
  assert.deepEqual(s.reviews,[]);
  console.log('Closing review: runs without a plan, before the opening review, once per page load, never blocks logging or resends passed.');
})().catch(e=>{console.error(e);process.exitCode=1;});
