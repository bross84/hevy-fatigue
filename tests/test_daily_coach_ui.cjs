const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
class Element{
  constructor(tag){this.tagName=tag;this.children=[];this.style={};this.textContent='';this.hidden=false;this.listeners={};}
  append(child){this.children.push(child);}
  replaceChildren(){this.children=[];}
  setAttribute(){}
  addEventListener(name,callback){this.listeners[name]=callback;}
}
const box=new Element('section'),calls=[];
let configured=true,revision='one',fail=false;
const views=new Map(),storage=new Map();
function view(){if(!views.has(revision))views.set(revision,{id:revision,created_at:'2026-11-06T12:00:00Z',turns:[]});return structuredClone(views.get(revision));}
const context=vm.createContext({TextDecoder,Date,crypto:{randomUUID:()=>Math.random().toString()},localStorage:{getItem:key=>key==='ai_preferred_model'?'test/budget-model':storage.get(key),setItem:(key,value)=>storage.set(key,value),removeItem:key=>storage.delete(key)},
  document:{getElementById:()=>box,createElement:tag=>new Element(tag)},
  fetch:async(url,options)=>{
    calls.push({url,method:options?.method||'GET',body:options?.body?JSON.parse(options.body):null});
    const ok=data=>({ok:true,status:200,json:async()=>data});
    if(url==='/api/ai/daily-reviews')return ok(view());
    if(url.startsWith('/api/ai/daily-reviews/'))return ok(views.has(revision)?view():null);
    if(url==='/api/settings/ai')return ok({configured,default_model:'test/default'});
    if(url.endsWith('/messages')){
      const id=url.split('/')[4],v=views.get(id);
      const request=JSON.parse(options.body);
      if(v.turns.length!==request.expected_sequence)return {ok:false,status:409};
      if(request.retry_pending_turn_id){
        assert.equal(v.retry_pending_turn_id,request.retry_pending_turn_id);
        v.turns.at(-1).status='interrupted';
        delete v.retry_pending_turn_id;
      }
      v.turns.push({status:fail?'interrupted':'complete',response:'<img src=x onerror=bad()> Tired but recovered.',model:'test/budget-model'});
      if(!fail)v.daily_recommendation={label:'Continue as planned',reason:'<img src=x onerror=bad()> Tired but recovered.'};
      const chunks=fail?['data: {"error":{"message":"Mock interruption"}}\n\n']:['data: [DO','NE]\n\n'];let index=0;
      return {ok:true,status:200,body:{getReader:()=>({read:async()=>index<chunks.length?{done:false,value:Buffer.from(chunks[index++])}:{done:true}})}};
    }
    return ok(structuredClone(views.get(url.split('/').pop())));
  }});
