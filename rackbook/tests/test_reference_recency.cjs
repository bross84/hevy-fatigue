const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const html=fs.readFileSync(path.join(__dirname,'../log.html'),'utf8');
const now=Date.parse('2026-11-24T12:00:00Z'),day=86400000;
class Clock extends Date {static now(){return now;}}
const c=vm.createContext({draft:{client_workout_id:"workout-one"},Date:Clock,LB_PER_KG:2.20462262185,num:Number,lbOfKg:n=>n*2.20462262185,
  pctFor:()=>.9,plannedKg:lb=>lb/2.20462262185,showWeight(){}});
vm.runInContext(html.slice(html.indexOf('  function setE1rm('),html.indexOf('  function refreshCard(')),c);
const stamp=days=>new Date(now-days*day).toISOString();
const make=()=>({template_id:'bench',ref:{basis:'e1rm',ls:true,tmPct:.95,state:{found:true,e1rm_lb:240,workout_start_time:stamp(91)}},
  sets:[{type:'normal',kg:'110',reps:'2',rpe:'8',done:false,manual:false}]});
let ex=make();assert.equal(c.baseFor(ex,0),null);c.applyAuto(ex);assert.equal(ex.sets[0].kg,'');
ex.ref.state.workout_start_time=stamp(90);assert.equal(c.baseFor(ex,0),240);
ex.ref.state.workout_start_time='invalid';assert.equal(c.baseFor(ex,0),null);
ex.ref.ts={found:true,e1rm_lb:275,set_at:stamp(91)};
assert.equal(c.baseFor(ex,0),null,'Stale TS cannot fall through to another reference');
ex.staleTsConfirmation=c.tsConfirmationKey(ex);assert.equal(c.baseFor(ex,0),275);
ex=JSON.parse(JSON.stringify(ex));assert.equal(c.baseFor(ex,0),275,'Same workout reload retains confirmation');
c.draft.client_workout_id='workout-two';assert.equal(c.baseFor(ex,0),null,'Copied confirmation cannot authorize a new workout');c.draft.client_workout_id='workout-one';
ex.ref.basis='tm';assert.equal(c.baseFor(ex,0),275*.95);
ex.ref.ts.e1rm_lb=280;assert.equal(c.baseFor(ex,0),null,'Changed TS requires fresh confirmation');
const other=make();other.ref.ts=ex.ref.ts;assert.equal(c.baseFor(other,0),null,'Confirmation is not shared across workouts');
ex.sets[0].manual=true;ex.sets[0].kg='100';c.applyAuto(ex);assert.equal(ex.sets[0].kg,'100');
ex.sets[0].manual=false;ex.sets[0].done=true;ex.sets[0].arpe='6';c.applyAuto(ex);assert.equal(ex.sets[0].kg,'100');
ex.sets.push({type:'normal',kg:'',reps:'2',rpe:'8'});
assert.ok(c.baseFor(ex,1)>240,'Movement-specific completed actual effort still supplies LSe1RM');
ex.ref.ls=false;assert.equal(c.baseFor(ex,1),null);
ex.ref.autoWeights=false;c.applyAuto(ex);assert.equal(ex.sets[0].kg,'100');
console.log('90-day boundary, stale TS confirmation, reload, changed references, manual/completed loads and LS passed.');
