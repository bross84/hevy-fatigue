/* A frozen payload belongs to one durable draft identity, including its end time. */
const WorkoutSave = (() => {
  const key = 'training.logDraft';
  function freeze(draft, entry) {
    if (!draft.client_workout_id) draft.client_workout_id = trainingUUID();
    if (!draft.frozenSave) draft.frozenSave = {...entry, client_workout_id:draft.client_workout_id};
    // Storage failure must prevent the remote request.
    localStorage.setItem(key, JSON.stringify(draft));
    return draft.frozenSave;
  }
  function noteFailure(draft, error) {
    // FastAPI's field-validation response is produced before the route runs.
    // A timeout, generic 422 or missing journal record alone proves nothing.
    if (draft?.frozenSave && error.status===422 && error.validationRejected===true) {
      draft.validationRejected=true;
      draft.validationError=error.message;
      try { localStorage.setItem(key,JSON.stringify(draft)); } catch (_) {}
    }
  }
  function correct(draft) {
    if (!confirm('This attempt was rejected before creating a workout. Unlock the draft and create a new save identity?')) return false;
    const corrected={...draft,client_workout_id:trainingUUID()};
    delete corrected.frozenSave;delete corrected.validationRejected;delete corrected.validationError;
    delete corrected.advisory_links;
    // Retain the original identity and frozen payload if persistence fails.
    localStorage.setItem(key,JSON.stringify(corrected));
    delete draft.frozenSave;delete draft.validationRejected;delete draft.validationError;
    delete draft.advisory_links;
    draft.client_workout_id=corrected.client_workout_id;
    return true;
  }
  function panel(draft, onComplete) {
    document.getElementById('saveRecovery')?.remove();
    if (!draft?.frozenSave) return;
    const box = document.createElement('section'); box.id='saveRecovery'; box.className='card';
    box.setAttribute('aria-live','polite');
    const message=document.createElement('p');
    message.textContent='A frozen save is pending. Check its status before changing or saving this workout.';
    box.append(message);
    async function request(suffix='', body=null) {
      const response=await fetch(trainingUrl('/workout-saves/'+draft.client_workout_id+suffix), body ?
        {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)} : suffix ? {method:'POST'} : {});
      const result=await response.json();
      if (response.status===404 && draft.validationRejected===true) {
        message.textContent=draft.validationError || 'Request validation rejected this attempt before saving.';
        corrected.hidden=false;
        return;
      }
      if (!response.ok) throw Error(typeof result.detail==='string'?result.detail:'Recovery request failed.');
      message.textContent=result.status+(result.failure_reason?' '+result.failure_reason:'');
      retry.hidden=result.state!=='remote_saved'; reconcile.hidden=!['sending','uncertain'].includes(result.state);
      corrected.hidden=result.state!=='rejected'; first.hidden=result.state!=='prepared';
      if(result.state==='complete') onComplete(result);
      return result;
    }
    function button(text,fn) {const b=document.createElement('button');b.type='button';b.textContent=text;b.addEventListener('click',async()=>{b.disabled=true;try{await fn();}catch(e){message.textContent=e.message;}finally{b.disabled=false;}});box.append(b);return b;}
    button('Check save status',()=>request());
    const first=button('Resume prepared save',async()=>{const r=await fetch(trainingUrl('/hevy/workouts'),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(draft.frozenSave)});if(!r.ok)throw Error('Save could not be resumed. Check status.');await request();});first.hidden=true;
    const retry=button('Finish local records',()=>request('/finalize'));retry.hidden=true;
    const reconcile=button('Link verified Hevy workout',async()=>{const id=prompt('Existing Hevy workout ID (from Recent workouts or Hevy). This will only read and verify it.');if(id?.trim())await request('/reconcile',{hevy_workout_id:id.trim()});});reconcile.hidden=true;
    const corrected=button('Correct rejected draft',()=>{if(correct(draft))location.reload();});corrected.hidden=true;
    const recent=document.createElement('a');recent.href=trainingUrl('/recent');recent.textContent='Recent workouts';box.append(recent);
    const settings=document.createElement('a');settings.href='/#settings';settings.textContent='Monitoring sync and settings';settings.style.marginLeft='1rem';box.append(settings);
    document.querySelector('main').prepend(box);
    request().catch(e=>{message.textContent=e.message+' The frozen draft is retained.';});
  }
  function monitoring(saved) {
    document.getElementById('monitoringRefresh')?.remove();
    const box=document.createElement('section');box.id='monitoringRefresh';box.setAttribute('aria-live','polite');
    const status=document.createElement('p');
    const show=value=>{status.textContent='Monitoring refresh '+(value||'pending')+'. Your workout is saved.';};
    show(saved.monitoring_refresh);
    const settings=document.createElement('a');settings.href='/#settings';settings.textContent='Open Settings to sync';
    const check=document.createElement('button');check.type='button';check.textContent='Check monitoring refresh';
    check.addEventListener('click',async()=>{check.disabled=true;try{const response=await fetch(trainingUrl('/workout-saves/'+saved.client_workout_id));if(!response.ok)throw Error();show((await response.json()).monitoring_refresh);}catch(e){show('pending; status unavailable');}finally{check.disabled=false;}});
    box.append(status,settings,check);document.getElementById('done').append(box);
  }
  return {freeze,panel,monitoring,noteFailure,correct};
})();
