// Weekly coaching call at the pre-training check-in (ADR 0002): local rendering only, AI and fetch mocked.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
function node(tag){return {tag,children:[],events:{},style:{},value:'',disabled:false,required:false,textContent:'',
  append(...items){this.children.push(...items)},replaceChildren(...items){this.children=items},addEventListener(k,v){this.events[k]=v},setAttribute(){},reportValidity(){return this.value!==''}};}
const text=n=>[n.textContent,...(n.children||[]).map(text)].join(' ');
const sleep=()=>new Promise(r=>setTimeout(r,10));
const source=fs.readFileSync(path.join(__dirname,'../static/session-motivation.js'),'utf8')+';this.ui=SessionMotivation;';

function scenario({offer=null,eligible=false,planned=false,reviewWeek,cards=false}) {
  const reviews=[],fetched=[],mounted=[];
  const strip=marker=>t=>({text:String(t).replace(marker,'[card]'),found:String(t).includes(marker)});
  const ctx=vm.createContext({document:{createElement:node},Option:function(t,v){return {text:t,value:v}},Date,trainingUrl:p=>'/training'+p,
    AICoach:{openUrl:id=>'/?coaching_conversation='+id,
      reviewWeek:async(plan,kind,session,onStatus,onPrepared)=>{
        reviews.push(kind+':'+plan);
        if(reviewWeek)return reviewWeek(plan,kind,onPrepared);
        onPrepared({id:'conversation-'+kind});return {id:'conversation-'+kind,turns:[{id:'turn-1',status:'complete',response:kind+' review text PROPOSAL'}]};}},
    fetch:async(url,options)=>{
      if(url.startsWith('/api/ai/conversations/')){fetched.push(url);return {ok:true,json:async()=>({id:'conversation-call',turns:[{status:'complete',response:'saved'}]})};}
      return {ok:true,json:async()=>({recorded:true,weekly_review_eligible:eligible,closing_review:offer})};}});
  if(cards){
    ctx.PlanProposal={strip:strip('PROPOSAL'),plain:t=>String(t).replace('PROPOSAL','[card]'),mount:(host,reply,options)=>mounted.push(['proposal',reply,options])};
    ctx.PlanChange={strip:strip('CHANGE'),mount:(host,reply,options)=>mounted.push(['change',reply,options])};
  }
  vm.runInContext(source,ctx);
  const draft={client_workout_id:'s'+Math.random(),startedAt:new Date().toISOString(),exercises:[{sets:[{type:'normal',kg:'100',reps:'5',rpe:'7',done:false}]}]};
  if(planned)draft.planned_session={mesocycle_id:'next-plan',session_id:'day1'};
  const box=node('div'),saves=[];
  const find=id=>box.children.find(n=>n.id===id);
  const mount=()=>ctx.ui.mount(draft,box,()=>saves.push(1));
  const confirm=async()=>{mount();find('motivation-level').value='1';find('motivation-level').events.change();await find('confirmMotivation').events.click();await sleep();};
  return {ctx,draft,box,find,mount,confirm,reviews,fetched,mounted};
}

