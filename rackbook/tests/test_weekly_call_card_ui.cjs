// Proposal card inside a weekly coaching call (ADR 0002): local rendering only, fetch mocked.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../static/plan-proposal.js'),'utf8');

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
const ctx=vm.createContext({document:{createElement:tag=>new Node(tag)},trainingUrl:p=>'/training'+p,
  fetch:async(url,options)=>{
    calls.push({url,method:options.method,body:JSON.parse(options.body)});
    const next=responses[url];const value=typeof next==='function'?next():next;
    return {ok:value.ok!==false,json:async()=>value.json};
  }});
vm.runInContext(source+';this.PlanProposal=PlanProposal;',ctx);
const PlanProposal=ctx.PlanProposal;

const base={found:true,valid:true,issues:[],title:'Same again',rationale:'Day 2 ran hot.',
  diff:{active_plan:null,added:[],removed:[],changed:[]},sessions:[{name:'Squat day',exercises:[{title:'Squat',summary:'3×5 @7',notes:''}]}]};
const call=(overrides={})=>({...base,call:{matches:true,this_turn:false,next_name:'BS2.4',next:null,
  source:{id:'src',name:'BS2.3',finished:true},call_id:'conv',proposal_id:'p1',...overrides}});
const set={plan_id:'new plan',name:'BS2.4',origin:'coach',proposal_id:'p1',can_undo:true,undo_problem:null};
const request={text:'```plan-proposal-v1\n{}\n```',conversationId:'conv',turnId:'turn'};
const PREVIEW='/training/api/weekly-call/src/preview',ACCEPT='/training/api/weekly-call/src/next-week',UNDO='/training/api/weekly-call/src/undo';

(async()=>{
  // In the call, the card offers Accept as next week (not Save as draft) and previews through the call route.
  let changes=0;
  responses={[PREVIEW]:{json:call()},[ACCEPT]:{json:{already_applied:false}}};
  let card=await PlanProposal.mount(new Node('div'),request,{call:{sourcePlanId:'src'},onChange:()=>changes++});
  assert.deepEqual(calls.map(c=>c.url),[PREVIEW]);
  assert.deepEqual(calls[0].body,{text:request.text,conversation_id:'conv',turn_id:'turn'});
  for(const expected of ['Day 2 ran hot.','Accept makes this your active microcycle, BS2.4','undo it until you train its first day','Squat — 3×5 @7'])
    assert.ok(card.textContent.includes(expected),expected);
  assert.deepEqual(buttons(card).map(b=>b.textContent),['Accept as next week']);
  assert.equal(calls.length,1,'Previewing never sets anything up');

  // Accept sets up next week, then the card shows it with Undo and a builder link.
  responses[PREVIEW]={json:call({this_turn:true,next:set})};
  await buttons(card)[0].click();
  assert.deepEqual(calls.slice(1).map(c=>[c.url,c.method]),[[ACCEPT,'POST'],[PREVIEW,'POST']]);
  assert.equal(changes,1);
  assert.ok(card.textContent.includes('BS2.4 is your active microcycle, set up from this proposal.'));
  assert.equal(find(card,n=>n.tagName==='A')[0].href,'/training/microcycles?plan=new%20plan');

  // Undo takes it back and the card offers Accept again.
  responses[UNDO]={json:{call:{}}};responses[PREVIEW]={json:call()};
  await buttons(card)[0].click();
  assert.equal(calls.at(-2).url,UNDO);
  assert.equal(changes,2);
  assert.deepEqual(buttons(card).map(b=>b.textContent),['Accept as next week']);

  // A failed accept changes nothing and can be retried.
  responses[ACCEPT]={ok:false,json:{detail:'Next week is already set up for that microcycle.'}};
  await buttons(card)[0].click();
  assert.ok(card.textContent.includes('already set up for that microcycle. Nothing was changed.'));
  assert.equal(buttons(card)[0].disabled,false);

  // Next week set up another way (Run it back): no Accept, but Undo while it is untouched.
  responses[PREVIEW]={json:call({next:{...set,origin:'repeat',proposal_id:null}})};
  card=await PlanProposal.mount(new Node('div'),request,{call:{sourcePlanId:'src'}});
  assert.ok(card.textContent.includes('Next week is already set up with Run it back: BS2.4.'));
  assert.deepEqual(buttons(card).map(b=>b.textContent),['Undo']);
  responses[PREVIEW]={json:call({this_turn:true,next:{...set,can_undo:false,undo_problem:'A day of the next week has been trained or skipped, so it cannot be undone here.'}})};
  card=await PlanProposal.mount(new Node('div'),request,{call:{sourcePlanId:'src'}});
  assert.equal(buttons(card).length,0);
  assert.ok(card.textContent.includes('cannot be undone here'));

  // A reply from a different conversation falls back to the ordinary draft card.
  responses[PREVIEW]={json:call({matches:false})};
  card=await PlanProposal.mount(new Node('div'),request,{call:{sourcePlanId:'src'}});
  assert.deepEqual(buttons(card).map(b=>b.textContent),['Save as draft']);

  // Invalid proposals list problems and offer nothing.
  responses[PREVIEW]={json:{found:true,valid:false,issues:['Unknown movement id(s): ghost'],call:call().call}};
  card=await PlanProposal.mount(new Node('div'),request,{call:{sourcePlanId:'src'}});
  assert.equal(buttons(card).length,0);
  assert.ok(card.textContent.includes('Unknown movement id(s): ghost'));

  // Plain text for pages without Markdown: machine blocks and their placeholders are gone.
  assert.equal(PlanProposal.plain('Good week.\n```plan-proposal-v1\n{}\n```\nAccept it.'),'Good week.\n\nAccept it.');
  assert.equal(PlanProposal.plain('Hold.\n```plan-proposal-v1\n{"ver'),'Hold.');

  for(const c of calls)assert.ok([PREVIEW,ACCEPT,UNDO].includes(c.url)&&c.method==='POST',c.url);
  console.log('Weekly call card: Accept as next week only on tap, undo, other set-ups, wrong conversation, invalid and failed accepts passed.');
})().catch(e=>{console.error(e);process.exitCode=1;});