vm.runInContext(fs.readFileSync('rackbook/static/ai-coach.js','utf8')+';this.weekly=AICoach;',context);
vm.runInContext(fs.readFileSync('static/daily-coach.js','utf8')+';this.daily=DailyCoach;',context);
const tick=()=>new Promise(resolve=>setImmediate(resolve));
const textOf=element=>[element.textContent,...element.children.map(textOf)].join('\n');
const text=()=>textOf(box);
const controls=()=>box.children.flatMap(element=>[element,...element.children]);
(async()=>{
  const firstMount=context.daily.mount('2026-11-06');
  assert.equal(controls().some(e=>e.tagName==='button'),false,'no action during initial lookup');
  await Promise.all([firstMount,context.daily.mount('2026-11-06')]);
  await Promise.all([context.daily.run('2026-11-06'),context.daily.run('2026-11-06')]);
  assert.equal(calls.filter(c=>c.url.endsWith('/messages')).length,1,'same ratings cannot be billed twice');
  const sent=calls.find(c=>c.url.endsWith('/messages')).body;
  assert.equal(sent.model,'test/budget-model');assert.equal(sent.expected_sequence,0);
  assert.ok(text().includes('<img src=x onerror=bad()>'),'provider text is rendered literally');
  assert.ok(text().includes('Continue as planned'));
  assert.ok(!text().includes('Evidence saved'));
  assert.equal(controls().filter(e=>e.tagName==='img').length,0);
  assert.ok(box.children.find(e=>e.tagName==='a').href.includes('coaching_conversation=one'));
  context.daily.mount('2026-11-06');await tick();
  assert.equal(calls.filter(c=>c.url.endsWith('/messages')).length,1);
  revision='two';fail=true;await context.daily.run('2026-11-06');
  assert.ok(text().includes('Mock interruption'));
  await context.daily.run('2026-11-06');
  assert.equal(calls.filter(c=>c.url.endsWith('/messages')).length,2,'uncertain/partial attempts cannot be resent automatically');
  await context.daily.mount('2026-11-06');
  fail=false;
  await controls().find(e=>e.textContent==='Retry').listeners.click();
  assert.equal(calls.filter(c=>c.url.endsWith('/messages')).length,3);
  assert.equal(calls.filter(c=>c.url.endsWith('/messages')).at(-1).body.expected_sequence,1);
  assert.ok(text().includes('Continue as planned'));
  assert.equal(controls().some(e=>e.tagName==='button'),false,'success has no Retry');
  revision='three';configured=false;await context.daily.run('2026-11-06');
  assert.ok(text().includes('Check-in saved. Configure AI'));
  assert.equal(calls.filter(c=>c.url.endsWith('/messages')).length,3);
  const settingsChecks=calls.filter(c=>c.url==='/api/settings/ai').length;
  await context.daily.mount('2026-11-06');
  assert.equal(calls.filter(c=>c.url==='/api/settings/ai').length,settingsChecks);
  assert.ok(controls().some(e=>e.textContent==='Retry'),'setup failure remains retryable on reload');
  revision='pending';
  view();views.get(revision).turns=[{id:'old-turn',status:'pending',model:'test/budget-model'}];
  await context.daily.mount('2026-11-06');
  assert.equal(controls().some(e=>e.tagName==='button'),false,'pending responses cannot be retried');
  views.get(revision).retry_pending_turn_id='old-turn';
  configured=true;
  await context.daily.mount('2026-11-06');
  assert.equal(calls.filter(c=>c.url.endsWith('/messages')).length,3,'stale pending is never automatically retried');
  await controls().find(e=>e.textContent==='Retry').listeners.click();
  const retried=calls.filter(c=>c.url.endsWith('/messages')).at(-1).body;
  assert.equal(retried.retry_pending_turn_id,'old-turn');
  assert.equal(retried.expected_sequence,1);
  assert.ok(text().includes('Continue as planned'));
  const failedView=(id,failure)=>views.set(id,{id,created_at:'2026-11-06T12:00:00Z',turns:[{id:'t-'+id,status:'failed',model:'test/budget-model',...(failure?{failure}:{})}]});
  revision='reason';failedView(revision,'The reason was 301 characters; the limit is 300.');
  await context.daily.mount('2026-11-06');
  assert.ok(text().includes('Response failed. The reason was 301 characters; the limit is 300. You can retry the interpretation.'),'a saved failure reason is shown');
  assert.ok(controls().some(e=>e.textContent==='Retry'),'a failed response stays retryable');
  revision='markup';failedView(revision,'<img src=x onerror=bad()> Provider said no.');
  await context.daily.mount('2026-11-06');
  assert.ok(text().includes('<img src=x onerror=bad()> Provider said no.'),'a failure reason is rendered literally');
  assert.equal(controls().filter(e=>e.tagName==='img').length,0);
  revision='older';failedView(revision,null);
  await context.daily.mount('2026-11-06');
  assert.ok(text().includes('Response failed. You can retry the interpretation.'),'a turn saved before reasons existed keeps the plain message');
  context.daily.clear('2026-11-06');assert.equal(box.hidden,true);
  console.log('Daily Coach: restore without billing, duplicate protection, selected model, literal text, saved links, revisions, AI outage and deletion passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
