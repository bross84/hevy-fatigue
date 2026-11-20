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
const head=lines.shift().split(','),table=new Map(lines.map(line=>{const row=Object.fromEntries(line.split(',').map((v,i)=>[head[i],v]));return [row.rpe+'|'+row.reps,Number(row.percentage)];}));
const weightCtx=vm.createContext({num:Number,lbOfKg:kg=>kg*2.20462262185,pctFor:(r,n)=>table.get(r+'|'+n),plannedKg:(lb,ref)=>Math.round(lb/2.20462262185/ref.stepKg)*ref.stepKg,showWeight(){}});
vm.runInContext(html.slice(html.indexOf('  function setE1rm('),html.indexOf('  function refreshCard(')),weightCtx);
const ex={ref:{basis:'e1rm',ls:true,tmPct:.95,stepKg:2.5,state:{found:true,e1rm_lb:240}},sets:[{type:'normal',kg:'',reps:'2',rpe:'8',done:false}]};
assert.equal(weightCtx.baseFor(ex,0),240);
assert.ok(weightCtx.autoWeight(ex,0)*2.20462262185<240,'240 e1RM with doubles @8 does not prescribe 250 lb');
ex.ref.ts={found:true,e1rm_lb:300};assert.equal(weightCtx.baseFor(ex,0),300,'Saved TS can explain a different basis');
ex.sets[0].manual=true;ex.sets[0].kg='113.3980925';weightCtx.applyAuto(ex);assert.equal(ex.sets[0].kg,'113.3980925','Manual 250 lb is preserved rather than recalculated');
console.log('Exact kg, whole-pound references, equipment isolation, shortages and load-source trace passed.');
