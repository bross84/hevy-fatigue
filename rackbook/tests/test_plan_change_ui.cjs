// AI Coach plan change card (ADR 0002): local rendering only, fetch mocked; no browser, network or Hevy.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../static/plan-change.js'),'utf8');
assert.ok(!/innerHTML|outerHTML|insertAdjacentHTML|document\.write/.test(source),'AI text must only be set as text');

class Node{
  constructor(tag){this.tagName=tag.toUpperCase();this.children=[];this.className='';this._text='';this.listeners={};this.disabled=false;}
  set textContent(value){this._text=String(value);this.children=[];}
  get textContent(){return this._text+this.children.map(child=>child.textContent).join('');}
  append(...nodes){this.children.push(...nodes);}
  replaceChildren(){this.children=[];this._text='';}
  addEventListener(name,handler){this.listeners[name]=handler;}
  click(){return this.listeners.click();}
}
const all=node=>[node,...node.children.flatMap(all)];
const find=(node,predicate)=>all(node).filter(predicate);
const buttons=card=>find(card,n=>n.tagName==='BUTTON');

let calls=[],responses={};
function load(){
  calls=[];
  const ctx=vm.createContext({document:{createElement:tag=>new Node(tag)},trainingUrl:p=>'/training'+p,
    fetch:async(url,options)=>{
      calls.push({url,method:options.method,body:JSON.parse(options.body)});
      const next=responses[url];
      const value=typeof next==='function'?next():next;
      return {ok:value.ok!==false,json:async()=>value.json};
    }});
  vm.runInContext(source+';this.PlanChange=PlanChange;',ctx);
  return ctx.PlanChange;
}
const plan={id:'plan 1',name:'Block 1.2',active:true,revision:3};
const days=[{day:2,name:'Day 2',changes:['Romanian Deadlift: 3×8 @7 → 2×8 @7','Swap Row → Chest Supported Row: 3×10 @8']}];
const pending=(overrides={})=>({found:true,valid:true,stale:false,issues:[],status:'pending',change_id:'chg',
  title:'Ease day 2',rationale:'RDL ran above target.',plan,days,...overrides});
const applied=(overrides={})=>pending({status:'applied',can_undo:true,undo_problem:null,applied_at:'2026-11-09T10:00:00Z',...overrides});
const block='Intro\n```plan-change-v1\n{"version":"plan-change-v1"}\n```\nOutro';
const request={text:block,conversationId:'conv',turnId:'turn'};
const PREVIEW='/training/api/plan-changes/preview',ACCEPT='/training/api/plan-changes/accept',UNDO='/training/api/plan-changes/chg/undo';

