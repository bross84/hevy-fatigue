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
      if(v.turns.length!==JSON.parse(options.body).expected_sequence)return {ok:false,status:409};
      v.turns.push({status:fail?'interrupted':'complete',response:'<img src=x onerror=bad()> Tired but recovered.',model:'test/budget-model'});
      const chunks=fail?['data: {"error":{"message":"Mock interruption"}}\n\n']:['data: [DO','NE]\n\n'];let index=0;
      return {ok:true,status:200,body:{getReader:()=>({read:async()=>index<chunks.length?{done:false,value:Buffer.from(chunks[index++])}:{done:true}})}};
    }
    return ok(structuredClone(views.get(url.split('/').pop())));
  }});
vm.runInContext(fs.readFileSync('rackbook/static/weekly-coach.js','utf8')+';this.weekly=WeeklyCoach;',context);
vm.runInContext(fs.readFileSync('static/daily-coach.js','utf8')+';this.daily=DailyCoach;',context);
const tick=()=>new Promise(resolve=>setImmediate(resolve));
const text=()=>box.children.map(e=>e.textContent).join('\n');
(async()=>{
  const firstMount=context.daily.mount('2026-11-06');
  assert.equal(box.children.some(e=>e.tagName==='button'),false,'no action during initial lookup');
  await Promise.all([firstMount,context.daily.mount('2026-11-06')]);
  await Promise.all([context.daily.run('2026-11-06'),context.daily.run('2026-11-06')]);
  assert.equal(calls.filter(c=>c.url.endsWith('/messages')).length,1,'same ratings cannot be billed twice');
  const sent=calls.find(c=>c.url.endsWith('/messages')).body;
  assert.equal(sent.model,'test/budget-model');assert.equal(sent.expected_sequence,0);
  assert.ok(text().includes('<img src=x onerror=bad()>'),'provider text is rendered literally');
  assert.equal(box.children.filter(e=>e.tagName==='img').length,0);
  assert.ok(box.children.find(e=>e.tagName==='a').href.includes('coaching_conversation=one'));
  context.daily.mount('2026-11-06');await tick();
  assert.equal(calls.filter(c=>c.url.endsWith('/messages')).length,1);
  revision='two';fail=true;await context.daily.run('2026-11-06');
  assert.ok(text().includes('Mock interruption'));assert.ok(text().includes('interrupted'));
  await context.daily.run('2026-11-06');
  assert.equal(calls.filter(c=>c.url.endsWith('/messages')).length,2,'uncertain/partial attempts cannot be resent automatically');
  await context.daily.mount('2026-11-06');
  fail=false;
  await box.children.find(e=>e.textContent==='Retry').listeners.click();
  assert.equal(calls.filter(c=>c.url.endsWith('/messages')).length,3);
  assert.equal(calls.filter(c=>c.url.endsWith('/messages')).at(-1).body.expected_sequence,1);
  assert.ok(text().includes('Saved interpretation.'));
  assert.equal(box.children.some(e=>e.tagName==='button'),false,'success has no Retry');
  revision='three';configured=false;await context.daily.run('2026-11-06');
  assert.ok(text().includes('Check-in saved. Configure AI'));
  assert.equal(calls.filter(c=>c.url.endsWith('/messages')).length,3);
  const settingsChecks=calls.filter(c=>c.url==='/api/settings/ai').length;
  await context.daily.mount('2026-11-06');
  assert.equal(calls.filter(c=>c.url==='/api/settings/ai').length,settingsChecks);
  assert.ok(box.children.some(e=>e.textContent==='Retry'),'setup failure remains retryable on reload');
  revision='pending';
  view();views.get(revision).turns=[{status:'pending',model:'test/budget-model'}];
  await context.daily.mount('2026-11-06');
  assert.equal(box.children.some(e=>e.tagName==='button'),false,'pending responses cannot be retried');
  context.daily.clear('2026-11-06');assert.equal(box.hidden,true);
  console.log('Daily Coach: restore without billing, duplicate protection, selected model, literal text, saved links, revisions, AI outage and deletion passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
