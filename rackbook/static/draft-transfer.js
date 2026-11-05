/* Versioned, browser-only transfer. Importing never calls an API. */
const DraftTransfer = (() => {
  const keys={ 'workout-draft':'training.logDraft', 'microcycle-editor':'training.mesocycleEditor' };
  const uuid=/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
  function assert(ok) {if(!ok)throw Error('Invalid draft file. Existing drafts have not changed.');}
  function object(x) {return x && typeof x==='object' && !Array.isArray(x);}
  function string(x,max=4000) {return typeof x==='string' && x.length<=max;}
  function numeric(x) {return (typeof x==='number' && Number.isFinite(x)) || (typeof x==='string' && x.length<40 && (x.trim()==='' || Number.isFinite(Number(x))));}
  function inputNumber(x) {return typeof x==='string' && numeric(x);}
  function timestamp(x) {return string(x,100)&&/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(x)&&Number.isFinite(Date.parse(x));}
  function planLink(x) {assert(object(x)&&string(x.mesocycle_id,100)&&x.mesocycle_id.length>0&&string(x.session_id,100)&&x.session_id.length>0);}
  function optionalNumber(x,min,max=Infinity) {assert(x==null||(typeof x==='number'&&Number.isFinite(x)&&x>=min&&x<=max));}
  function evidence(x) {
    assert(object(x)&&string(x.set_id,200)&&x.set_id.length>0&&string(x.exercise_id,200)&&x.exercise_id.length>0);
    assert(typeof x.manual_weight==='boolean'&&typeof x.ls_enabled==='boolean'&&['e1rm','tm'].includes(x.basis));
    assert(['entered','copied_target','unrated','unknown'].includes(x.rpe_source)&&timestamp(x.completed_at));
    optionalNumber(x.suggested_weight_kg,0);optionalNumber(x.actual_percentage,Number.MIN_VALUE,1);
  }
  function prescription(x) {
    assert(object(x)&&x.version===1&&['plan','repeated_workout','ad_hoc'].includes(x.source)&&string(x.name));
    assert(Array.isArray(x.exercises)&&x.exercises.length<=100&&Array.isArray(x.rpe_chart)&&x.rpe_chart.length<=2000);
    if(x.plan_revision!=null)assert(Number.isInteger(x.plan_revision)&&x.plan_revision>=0);
    for(const field of ['plan_id','session_id'])if(x[field]!=null)assert(string(x[field],100));
    const movements=new Set(),sets=new Set();
    for(const ex of x.exercises){
      assert(object(ex)&&string(ex.id,200)&&ex.id.length>0&&!movements.has(ex.id)&&string(ex.exercise_template_id,200)&&ex.exercise_template_id.length>0&&string(ex.title,200)&&Array.isArray(ex.sets)&&ex.sets.length<=200);movements.add(ex.id);
      if(ex.notes!=null)assert(string(ex.notes));
      for(const s of ex.sets){assert(object(s)&&string(s.id,200)&&s.id.length>0&&!sets.has(s.id)&&['warmup','normal','failure','dropset'].includes(s.type)&&typeof s.ts==='boolean');sets.add(s.id);
        if(s.reps!=null)assert(Number.isInteger(s.reps)&&s.reps>=0&&s.reps<=1000);
        optionalNumber(s.rpe,0,10);optionalNumber(s.weight_kg,0);}
    }
    for(const cell of x.rpe_chart){assert(object(cell)&&Number.isInteger(cell.reps)&&cell.reps>=1&&cell.reps<=1000);optionalNumber(cell.rpe,0,10);optionalNumber(cell.percentage,Number.MIN_VALUE,1);assert(cell.rpe!=null&&cell.percentage!=null);}
  }
  function frozenRequest(x,id) {
    assert(object(x)&&x.client_workout_id===id&&string(x.title)&&timestamp(x.start_time)&&timestamp(x.end_time)&&Date.parse(x.end_time)>=Date.parse(x.start_time)&&Array.isArray(x.exercises)&&x.exercises.length>0);
    assert([undefined,null,'kg','lb'].includes(x.weight_unit));
    if(x.planned_session)planLink(x.planned_session);
    if(x.prescription!=null)prescription(x.prescription);
    for(const ex of x.exercises){
      assert(object(ex)&&string(ex.exercise_template_id,200)&&ex.exercise_template_id.length>0&&Array.isArray(ex.sets)&&ex.sets.length>0);
      assert([undefined,null,'kg','lb'].includes(ex.weight_unit));if(ex.notes!=null)assert(string(ex.notes));
      for(const s of ex.sets){assert(object(s)&&['warmup','normal','failure','dropset'].includes(s.type));
        if(s.weight_kg!=null)assert(typeof s.weight_kg==='number'&&Number.isFinite(s.weight_kg)&&s.weight_kg>=0);
        if(s.reps!=null)assert(Number.isInteger(s.reps)&&s.reps>=0);
        if(s.rpe!=null)assert(typeof s.rpe==='number'&&Number.isFinite(s.rpe)&&s.rpe>=0&&s.rpe<=10);
        if(s.target_rpe!=null)assert(typeof s.target_rpe==='number'&&Number.isFinite(s.target_rpe)&&s.target_rpe>=0&&s.target_rpe<=10);
        if(s.review!=null)evidence(s.review);
        if(s.ts!==undefined)assert(typeof s.ts==='boolean');}
    }
  }
  function safe(x,depth=0) {
    assert(depth<30);
    if(typeof x==='number')assert(Number.isFinite(x));
    if(typeof x==='string')assert(x.length<100000);
    if(x&&typeof x==='object')for(const [k,v] of Object.entries(x)){assert(!['__proto__','constructor','prototype'].includes(k));safe(v,depth+1);}
  }
  function validateWorkout(d) {
    assert(object(d)&&string(d.title)&&timestamp(d.startedAt)&&Array.isArray(d.exercises)&&d.exercises.length<=100);
    if(d.client_workout_id!==undefined)assert(uuid.test(d.client_workout_id));
    if(d.planned_session)planLink(d.planned_session);
    if(d.prescription!=null)prescription(d.prescription);
    for(const ex of d.exercises){
      assert(object(ex)&&string(ex.id,200)&&ex.id.length>0&&string(ex.template_id,200)&&ex.template_id.length>0&&string(ex.title,200)&&Array.isArray(ex.sets)&&ex.sets.length<=200);
      if(ex.notes!=null)assert(string(ex.notes));
      if(ex.ref){
        assert(object(ex.ref)&&[undefined,null,'kg','lb'].includes(ex.ref.weightUnit));
        for(const field of ['state','ts'])if(ex.ref[field]!=null)assert(object(ex.ref[field]));
        if(ex.ref.state?.previous!=null)assert(Array.isArray(ex.ref.state.previous)&&ex.ref.state.previous.every(object));
      }
      for(const s of ex.sets){assert(object(s)&&['warmup','normal','failure','dropset'].includes(s.type)&&inputNumber(s.kg)&&inputNumber(s.reps)&&inputNumber(s.rpe)&&typeof s.done==='boolean');if(s.arpe!==undefined)assert(inputNumber(s.arpe));if(s.ts!==undefined)assert(typeof s.ts==='boolean');
        if(s.review!=null)evidence(s.review);if(s.review_id!=null)assert(string(s.review_id,200)&&s.review_id.length>0);
        if(s.actualSource!=null)assert(['entered','copied_target','unrated','unknown'].includes(s.actualSource));
        optionalNumber(s.autoSuggestion,0);}
    }
    if(d.frozenSave)frozenRequest(d.frozenSave,d.client_workout_id);
    safe(d);return d;
  }
  function validateEditor(data) {
    assert(object(data)&&object(data.plan)&&Number.isInteger(data.wi)&&Number.isInteger(data.si));
    const p=data.plan;
    if(p.program_name!==undefined)assert(string(p.program_name,90));
    if(p.notes!==undefined)assert(string(p.notes,4000));
    if(p.completed!==undefined)assert(Array.isArray(p.completed)&&p.completed.every(c=>object(c)&&string(c.session_id,100)));
    for(const key of ['cycle','week'])if(p[key]!=null)assert(typeof p[key]==='number'&&Number.isFinite(p[key]));
    assert(string(p.name,120)&&Array.isArray(p.weeks)&&p.weeks.length===1&&Array.isArray(p.weeks[0].sessions)&&p.weeks[0].sessions.length<=14&&data.wi===0);
    assert(data.si>=0&&data.si<Math.max(1,p.weeks[0].sessions.length));
    for(const session of p.weeks[0].sessions){assert(object(session)&&string(session.id,100)&&string(session.name,120)&&Array.isArray(session.exercises)&&session.exercises.length<=30);
      for(const ex of session.exercises){assert(object(ex)&&string(ex.exercise_template_id,200)&&string(ex.title,200)&&Array.isArray(ex.sets)&&ex.sets.length<=50);
        // Editor inputs intentionally store null while a numeric field is blank.
        // Preserve unfinished edits; the plan API validates them at save time.
        for(const s of ex.sets)assert(object(s)&&(s.reps==null||numeric(s.reps))&&(s.rpe==null||numeric(s.rpe))&&(s.weight_kg==null||numeric(s.weight_kg))&&['normal','failure','dropset'].includes(s.type));}}
    safe(data);return data;
  }
  function validate(envelope,type) {
    assert(object(envelope)&&envelope.version===1&&envelope.type===type&&Object.hasOwn(keys,type)&&object(envelope.data));
    safe(envelope);
    const data=envelope.data;
    if(type==='workout-draft'){
      validateWorkout(data.draft);
      assert([undefined,'kg','lb'].includes(data.unit));
      for(const k of ['restEnd','restTotal','restSecs'])if(data[k]!=null)assert(numeric(data[k]));
    }else validateEditor(data);
    return structuredClone(data);
  }
  function exportData(type,storage=localStorage) {
    assert(Object.hasOwn(keys,type));
    const draft=JSON.parse(storage.getItem(keys[type]));
    const data=type==='workout-draft'?{draft,unit:storage.getItem('training.unit')||'kg',restEnd:storage.getItem('training.restEnd'),restTotal:storage.getItem('training.restTotal'),restSecs:storage.getItem('training.restSecs')}:draft;
    const envelope={version:1,type,data};validate(envelope,type);return envelope;
  }
  function importData(envelope,type,storage=localStorage,confirmReplace=confirm) {
    const data=validate(envelope,type), key=keys[type];
    if(storage.getItem(key)&&!confirmReplace('Replace this device’s existing '+(type==='workout-draft'?'workout draft':'unsaved plan edits')+'?'))return false;
    const changes=type==='workout-draft'?{[key]:JSON.stringify(data.draft),'training.unit':data.unit||'kg','training.restEnd':Number(data.restEnd)>Date.now()?String(data.restEnd):null,'training.restTotal':Number(data.restEnd)>Date.now()?String(data.restTotal||0):null,'training.restSecs':data.restSecs==null?null:String(data.restSecs)}:{[key]:JSON.stringify(data)};
    const before=Object.fromEntries(Object.keys(changes).map(k=>[k,storage.getItem(k)]));
    try{for(const [k,v]of Object.entries(changes))v==null?storage.removeItem(k):storage.setItem(k,v);}
    catch(e){for(const[k,v]of Object.entries(before))v==null?storage.removeItem(k):storage.setItem(k,v);throw e;}
    return true;
  }
  function install(type) {
    const bar=document.createElement('details');bar.style.cssText='margin:1rem 0';
    const title=document.createElement('summary');title.textContent='Transfer device draft';bar.append(title);
    const message=document.createElement('p');message.setAttribute('role','status');
    const out=document.createElement('button');out.type='button';out.textContent='Export draft JSON';out.onclick=()=>{try{const blob=new Blob([JSON.stringify(exportData(type),null,2)],{type:'application/json'});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=type+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);}catch(e){message.textContent=e.message;}};
    const input=document.createElement('input');input.type='file';input.accept='.json,application/json';input.setAttribute('aria-label','Import draft JSON');input.onchange=async()=>{try{const f=input.files[0];if(!f)return;assert(f.size<=2000000);if(importData(JSON.parse(await f.text()),type)){message.textContent='Imported locally. Reloading draft.';location.reload();}}catch(e){message.textContent=e.message;}finally{input.value='';}};
    bar.append(out,input,message);
    // Keep editor transfer controls above its sticky save bar on phone screens.
    const editor=type==='microcycle-editor'&&document.getElementById('editor');
    if(editor)editor.before(bar);else document.querySelector('main').append(bar);
  }
  return {validate,validateWorkout,validateEditor,exportData,importData,install};
})();