(async()=>{
  const PlanChange=load();
  // Stripping hides the machine block but leaves the discussion, including while it streams.
  assert.deepEqual({...PlanChange.strip(block)},{text:'Intro\n\n\n*(Suggested plan change shown below.)*\n\n\nOutro',found:true});
  assert.equal(PlanChange.strip('Hold the plan as it is.').found,false);
  assert.equal(PlanChange.strip('```plan-proposal-v1\n{}\n```').found,false);
  const streaming=PlanChange.strip('Hello\n```plan-change-v1\n{"ver');
  assert.equal(streaming.found,true);assert.ok(!streaming.text.includes('{"ver'));

  // No change block: no request and no card.
  assert.equal(await PlanChange.mount(new Node('div'),{...request,text:'No block'}),null);
  assert.equal(calls.length,0);

  // A valid change is described day by day and applies only on the Accept tap.
  responses={[PREVIEW]:{json:pending({title:'<img src=x onerror=alert(1)>'})},[ACCEPT]:{json:{already_applied:false,change:applied(),plan}}};
  const host=new Node('div');
  let card=await PlanChange.mount(host,request);
  assert.equal(host.children[0],card);
  assert.deepEqual(calls.map(c=>[c.url,c.method]),[[PREVIEW,'POST']]);
  assert.deepEqual(calls[0].body,{text:block,conversation_id:'conv',turn_id:'turn'});
  for(const expected of ['<img src=x onerror=alert(1)>','RDL ran above target.','For Block 1.2 (your active microcycle)','Day 2 · Day 2',
    'Romanian Deadlift: 3×8 @7 → 2×8 @7','Swap Row → Chest Supported Row','Nothing changes until you tap Accept','undo it afterwards'])
    assert.ok(card.textContent.includes(expected),expected);
  assert.equal(find(card,n=>n.tagName==='IMG'||n.tagName==='SCRIPT').length,0);
  const [accept]=buttons(card);
  assert.equal(accept.textContent,'Accept change');
  assert.equal(calls.length,1,'Previewing never applies');
  await accept.click();
  assert.deepEqual([calls[1].url,calls[1].method],[ACCEPT,'POST']);
  assert.deepEqual(calls[1].body,calls[0].body);
  assert.ok(card.textContent.includes('Applied to Block 1.2.'));
  const [link]=find(card,n=>n.tagName==='A');
  assert.equal(link.href,'/training/microcycles?plan=plan%201');
  const [undo]=buttons(card);
  assert.equal(undo.textContent,'Undo');

  // Undo restores the previous plan; failures say nothing changed and allow another try.
  responses[UNDO]={ok:false,json:{detail:'A changed day has been trained or skipped since, so this change cannot be undone.'}};
  await undo.click();
  assert.equal(undo.disabled,false);
  assert.ok(card.textContent.includes('cannot be undone. The plan was not changed.'));
  responses[UNDO]={json:{change:applied({status:'undone',can_undo:false,undone_at:'2026-11-09T11:00:00Z'}),plan}};
  await undo.click();
  assert.deepEqual([calls.at(-1).url,calls.at(-1).method],[UNDO,'POST']);
  assert.ok(card.textContent.includes('Undone. The plan is back to how it was'));
  assert.equal(buttons(card).length,0);

  // Reloading a saved review shows what happened instead of offering Accept again.
  responses[PREVIEW]={json:applied()};
  card=await PlanChange.mount(new Node('div'),request);
  assert.deepEqual(buttons(card).map(b=>b.textContent),['Undo']);
  responses[PREVIEW]={json:applied({can_undo:false,undo_problem:'The plan was edited after this change, so it cannot be undone here.'})};
  card=await PlanChange.mount(new Node('div'),request);
  assert.equal(buttons(card).length,0);
  assert.ok(card.textContent.includes('edited after this change'));
  responses[PREVIEW]={json:applied({status:'undone',can_undo:false})};
  card=await PlanChange.mount(new Node('div'),request);
  assert.equal(buttons(card).length,0);
  assert.ok(card.textContent.includes('Undone.'));

  // A refused accept (for example a stale plan) keeps Accept available and says nothing changed.
  responses[PREVIEW]={json:pending()};
  responses[ACCEPT]={ok:false,json:{detail:'This change cannot be applied: This plan has been edited since the coach wrote this change.'}};
  card=await PlanChange.mount(new Node('div'),request);
  const [retry]=buttons(card);
  await retry.click();
  assert.equal(retry.disabled,false);
  assert.ok(card.textContent.includes('edited since the coach wrote this change. Nothing was changed.'));
  assert.equal(find(card,n=>n.tagName==='A').length,0);

  // Invalid changes list the problems and offer no Accept.
  responses[PREVIEW]={json:{found:true,valid:false,stale:true,issues:['This plan has been edited since the coach wrote this change.'],status:'pending',plan}};
  card=await PlanChange.mount(new Node('div'),request);
  assert.equal(buttons(card).length,0);
  assert.ok(card.textContent.includes('cannot be applied as written'));

  // A failed preview is explained, with no retry or writes.
  responses[PREVIEW]={ok:false,json:{detail:'Server unavailable.'}};
  const before=calls.length;
  card=await PlanChange.mount(new Node('div'),request);
  assert.ok(card.textContent.includes('Server unavailable.'));
  assert.equal(calls.length,before+1);
  assert.equal(buttons(card).length,0);

  // Every request is a POST to the three plan-change paths: nothing activates, deletes or edits plans another way.
  for(const call of calls) assert.ok([PREVIEW,ACCEPT,UNDO].includes(call.url)&&call.method==='POST',call.url);
  console.log('Plan change card: block stripping, text-only rendering, Accept only on tap, undo and its refusals, reload states, stale and invalid changes passed.');
})().catch(e=>{console.error(e);process.exitCode=1;});
