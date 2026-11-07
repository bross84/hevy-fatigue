const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
let turns=[],configured=true,interrupted=false;const calls=[];
const view=()=>({id:'review',turns:structuredClone(turns)});
const ctx=vm.createContext({TextDecoder,localStorage:{getItem:()=> 'test/value-model'},crypto:{randomUUID:()=> 'message-id'},
  fetch:async(url,options)=>{
    calls.push({url,body:options?.body?JSON.parse(options.body):null});
    if(url==='/api/ai/week-reviews')return {ok:true,json:async()=>view()};
    if(url==='/api/settings/ai')return {ok:true,json:async()=>({configured,default_model:'test/default'})};
    if(url.endsWith('/messages')){
      turns=[{status:interrupted?'pending':'complete',response:interrupted?null:'Keep the plan.'}];
      const chunks=interrupted?['data: {"choices":[]}\n\n']:['data: {"choices":[]}\n\ndata: [DO','NE]\n\n'];let index=0;
      return {ok:true,status:200,body:{getReader:()=>({read:async()=>index<chunks.length?{done:false,value:Buffer.from(chunks[index++])}:{done:true}})}};
    }
    return {ok:true,json:async()=>view()};
  }});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../static/ai-coach.js'),'utf8')+';this.weekly=AICoach;',ctx);
(async()=>{
  const first=await ctx.weekly.reviewWeek('plan','start','session');assert.equal(first.turns[0].status,'complete');
  assert.equal(calls.find(c=>c.url.endsWith('/messages')).body.model,'test/value-model');
  assert.equal(calls.filter(c=>c.url.endsWith('/messages')).length,1);
  await ctx.weekly.reviewWeek('plan','start','session');assert.equal(calls.filter(c=>c.url.endsWith('/messages')).length,1);
  turns=[];interrupted=true;
  await assert.rejects(()=>ctx.weekly.reviewWeek('plan2','start','session2'),/interrupted/);
  await ctx.weekly.reviewWeek('plan2','start','session2');assert.equal(calls.filter(c=>c.url.endsWith('/messages')).length,2);
  turns=[];configured=false;
  await assert.rejects(()=>ctx.weekly.reviewWeek('plan3','start','session3'),/Configure AI/);
  assert.equal(calls.filter(c=>c.url.endsWith('/messages')).length,2);
  assert.equal(ctx.weekly.endUrl('a/b'),'/?coaching_week=a%2Fb&coaching_kind=end#ai');
  console.log('Weekly Coach: selected model, split stream, cached/uncertain no resend, missing settings and safe navigation passed.');
})().catch(e=>{console.error(e);process.exitCode=1;});
