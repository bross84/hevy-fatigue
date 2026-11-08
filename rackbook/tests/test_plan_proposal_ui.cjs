const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../static/plan-proposal.js'),'utf8');
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
  vm.runInContext(source+';this.PlanProposal=PlanProposal;',ctx);
  return ctx.PlanProposal;
}
const preview=(overrides={})=>({title:'Deload week',rationale:'Sessions ran above target.',valid:true,issues:[],
  diff:{active_plan:{id:'p',name:'Current'},added:['Bench'],removed:['Row'],changed:[{title:'Squat',was:'3×5 @7',now:'1×3 @7 TS'}]},
  sessions:[{name:'Day 1',exercises:[{exercise_template_id:'sq',title:'Squat',summary:'3×5 @7',notes:'Smooth'}]}],...overrides});
const block='Intro\n```plan-proposal-v1\n{"version":"plan-proposal-v1"}\n```\nOutro';
const request={text:block,conversationId:'conv',turnId:'turn'};

(async()=>{
  const PlanProposal=load();
  // Stripping hides the machine block but leaves the discussion.
  assert.deepEqual({...PlanProposal.strip(block)},{text:'Intro\n\n\n*(Plan proposal shown below.)*\n\n\nOutro',found:true});
  assert.equal(PlanProposal.strip('Just talking').found,false);
  assert.equal(PlanProposal.strip(null).text,'');
  const streaming=PlanProposal.strip('Hello\n```plan-proposal-v1\n{"ver');
  assert.equal(streaming.found,true);assert.ok(!streaming.text.includes('{"ver'));
  assert.equal(PlanProposal.strip('```json\n{}\n```').found,false);

  // No proposal: no request, no card.
  assert.equal(await PlanProposal.mount(new Node('div'),{...request,text:'No block'}),null);
  assert.equal(calls.length,0);

  // A valid preview shows a card, never auto-saves, and saves only on click.
  responses={'/training/api/plan-proposals/preview':{json:preview({title:'<img src=x onerror=alert(1)>'})},
    '/training/api/plan-proposals/save':{json:{already_saved:false,plan:{id:'new'}}}};
  let host=new Node('div');
  let card=await PlanProposal.mount(host,request);
  assert.equal(host.children[0],card);
  assert.deepEqual(calls.map(c=>[c.url,c.method]),[['/training/api/plan-proposals/preview','POST']]);
  assert.deepEqual(calls[0].body,{text:block,conversation_id:'conv',turn_id:'turn'});
  const text=card.textContent;
  for(const expected of ['<img src=x onerror=alert(1)>','Sessions ran above target.','Not applied','inactive draft','Added: Bench','Removed: Row','Changed: Squat · was 3×5 @7 · now 1×3 @7 TS','Squat — 3×5 @7 (Smooth)','Compared with your active microcycle, Current'])
    assert.ok(text.includes(expected),expected);
  assert.equal(find(card,n=>n.tagName==='IMG'||n.tagName==='SCRIPT').length,0);
  const [save]=find(card,n=>n.tagName==='BUTTON');
  assert.equal(save.textContent,'Save as draft');
  assert.equal(calls.length,1);
  await save.click();
  assert.equal(calls.length,2);
  assert.deepEqual([calls[1].url,calls[1].method],['/training/api/plan-proposals/save','POST']);
  assert.equal(save.disabled,true);
  assert.ok(card.textContent.includes('Saved as an inactive draft.'));
  const [link]=find(card,n=>n.tagName==='A');
  assert.equal(link.href,'/training/microcycles');
  assert.ok(link.textContent.includes('review and activate'));

  // Repeat saves are reported honestly.
  responses['/training/api/plan-proposals/save']={json:{already_saved:true,plan:{id:'new'}}};
  card=await PlanProposal.mount(new Node('div'),request);
  await find(card,n=>n.tagName==='BUTTON')[0].click();
  assert.ok(card.textContent.includes('Already saved as an inactive draft.'));

  // Save failures re-enable the button and change nothing.
  responses['/training/api/plan-proposals/save']={ok:false,json:{detail:'No plan proposal was found in that reply.'}};
  card=await PlanProposal.mount(new Node('div'),request);
  const [retry]=find(card,n=>n.tagName==='BUTTON');
  await retry.click();
  assert.equal(retry.disabled,false);
  assert.ok(card.textContent.includes('No plan proposal was found in that reply. Nothing was changed.'));
  assert.equal(find(card,n=>n.tagName==='A').length,0);

  // Invalid proposals list the problems and offer no save.
  responses['/training/api/plan-proposals/preview']={json:{found:true,valid:false,issues:['Unknown movement id(s): made-up']}};
  card=await PlanProposal.mount(new Node('div'),request);
  assert.equal(find(card,n=>n.tagName==='BUTTON').length,0);
  assert.ok(card.textContent.includes('cannot be saved as written'));
  assert.ok(card.textContent.includes('Unknown movement id(s): made-up'));

  // A failed preview is explained without retry or writes.
  responses['/training/api/plan-proposals/preview']={ok:false,json:{detail:'Server unavailable.'}};
  const before=calls.length;
  card=await PlanProposal.mount(new Node('div'),request);
  assert.ok(card.textContent.includes('Server unavailable.'));
  assert.equal(calls.length,before+1);
  assert.equal(find(card,n=>n.tagName==='BUTTON').length,0);

  // Every request is a POST to one of two proposal paths: nothing edits, activates or deletes a plan.
  for(const call of calls) assert.ok(['/training/api/plan-proposals/preview','/training/api/plan-proposals/save'].includes(call.url)&&call.method==='POST');
  console.log('Plan proposal card: block stripping, text-only rendering, explicit save, idempotent and failed saves, invalid and failed previews passed.');
})().catch(e=>{console.error(e);process.exitCode=1;});
