/* Suggestions and intent only. This module never edits workout sets or plans. */
const SessionAdvice = (() => {
  const cache=new Map();let currentSession=null;
  const node=(tag,text)=>{const n=document.createElement(tag);if(text!=null)n.textContent=text;return n;};
  const day=()=>{const d=new Date();return d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0');};
  async function post(path,body){const r=await fetch(trainingUrl(path),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    const data=await r.json();if(!r.ok)throw Error(typeof data.detail==='string'?data.detail:'Suggestion unavailable.');return data;}
  function mount(draft,ex,box,save,pain=false){
    if(draft.frozenSave){box.replaceChildren(node('p','Recommendation decisions are frozen while saving.'));return;}
    if(currentSession!==draft.client_workout_id){cache.clear();currentSession=draft.client_workout_id;}
    const key=draft.client_workout_id+':'+ex.id;
    let state=cache.get(key);
    const working=ex.sets.filter(s=>s.type!=='warmup');
    if(!working.length)return;
    if(!state){state={row:null,error:null,pending:false};cache.set(key,state);}
    const link=()=>{if(draft.frozenSave||!state.row)return;
      const item={recommendation_id:state.row.id,decision_id:state.row.decision?.id || null};
      draft.advisory_links=[...(draft.advisory_links || []).filter(x=>x.recommendation_id!==item.recommendation_id),item];save();};
    const load=async()=>{state.pending=true;draw();try{state.row=await post('/session-advice',{
      session_id:draft.client_workout_id,exercise_id:ex.id,exercise_template_id:ex.template_id,title:ex.title,
      workout_start:draft.startedAt,local_date:day(),sets:working.map(s=>({reps:Number(s.reps),rpe:s.rpe?Number(s.rpe):null,ts:Boolean(s.ts)})),
      automatic_weights:ex.ref.autoWeights!==false,started:working.some(s=>s.done),pain});state.error=null;link();}
      catch(e){state.error=e.message;}finally{state.pending=false;state.render();}};
    function draw(){
      box.replaceChildren();
      if(draft.frozenSave){box.append(node('p','Recommendation decisions are frozen while saving.'));return;}
      if(!state.row){box.append(node('p',state.pending?'Preparing provisional session advice…':state.error || 'Session advice available before lifting.'));
        if(!state.pending){const retry=node('button','Get session advice');retry.type='button';retry.addEventListener('click',load);box.append(retry);}return;}
      const row=state.row,decision=row.decision;
      const details=node('details');details.open=row.action!=='hold'&&!row.suppressed&&!['dismiss','not_now'].includes(decision?.action);
      details.style.cssText='margin:10px 0;overflow-wrap:anywhere';
      details.append(node('summary','Provisional session advice'+(decision?' · '+decision.action.replaceAll('_',' '):'')));
      details.append(node('p',row.message),node('p','Suggested working sets: '+row.proposed.working_sets+'. No workout or program edits are applied.'));
      details.append(node('p','Evidence is frozen when this suggestion is captured; later workout/check-in edits are not a fresh assessment.'));
      if(decision)details.append(node('p','Recorded decision: '+decision.action.replaceAll('_',' ')+(decision.reason?' — '+decision.reason:'')));
      if(decision?.dose)details.append(node('p','Recorded intent: '+decision.dose.working_sets+' working sets'+
        (decision.dose.reps!=null?', '+decision.dose.reps+' reps':'')+(decision.dose.target_rpe!=null?', RPE '+decision.dose.target_rpe:'')+'.'));
      if(state.error)details.append(node('p',state.error));
      for(const text of row.reasons)details.append(node('p',text));
      const reason=node('input');reason.type='text';reason.maxLength=1000;reason.setAttribute('aria-label','Optional recommendation reason for '+ex.title);reason.placeholder='Reason (optional)';
      details.append(reason);
      const buttons=node('div');buttons.style.cssText='display:grid;grid-template-columns:1fr 1fr;gap:6px;margin:8px 0';
      const modify=node('div');modify.hidden=true;
      const number=(name,value,min,max,step)=>{const label=node('label',name),input=node('input');label.style.display='block';input.style.width='100%';input.style.minWidth='0';input.type='number';input.min=min;input.max=max;input.step=step;input.value=value ?? '';input.setAttribute('aria-label',name+' for '+ex.title);label.append(input);modify.append(label);return input;};
      const intended=decision?.dose || row.proposed;
      const sets=number('Intended working sets',intended.working_sets,0,100,1);
      const reps=number('Intended reps (optional)',intended.reps,1,1000,1);
      const rpe=number('Intended RPE (optional)',intended.target_rpe,4,10,.5);
      const decide=async(action,modification=null)=>{if(state.pending||draft.frozenSave)return;state.pending=true;
        for(const b of buttons.children)b.disabled=true;record.disabled=true;
        try{state.row=await post('/session-advice/'+encodeURIComponent(row.id)+'/decisions',{
          id:trainingUUID(),action,modification,reason:reason.value || '',expected_decision_id:row.decision?.id || null});state.error=null;link();}
        catch(e){state.error=e.message;}finally{state.pending=false;state.render();}};
      for(const [text,action] of [['Accept','accept'],['Modify','modify'],['Dismiss','dismiss'],['Not now','not_now']]){
        const b=node('button',text);b.type='button';b.disabled=state.pending;b.addEventListener('click',()=>{
          if(action==='modify'){modify.hidden=!modify.hidden;return;}decide(action);});buttons.append(b);}
      const record=node('button','Record modification');record.type='button';record.disabled=state.pending;
      record.addEventListener('click',()=>{if(![sets,reps,rpe].every(n=>n.reportValidity())||!sets.value)return;
        decide('modify',{working_sets:Number(sets.value),reps:reps.value?Number(reps.value):null,target_rpe:rpe.value?Number(rpe.value):null});});
      modify.append(record,node('p','Intent only. Make any changes yourself in the workout.'));
      details.append(buttons,modify);
      const evidence=node('details');evidence.append(node('summary','Evidence and limitations'));
      if(row.evidence.captured_at)evidence.append(node('p','Captured: '+new Date(row.evidence.captured_at).toLocaleString()));
      evidence.append(node('p',row.evidence.comparable_exposures+' rep-matched exposures from '+row.evidence.history_workouts+' known stored workouts.'));
      for(const c of row.evidence.checkins)evidence.append(node('p',c.date+': tiredness '+(c.tiredness ?? 'unknown')+'/4; poor recovery '+(c.perceived_recovery ?? 'unknown')+'/4.'));
      for(const f of row.evidence.feedback || [])evidence.append(node('p','Recent feedback: '+f.action.replaceAll('_',' ')+(f.reason?' — '+f.reason:'')+
        (f.saved_working_sets!=null?'; '+f.saved_working_sets+' sets later saved':' (no linked saved outcome yet)')+'.'));
      for(const text of row.limitations)evidence.append(node('p',text));details.append(evidence);
      const refresh=node('button','Refresh recorded decision');refresh.type='button';refresh.disabled=state.pending;refresh.addEventListener('click',load);details.append(refresh);
      box.append(details);
    }
    state.render=draw;draw();if(!state.row&&!state.pending&&!state.error)load();
  }
  return {mount};
})();