(async()=>{
  // A workout with no plan still gets the weekly coaching call for the microcycle just finished.
  let s=scenario({offer:{plan_id:'done-plan',name:'Push and pull'}});
  await s.confirm();
  assert.deepEqual(s.reviews,['call:done-plan']);
  assert.equal(s.draft.closing_review_id,'conversation-call');
  const closing=s.find('microcycleClosingReview');
  assert.match(text(closing),/Weekly coaching call · complete/);
  assert.match(text(closing),/call review text/);
  assert.match(text(closing),/Your plan changes only if you tap Accept or Run it back/);
  assert.ok(closing.children.some(n=>n.tag==='a'&&n.href==='/?coaching_conversation=conversation-call'));
  // Mounting again in the same page load never asks again.
  s.mount();await sleep();assert.deepEqual(s.reviews,['call:done-plan']);

  // Day 1 of the next plan: one call, no separate look-ahead review any more.
  s=scenario({offer:{plan_id:'done-plan'},eligible:true,planned:true});
  await s.confirm();
  assert.deepEqual(s.reviews,['call:done-plan']);
  assert.equal(s.draft.weekly_review_id,undefined);
  assert.equal(s.find('weeklyOpeningReview'),undefined);

  // Nothing finished: no AI traffic, even on day 1 of a plan.
  s=scenario({eligible:true,planned:true});
  await s.confirm();
  assert.deepEqual(s.reviews,[]);
  assert.equal(s.draft.closing_review_id,undefined);
  assert.equal(text(s.find('microcycleClosingReview')).trim(),'');
  s=scenario({});
  await s.confirm();
  assert.deepEqual(s.reviews,[]);

  // With the cards loaded, machine blocks are hidden and the cards get this microcycle's call context.
  s=scenario({offer:{plan_id:'done-plan'},cards:true});
  await s.confirm();
  assert.ok(!text(s.find('microcycleClosingReview')).includes('PROPOSAL'));
  assert.match(text(s.find('microcycleClosingReview')),/\[card\]/);
  const proposal=s.mounted.find(m=>m[0]==='proposal');
  assert.deepEqual(JSON.parse(JSON.stringify(proposal[1])),{text:'call review text PROPOSAL',conversationId:'conversation-call',turnId:'turn-1'});
  assert.deepEqual(JSON.parse(JSON.stringify(proposal[2])),{call:{sourcePlanId:'done-plan'}});
  assert.ok(s.mounted.some(m=>m[0]==='change'));

  // A failed call never blocks the check-in and is never resent.
  s=scenario({offer:{plan_id:'done-plan'},eligible:true,planned:true,reviewWeek:async()=>{throw Error('AI unavailable.');}});
  await s.confirm();
  assert.ok(s.ctx.ui.ready(s.draft));
  assert.match(text(s.find('microcycleClosingReview')),/AI unavailable\. Logging can continue; no automatic resend\./);
  s.mount();await sleep();assert.deepEqual(s.reviews,['call:done-plan']);

  // Once training has started the call is not run now; an already-created one is only shown.
  s=scenario({offer:{plan_id:'done-plan'}});
  s.draft.exercises[0].sets[0].done=true;s.draft.exercises[0].trialStarted=true;
  await s.confirm();
  assert.deepEqual(s.reviews,[]);
  assert.match(text(s.find('microcycleClosingReview')),/Training has started, so the weekly coaching call did not start automatically/);
  s=scenario({offer:{plan_id:'done-plan'}});
  s.draft.exercises[0].sets[0].done=true;s.draft.exercises[0].trialStarted=true;s.draft.closing_review_id='conversation-call';
  await s.confirm();
  assert.deepEqual(s.reviews,[]);assert.deepEqual(s.fetched,['/api/ai/conversations/conversation-call']);
  assert.match(text(s.find('microcycleClosingReview')),/saved/);

  // After a reload the confirmed check-in is re-posted once and resumes the call.
  s=scenario({offer:{plan_id:'done-plan'}});
  s.draft.motivation={level:1,note:'',recorded_at:new Date().toISOString(),timing:'before_working_sets'};
  s.draft.checkin_confirmation={signature:JSON.stringify({motivation:s.draft.motivation,plan:null,start:s.draft.startedAt}),confirmed_at:new Date().toISOString()};
  s.mount();await sleep();
  assert.deepEqual(s.reviews,['call:done-plan']);
  s.mount();await sleep();assert.deepEqual(s.reviews,['call:done-plan']);

  // A frozen save never starts a call.
  s=scenario({offer:{plan_id:'done-plan'}});
  s.draft.frozenSave={};s.draft.motivation={level:1,note:'',recorded_at:new Date().toISOString(),timing:'before_working_sets'};
  await s.ctx.ui.ensureSaved(s.draft);s.mount();await sleep();
  assert.deepEqual(s.reviews,[]);
  console.log('Weekly coaching call at check-in: one call replacing both reviews, cards with call context, once per page load, never blocks logging or resends passed.');
})().catch(e=>{console.error(e);process.exitCode=1;});
