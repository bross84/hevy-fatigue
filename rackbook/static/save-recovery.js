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
  function dismiss() {
    document.getElementById('saveRecovery')?.remove();
    document.querySelector('main').removeAttribute('data-save-recovery');
  }
  function panel(draft, onComplete, {initialStatus, focus = false} = {}) {
    dismiss();
    if (!draft?.frozenSave) return;
    const main = document.querySelector('main');
    const node = (tag, text) => {
      const element = document.createElement(tag);
      if (text) element.textContent = text;
      return element;
    };
    const box = node('section');
    box.id = 'saveRecovery';
    box.className = 'card';
    box.setAttribute('aria-labelledby', 'saveRecoveryTitle');
    const heading = node('h2', 'Workout save pending');
    heading.id = 'saveRecoveryTitle';
    heading.tabIndex = -1;
    const message = node('p', 'Check this attempt before continuing. Your draft is retained.');
    message.setAttribute('aria-live', 'polite');
    const feedback = node('p');
    feedback.className = 'recovery-feedback';
    feedback.setAttribute('role', 'status');
    box.append(heading, message);

    const controls = [];
    let busy = false;
    let statusKnown = false;
    async function run(label, action) {
      if (busy) return;
      busy = true;
      for (const control of controls) control.disabled = true;
      feedback.textContent = label;
      try { await action(); }
      catch (error) {
        if (!statusKnown) {
          heading.textContent = 'Save status unavailable';
          message.textContent = 'The workout may already be in Hevy. Your draft is retained.';
        }
        feedback.textContent = error instanceof TypeError
          ? 'Connection unavailable. Try again when you’re connected.' : error.message;
      } finally {
        busy = false;
        for (const control of controls) control.disabled = false;
      }
    }

    function render(result) {
      statusKnown = true;
      const state = result.state;
      const pending = state === 'remote_saved';
      const unknown = state === 'uncertain';
      const verifying = unknown || state === 'sending';
      box.setAttribute('data-state', state);
      heading.textContent = pending ? 'Saved to Hevy' : unknown ? 'Save outcome unknown'
        : state === 'sending' ? 'Save in progress' : 'Workout save recovery';
      message.textContent = pending
        ? 'Local records are still pending.' + (draft.frozenSave.planned_session ? ' Your plan will advance after they’re saved.' : '')
        : unknown ? 'The workout may already be in Hevy. Your draft is still on this device.'
        : [result.status, result.failure_reason].filter(Boolean).join(' ');
      retry.hidden = retryHint.hidden = !pending;
      lookup.hidden = reconcile.hidden = !verifying;
      settings.hidden = pending || verifying;
      if (!verifying) reconcile.open = false;
      corrected.hidden = state !== 'rejected';
      first.hidden = state !== 'prepared';
      retry.className = pending ? 'recovery-primary' : '';
      check.className = pending ? 'recovery-secondary' : 'recovery-primary';
      if (state === 'complete') onComplete(result);
    }

    async function request(suffix='', body=null) {
      const response=await fetch(trainingUrl('/workout-saves/'+draft.client_workout_id+suffix), body ?
        {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)} : suffix ? {method:'POST'} : {});
      const result=await response.json();
      if (!box.isConnected) return;
      if (response.status===404 && draft.validationRejected===true) {
        render({state:'rejected', status:draft.validationError || 'Request validation rejected this attempt before saving.'});
        feedback.textContent = '';
        return;
      }
      if (!response.ok) throw Error(typeof result.detail==='string'?result.detail:'Recovery request failed.');
      render(result);
      feedback.textContent = '';
      return result;
    }
    function button(text, label, action) {
      const control = node('button', text);
      control.type = 'button';
      controls.push(control);
      control.addEventListener('click', () => run(label, action));
      box.append(control);
      return control;
    }
    const retry = button('Finish local records', 'Finishing local records…', async () => {
      const result = await request('/finalize');
      if (result?.state === 'remote_saved') feedback.textContent = 'Local records are still pending. Try finishing them again.';
    });
    const retryHint = node('p', 'Uses the workout already in Hevy.');
    retryHint.className = 'recovery-hint';
    box.append(retryHint);
    const check = button('Check save status', 'Checking save status…', async () => {
      const result = await request();
      if (result?.state === 'uncertain') feedback.textContent = 'The save outcome is still unknown.';
    });
    check.className = 'recovery-primary';
    const first = button('Resume prepared save', 'Resuming the prepared save…', async () => {
      const response = await fetch(trainingUrl('/hevy/workouts'), {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(draft.frozenSave)});
      if (!response.ok) throw Error('Save could not be resumed. Check its status.');
      await request();
    });
    const corrected = button('Correct rejected draft', '', () => { if (correct(draft)) location.reload(); });
    const recent = node('a', 'Recent workouts');
    recent.href = trainingUrl('/recent');
    const lookup = node('p', 'Look for this workout in Hevy or ');
    lookup.className = 'recovery-hint';
    lookup.append(recent, '.');

    const reconcile = node('details');
    reconcile.append(node('summary', 'I found the workout in Hevy'));
    const form = node('form');
    const label = node('label', 'Existing Hevy workout ID');
    label.htmlFor = 'recoveryWorkoutId';
    const input = node('input');
    input.id = 'recoveryWorkoutId';
    input.type = 'text';
    input.autocomplete = 'off';
    input.setAttribute('autocapitalize', 'none');
    input.spellcheck = false;
    input.required = true;
    const verify = node('button', 'Verify and link workout');
    verify.type = 'submit';
    controls.push(input, verify);
    form.append(label, input, verify);
    form.addEventListener('submit', event => {
      event.preventDefault();
      const id = input.value.trim();
      if (!id) { feedback.textContent = 'Enter the existing Hevy workout ID.'; input.focus(); return; }
      return run('Verifying the existing workout…', async () => {
        const result = await request('/reconcile', {hevy_workout_id:id});
        if (result?.state === 'remote_saved') feedback.textContent = 'Workout verified. Finish local records to complete the save.';
      });
    });
    reconcile.append(node('p', 'The logger checks that the existing workout matches your draft before linking it.'), form);
    const settings = node('a', 'Monitoring sync and settings');
    settings.href = '/#settings';
    settings.className = 'recovery-settings';
    box.append(feedback, lookup, reconcile, settings);
    for (const element of [retry, retryHint, first, corrected, lookup, reconcile]) element.hidden = true;
    main.querySelector('.app-header').after(box);
    main.setAttribute('data-save-recovery', '');
    if (initialStatus) render(initialStatus);
    else run('Checking save status…', () => request());
    if (focus) heading.focus();
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
  return {freeze,panel,dismiss,monitoring,noteFailure,correct};
})();
