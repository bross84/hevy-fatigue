/* Required engagement check-in. No fatigue, trial or loading calculations. */
const SessionMotivation = (() => {
  const levels=['Eager','Willing','Neutral','Reluctant','Dreading it'],states=new Map();
  const started=d=>d.exercises.some(ex=>ex.trialStarted||ex.sets.some(s=>s.type!=='warmup'&&s.done));
  const signature=d=>JSON.stringify({motivation:d.motivation,plan:d.planned_session || null,start:d.startedAt});
  const ready=d=>!!d.motivation&&Number.isInteger(d.motivation.level)&&d.motivation.level>=0&&d.motivation.level<=4&&d.checkin_confirmation?.signature===signature(d);
  async function ensureSaved(draft) {
    if(draft.frozenSave)return;
    if(!ready(draft))throw Error('Choose your motivation and confirm the pre-training check-in.');
    const response=await fetch(trainingUrl('/session-checkins'),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
      session_id:draft.client_workout_id,workout_start:draft.startedAt,motivation:draft.motivation,planned_session:draft.planned_session || null})});
    const data=await response.json();if(!response.ok)throw Error(typeof data.detail==='string'?data.detail:'Could not save the check-in.');
    return data;
  }
  function mount(draft,box,save,onState=()=>{}) {
    box.replaceChildren();
    let state=states.get(draft.client_workout_id);
    if(!state){state={pending:false,reviewRunning:false,reviewChecked:false,message:'',view:null};states.set(draft.client_workout_id,state);}
    const node=(tag,text)=>{const n=document.createElement(tag);if(text!=null)n.textContent=text;return n;};
    const heading=node('h3','Pre-training check-in'),label=node('label','How do you feel about training today?');label.htmlFor='motivation-level';
    const level=node('select');level.id='motivation-level';level.required=true;level.append(new Option('Choose motivation (required)',''));
    levels.forEach((text,i)=>level.append(new Option(text,String(i))));level.value=draft.motivation==null?'':String(draft.motivation.level);
    const noteLabel=node('label','Anything else? (optional)');noteLabel.htmlFor='motivation-note';
    const note=node('input');note.id='motivation-note';note.type='text';note.maxLength=500;note.value=draft.motivation?.note || '';
    const hint=node('p','Motivation is required before working sets. It measures engagement, separately from tiredness, recovery and your fatigue score.');hint.className='hint';
    const confirm=node('button');confirm.type='button';confirm.id='confirmMotivation';
    const status=node('p');status.className='hint';status.setAttribute('role','status');
    const reviewBox=node('div');reviewBox.id='weeklyOpeningReview';
    function paint() {
      const locked=Boolean(draft.frozenSave)||state.pending;
      level.disabled=note.disabled=locked;confirm.disabled=locked||level.value==='';
      confirm.textContent=ready(draft)?'Check-in confirmed':'Confirm check-in';
      status.textContent=state.message || (ready(draft)?'Check-in confirmed. Your workout remains yours to adjust.':'Choose motivation, add a note if useful, then confirm.');
      reviewBox.replaceChildren();
      if(draft.weekly_review_id){const link=node('a','Discuss this week with AI Coach');link.href=AICoach.openUrl(draft.weekly_review_id);reviewBox.append(link);}
      const turn=state.view?.turns?.at(-1);
      if(turn){
        const details=node('details');details.append(node('summary','Before day 1 · '+turn.status));
        if(turn.response){const text=node('p',turn.response);text.style.whiteSpace='pre-wrap';details.append(text);}
        if(turn.status!=='complete')details.append(node('p','Open AI Coach to check or discuss this attempt. It will not be automatically resent.'));
        reviewBox.append(details);
      }
      onState();
    }
    state.paint=paint;
    async function opening(result) {
      if(state.reviewRunning||state.reviewChecked||!draft.planned_session)return;
      if(!result?.weekly_review_eligible)return;
      state.reviewChecked=true;state.reviewRunning=true;
      try {
        if(started(draft)){
          if(draft.weekly_review_id){const r=await fetch('/api/ai/conversations/'+encodeURIComponent(draft.weekly_review_id));if(r.ok)state.view=await r.json();}
          else state.message='Training has started; no opening assessment will be presented as pre-training evidence. Discuss this session in AI Coach.';
        } else state.view=await AICoach.reviewWeek(draft.planned_session.mesocycle_id,'start',draft.client_workout_id,
          text=>{state.message=text;state.paint();},view=>{draft.weekly_review_id=view.id;save();state.paint();});
        if(state.view)state.message='Opening review '+(state.view.turns.at(-1)?.status || 'saved')+'. Open AI Coach to discuss any proposals. No programming changes were applied.';
      }catch(error){state.message=error.message+' Logging can continue; no automatic resend.';}
      finally{state.reviewRunning=false;state.paint();}
    }
    function change(){
      if(draft.frozenSave||state.pending)return;
      if(level.value==='')delete draft.motivation;
      else draft.motivation={level:Number(level.value),note:note.value,recorded_at:new Date().toISOString(),
        timing:started(draft)||draft.motivation?.timing==='after_working_sets'?'after_working_sets':'before_working_sets'};
      delete draft.checkin_confirmation;state.message='';save();paint();
    }
    level.addEventListener('change',change);note.addEventListener('input',change);
    confirm.addEventListener('click',async()=>{
      if(draft.frozenSave||state.pending||!level.reportValidity())return;
      if(ready(draft))return;
      if(!draft.motivation)change();
      delete draft.motivation.reason;
      draft.checkin_confirmation={signature:signature(draft),confirmed_at:new Date().toISOString()};
      if(save()===false){delete draft.checkin_confirmation;state.message='Could not preserve this check-in. Try again before training.';paint();return;}
      state.pending=true;state.message='Saving your check-in…';paint();let result;
      try{result=await ensureSaved(draft);state.message='Check-in saved. Motivation does not affect your fatigue score.';}
      catch(error){state.message='Confirmed on this device. '+error.message+' It will be saved before workout upload.';}
      finally{state.pending=false;paint();}
      if(result)opening(result);
    });
    for(const control of [level,note])control.style.cssText='display:block;width:100%;box-sizing:border-box;margin:6px 0 12px';
    box.append(heading,label,level,noteLabel,note,hint,confirm,status,reviewBox);paint();
    if(ready(draft)&&!draft.frozenSave&&!state.pending&&!state.reviewChecked&&draft.planned_session){
      ensureSaved(draft).then(opening).catch(error=>{state.message=error.message;state.paint();});
    }
  }
  return {mount,ready,ensureSaved};
})();
