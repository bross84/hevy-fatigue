const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),path=require('node:path');
const root=path.join(__dirname,'../rackbook/static');
const context=vm.createContext({structuredClone,Date,confirm:()=>false});
vm.runInContext(fs.readFileSync(path.join(root,'draft-transfer.js'),'utf8')+';this.transfer=DraftTransfer;',context);
const storage=()=>{const values=new Map();return {getItem:k=>values.get(k)??null,setItem:(k,v)=>values.set(k,String(v)),removeItem:k=>values.delete(k),values};};
const source=storage(),dest=storage();
const draft={title:'ST workout',startedAt:'2026-10-30T10:00:00Z',client_workout_id:'12345678-1234-4123-8123-123456789abc',
 planned_session:{mesocycle_id:'plan',session_id:'day'},exercises:[{id:'movement-1',template_id:'sq',title:'Squat',notes:'Keep this',ref:{weightUnit:'lb'},sets:[{type:'normal',kg:'100.123',reps:'1',rpe:'5',ts:true,done:true,manual:true}]}]};
source.setItem('training.logDraft',JSON.stringify(draft));source.setItem('training.unit','lb');source.setItem('training.restEnd',Date.now()-1000);source.setItem('secret','must never export');
const file=context.transfer.exportData('workout-draft',source);
assert.ok(!JSON.stringify(file).includes('must never export'));
assert.ok(context.transfer.importData(file,'workout-draft',dest,()=>{throw Error('No existing draft');}));
assert.equal(dest.getItem('training.logDraft'),JSON.stringify(draft));assert.equal(dest.getItem('training.restEnd'),null);
const before=JSON.stringify([...dest.values]);
let confirmations=0;
assert.equal(context.transfer.importData(file,'workout-draft',dest,()=>{confirmations++;return false;}),false);
assert.equal(confirmations,1);assert.equal(JSON.stringify([...dest.values]),before);
const invalid=structuredClone(file);invalid.data.draft.exercises[0].sets[0].kg={bad:true};
assert.throws(()=>context.transfer.importData(invalid,'workout-draft',dest,()=>true));
assert.equal(JSON.stringify([...dest.values]),before);
// Workout inputs are strings throughout the real logger. A numeric JSON value
// must be rejected before confirmation/storage instead of breaking .trim().
for(const field of ['kg','reps','rpe','arpe']) {
  const malformed=structuredClone(file);malformed.data.draft.exercises[0].sets[0][field]=5;
  assert.throws(()=>context.transfer.importData(malformed,'workout-draft',dest,()=>{throw Error('Must validate before asking to replace');}));
  assert.equal(JSON.stringify([...dest.values]),before);
}
for(const mutate of [d=>delete d.exercises[0].id,d=>d.startedAt='10/30/2026',
                    d=>d.exercises[0].ref.state={previous:{}},d=>d.frozenSave={client_workout_id:d.client_workout_id,end_time:'invalid',exercises:[]}]){
  const malformed=structuredClone(file);mutate(malformed.data.draft);
  assert.throws(()=>context.transfer.importData(malformed,'workout-draft',dest,()=>true));
  assert.equal(JSON.stringify([...dest.values]),before);
}
const log=fs.readFileSync(path.join(__dirname,'../rackbook/log.html'),'utf8');
Object.assign(context,{draft:JSON.parse(dest.getItem('training.logDraft')),unit:'lb',sorenessPatterns:null,document:{querySelector:()=>null}});
vm.runInContext(log.slice(log.indexOf('  function buildEntry()'),log.indexOf('  const saveDialog =')),context);
assert.equal(context.buildEntry().exercises[0].sets[0].weight_kg,100.123);
assert.throws(()=>context.transfer.importData({...file,version:2},'workout-draft',dest,()=>true));
assert.throws(()=>context.transfer.importData(file,'microcycle-editor',dest,()=>true));
const editor={plan:{name:'Unsaved plan',weeks:[{name:'Week',sessions:[{id:'day',name:'Day',exercises:[{exercise_template_id:'sq',title:'Squat',sets:[{type:'normal',reps:5,rpe:5,weight_kg:80,ts:true}]}]}]}]},wi:0,si:0,assignmentCatalog:{}};
source.setItem('training.mesocycleEditor',JSON.stringify(editor));
const editorFile=context.transfer.exportData('microcycle-editor',source);
context.transfer.importData(editorFile,'microcycle-editor',dest,()=>true);
assert.equal(dest.getItem('training.mesocycleEditor'),JSON.stringify(editor));
assert.equal(dest.getItem('training.logDraft'),JSON.stringify(draft));
// A cleared reps field is a legitimate unfinished editor value, not a saved
// prescription. It must survive export, import and the exact restore validator.
const unfinished=structuredClone(editor);
unfinished.plan.weeks[0].sessions[0].exercises[0].sets[0].reps=null;
source.setItem('training.mesocycleEditor',JSON.stringify(unfinished));
const unfinishedFile=context.transfer.exportData('microcycle-editor',source);
context.transfer.importData(unfinishedFile,'microcycle-editor',dest,()=>true);
const restored=JSON.parse(dest.getItem('training.mesocycleEditor'));
context.transfer.validateEditor(restored);
assert.equal(restored.plan.weeks[0].sessions[0].exercises[0].sets[0].reps,null);
const malformedEditor=structuredClone(unfinishedFile);
malformedEditor.data.plan.weeks[0].sessions[0].exercises[0].sets[0].reps={invalid:true};
const editorBefore=dest.getItem('training.mesocycleEditor');
assert.throws(()=>context.transfer.importData(malformedEditor,'microcycle-editor',dest,()=>true));
assert.equal(dest.getItem('training.mesocycleEditor'),editorBefore);
for(const mutate of [p=>p.completed={},p=>p.program_name=42,p=>p.notes={}]){
  const malformed=structuredClone(unfinishedFile);mutate(malformed.data.plan);
  assert.throws(()=>context.transfer.importData(malformed,'microcycle-editor',dest,()=>true));
  assert.equal(dest.getItem('training.mesocycleEditor'),editorBefore);
}
// There is no fetch/API object in this VM; transferring a draft cannot post or complete anything.
let persisted='';const freezeContext=vm.createContext({localStorage:{setItem:(k,v)=>persisted=v},trainingUUID:()=>draft.client_workout_id});
vm.runInContext(fs.readFileSync(path.join(root,'save-recovery.js'),'utf8')+';this.freeze=WorkoutSave.freeze;',freezeContext);
const old={exercises:[]},one={end_time:'original'},two={end_time:'later'};
freezeContext.freeze(old,one);assert.ok(JSON.parse(persisted).client_workout_id);
assert.equal(freezeContext.freeze(old,two).end_time,'original');
freezeContext.localStorage.setItem=()=>{throw Error('Quota exceeded');};
assert.throws(()=>freezeContext.freeze({},one),/Quota/);
// Separate Rx and actual values also survive transfer of a pending frozen save.
const paired=structuredClone(draft);
paired.exercises[0].sets[0].rpe='6';paired.exercises[0].sets[0].arpe='5';
paired.frozenSave={client_workout_id:paired.client_workout_id,title:paired.title,start_time:paired.startedAt,end_time:'2026-10-30T11:00:00Z',exercises:[{exercise_template_id:'sq',sets:[{type:'normal',weight_kg:100.123,reps:1,rpe:5,target_rpe:6,ts:true}]}]};
source.setItem('training.logDraft',JSON.stringify(paired));
const pairedFile=context.transfer.exportData('workout-draft',source);
context.transfer.importData(pairedFile,'workout-draft',dest,()=>true);
assert.deepEqual(JSON.parse(dest.getItem('training.logDraft')),paired);
const badTarget=structuredClone(pairedFile);badTarget.data.draft.frozenSave.exercises[0].sets[0].target_rpe=11;
assert.throws(()=>context.transfer.importData(badTarget,'workout-draft',dest,()=>true));
console.log('Draft transfer: exact sets, separate Rx/actual, TS, notes, references, identity, editor, validation, confirmation, expired timer, frozen payload and no API effects passed.');
