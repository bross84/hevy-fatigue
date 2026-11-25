const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const html=fs.readFileSync(path.join(__dirname,'../log.html'),'utf8');
const ctx=vm.createContext({LB_PER_KG:2.20462262185,lbOfKg:kg=>kg*2.20462262185,unitFor:ref=>ref.weightUnit||'kg',unit:'kg',num:Number,trim:String,el(){}});
vm.runInContext(html.slice(html.indexOf('  const PLATES_KG ='),html.indexOf('  function fillLoader(')),ctx);
vm.runInContext(html.slice(html.indexOf('  function plateLine('),html.indexOf('  function paintPlates(')),ctx);
for(const weightUnit of ['kg','lb']) {
  const ex={ref:{weightUnit,barKg:20,chainKg:0},sets:[{kg:'100',type:'normal'}]};
  const before=JSON.stringify(ex),line=ctx.plateLine(ex,0);
  assert.match(line.set,/100 kg · 220 lb/);assert.equal(line.short,'');
  assert.equal(JSON.stringify(ex),before,'Display cannot mutate canonical weights');
  assert.deepEqual(JSON.parse(JSON.stringify(line.plan.counts)),[[25,1],[15,1]]);
  ex.ref.barKg=0;ex.sets[0].kg='25';
  const noBar=ctx.plateLine(ex,0);assert.match(noBar.set,/25 kg · 55 lb/);assert.equal(noBar.short,'');
  ex.ref.barKg=30;ex.ref.chainKg=10;ex.sets[0].kg='100';
  assert.deepEqual(JSON.parse(JSON.stringify(ctx.plateLine(ex,0).plan.counts)),[[25,1],[5,1]]);
  assert.ok(ctx.platePlan(100.1,ex).short>0,'A genuinely unloadable kg target reports a remainder');
}
// Use the repository's actual table, not a replacement percentage, to trace the reported doubles.
const lines=fs.readFileSync(path.join(__dirname,'../data/rpe_chart_user.csv'),'utf8').trim().split(/\r?\n/);
const head=lines.shift().split(','),table=new Map(lines.map(line=>{const row=Object.fromEntries(line.split(',').map((v,i)=>[head[i],v]));return [Number(row.rpe)+'|'+Number(row.reps),Number(row.percentage)];}));
const weightCtx=vm.createContext({LB_PER_KG:2.20462262185,unit:'lb',rpeTable:table,showWeight(){}});
// Load real lookup, conversion and rounding code as well as source selection.
vm.runInContext(html.slice(html.indexOf('  function pctFor('),html.indexOf('  const primaryText =')),weightCtx);
vm.runInContext(html.slice(html.indexOf('  function setE1rm('),html.indexOf('  function refreshCard(')),weightCtx);
const ex={ref:{basis:'e1rm',ls:true,tmPct:.95,stepKg:2.5,stepLb:5,weightUnit:'lb',state:{found:true,workout_start_time:new Date(Date.now()-86400000).toISOString(),e1rm_lb:240}},sets:[{type:'normal',kg:'',reps:'2',rpe:'8',done:false}]};
assert.equal(weightCtx.baseFor(ex,0),240);
const pounds=()=>weightCtx.autoWeight(ex,ex.sets.length-1)*2.20462262185;
assert.ok(Number.isFinite(weightCtx.autoWeight(ex,0)) && weightCtx.autoWeight(ex,0)>0,'A missing lookup must not pass as a zero-pound recommendation');
assert.equal(pounds(),215,'240 e1RM with doubles @8 rounds to 215 lb');
ex.sets[0].rpe='10';assert.equal(pounds(),230,'Even doubles @10 stay below 240 with normal increments');ex.sets[0].rpe='8';
ex.ref.weightUnit='kg';assert.equal(weightCtx.autoWeight(ex,0),97.5);ex.ref.weightUnit='lb';
ex.ref.ts={found:true,set_at:new Date(Date.now()-86400000).toISOString(),e1rm_lb:275};assert.equal(pounds(),250,'A saved 275 lb TS can produce the reported load despite a 240 lb history reference');
ex.ref.ts=null;
ex.sets.unshift({type:'normal',kg:String(235/2.20462262185),reps:'2',rpe:'8',arpe:'6',done:true});
assert.equal(pounds(),250,'Earlier 235 lb doubles logged @6 can drive the next doubles @8 through LSe1RM');
ex.sets.shift();
ex.ref.ts={found:true,set_at:new Date(Date.now()-86400000).toISOString(),e1rm_lb:300};assert.equal(weightCtx.baseFor(ex,0),300,'Saved TS can explain a different basis');
ex.sets[0].manual=true;ex.sets[0].kg='113.3980925';weightCtx.applyAuto(ex);assert.equal(ex.sets[0].kg,'113.3980925','Manual 250 lb is preserved rather than recalculated');
console.log('Exact kg, whole-pound references, equipment isolation, shortages and load-source trace passed.');
