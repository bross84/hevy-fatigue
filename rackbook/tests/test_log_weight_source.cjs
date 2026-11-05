const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const html=fs.readFileSync(path.join(__dirname,'../log.html'),'utf8');
function el(tag,cls,text){const n={tag,cls,children:[],attrs:{},events:{},textContent:text,
  classList:{add(){}},append(...items){this.children.push(...items)},setAttribute(k,v){this.attrs[k]=v},
  addEventListener(k,v){this.events[k]=v},querySelector(sel){return walk(this).find(x=>x.cls?.split(' ').includes(sel.slice(1)))}};return n;}
const walk=n=>[n,...n.children.filter(x=>typeof x==='object').flatMap(walk)];
let saved=[];
const c=vm.createContext({el,LB_PER_KG:2.20462262185,num:Number,lbOfKg:n=>n*2.20462262185,
  pctFor:rpe=>({5:.7,6:.75,7:.8})[rpe],plannedKg:lb=>Math.round(lb/2.20462262185/2.5)*2.5,
  showWeight(){},saveDraft(){},saveRef:ex=>saved.push(structuredClone(ex.ref)),refreshCard(){},
  trim:String,fmtShortDate:String,setE1Cells:new Map()});
vm.runInContext(html.slice(html.indexOf('  function setE1rm('),html.indexOf('  function refreshCard(')),c);
vm.runInContext(html.slice(html.indexOf('  function renderRefBar('),html.indexOf('  // ── The plate loader')),c);
const ex={ref:{basis:'e1rm',ls:true,tmPct:.95,state:{found:true,e1rm_lb:300}},sets:[
  {type:'normal',done:true,kg:'100',reps:'5',rpe:'6',arpe:'5'},
  {type:'normal',done:false,manual:false,kg:'90',reps:'5',rpe:'6'},
  {type:'normal',done:false,manual:true,kg:'80',reps:'5',rpe:'6'}]};
const select=(box,name)=>walk(box).find(n=>n.attrs['aria-label']===name);
let bar=c.renderRefBar(ex);
assert.equal(select(bar,'Use e1RM for weights').attrs['aria-pressed'],'true');
select(bar,'Use e1RM for weights').events.click();
assert.equal(ex.ref.autoWeights,false);
assert.deepEqual(ex.sets.map(s=>s.kg),['100','90','80'],'Deselecting preserves supplied and completed weights');
bar=c.renderRefBar(ex);
assert.equal(select(bar,'Use e1RM for weights').attrs['aria-pressed'],'false');
assert.equal(select(bar,'Use TM for weights').attrs['aria-pressed'],'false');
assert.equal(walk(bar).find(n=>n.textContent==='LSe1RM').disabled,true);
assert.equal(ex.ref.ls,true,'Deselecting must remember the existing LS preference');
ex.sets[0].arpe='7';ex.sets[1].rpe='7';c.applyAuto(ex);
assert.equal(c.baseFor(ex,1),null);assert.equal(c.autoWeight(ex,1),null);
assert.equal(ex.sets[1].kg,'90','Actual/target RPE edits cannot calculate weights with neither selected');
select(bar,'Use TM for weights').events.click();
assert.equal(ex.ref.autoWeights,true);assert.equal(ex.ref.basis,'tm');
assert.notEqual(ex.sets[1].kg,'90','Selecting a source restores the existing automatic behavior');
assert.equal(ex.sets[0].kg,'100');assert.equal(ex.sets[2].kg,'80');
bar=c.renderRefBar(ex);select(bar,'Use TM for weights').events.keydown({key:' ',preventDefault(){}});
assert.equal(ex.ref.autoWeights,false,'Keyboard activation can deselect TM too');
assert.deepEqual(saved.map(x=>x.autoWeights),[false,true,false]);
console.log('Both weight sources can be deselected; no auto calculation, remembered LS and fixed/completed loads preserved.');
