/* Optional session context. No score calculations or workout-set changes. */
const SessionMotivation = (() => {
  const levels = ['Eager', 'Willing', 'Neutral', 'Reluctant', 'Dreading it'];
  const reasons = [['fatigue','Tired / poor recovery'],['stale','Training feels stale'],['life_stress','Time / life stress'],['other','Other']];
  function mount(draft, box, save) {
    box.replaceChildren();
    const node = (tag,text) => {const n=document.createElement(tag);if(text!=null)n.textContent=text;return n;};
    const heading=node('h3','Pre-training check-in');
    const label=node('label','How do you feel about training today?');
    label.htmlFor='motivation-level';
    const level=node('select');level.id='motivation-level';
    level.append(new Option('Not answered (optional)',''));
    levels.forEach((text,index)=>level.append(new Option(text,String(index))));
    level.value=draft.motivation==null?'':String(draft.motivation.level);
    const reasonLabel=node('label','Reason (optional)');reasonLabel.htmlFor='motivation-reason';
    const reason=node('select');reason.id='motivation-reason';reason.append(new Option('No reason selected',''));
    reasons.forEach(([id,text])=>reason.append(new Option(text,id)));reason.value=draft.motivation?.reason || '';
    const noteLabel=node('label','Anything else? (optional)');noteLabel.htmlFor='motivation-note';
    const note=node('input');note.id='motivation-note';note.type='text';note.maxLength=500;note.value=draft.motivation?.note || '';
    const hint=node('p','Optional. Saved with this workout for AI reviews; separate from your fatigue score.');hint.className='hint';
    const timing=node('p');timing.className='hint';
    function updateState() {
      level.disabled=Boolean(draft.frozenSave);
      reason.disabled=note.disabled=Boolean(draft.frozenSave)||level.value==='';
      timing.textContent=draft.motivation?.timing==='after_working_sets'
        ? 'Updated after a working set was checked off; recorded as a later response.'
        : draft.motivation ? 'Answered before a working set was marked complete.' : '';
    }
    function change() {
      if(draft.frozenSave)return;
      if(level.value==='') {delete draft.motivation;reason.value='';note.value='';}
      else {
        const started=draft.motivation?.timing==='after_working_sets'||draft.exercises.some(ex=>ex.trialStarted||ex.sets.some(s=>s.type!=='warmup'&&s.done));
        draft.motivation={level:Number(level.value),reason:reason.value || null,note:note.value,
          recorded_at:new Date().toISOString(),timing:started?'after_working_sets':'before_working_sets'};
      }
      save();updateState();
    }
    level.addEventListener('change',change);reason.addEventListener('change',change);note.addEventListener('input',change);
    for(const control of [level,reason,note])control.style.cssText='display:block;width:100%;box-sizing:border-box;margin:6px 0 12px';
    box.append(heading,label,level,reasonLabel,reason,noteLabel,note,hint,timing);updateState();
  }
  return {mount};
})();
