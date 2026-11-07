/* Daily interpretation is separate from saving ratings, scoring and programming. */
const DailyCoach = (() => {
  const states=new Map(), active=new Map(), revisions=new Map();
  let visibleDate=null, preferredDate=null;
  async function json(path,options){
    const response=await fetch(path,options),data=await response.json();
    if(!response.ok)throw Error(typeof data.detail==='string'?data.detail:'Daily interpretation unavailable.');
    return data;
  }
  function draw(){
    const box=document.getElementById('daily-coach-review');
    if(!box||!visibleDate)return;
    const state=states.get(visibleDate)||{};
    box.replaceChildren();
    const title=document.createElement('strong');title.textContent='AI daily interpretation · '+visibleDate;box.append(title);
    const status=document.createElement('p');status.textContent=state.status || 'No interpretation saved for this check-in.';status.setAttribute('role','status');box.append(status);
    if(state.view){
      const turns=state.view.turns||[],first=turns[0];
      if(first?.response){const response=document.createElement('p');response.textContent=first.response;response.style.whiteSpace='pre-wrap';box.append(response);}
      const detail=document.createElement('small');
      detail.textContent='Evidence saved '+new Date(state.view.created_at).toLocaleString()+(first?' · '+first.model+' · '+first.status:'')+'. Proposals only; programming is unchanged.';box.append(detail);
      const link=document.createElement('a');link.href=WeeklyCoach.openUrl(state.view.id);link.textContent='Discuss with AI Coach';link.style.display='block';box.append(link);
    }
    // Never auto-retry partial/pending/failed turns. Open the saved conversation.
    if(!state.busy && !(state.view?.turns||[]).length){
      const button=document.createElement('button');button.type='button';button.className='btn btn-secondary';button.textContent='Interpret this check-in';
      const date=visibleDate;button.addEventListener('click',()=>run(date));box.append(button);
    }
  }
  function update(date,values){states.set(date,{...states.get(date),...values});draw();}
  function mount(date,hasCheckin=true){
    const box=document.getElementById('daily-coach-review');
    if(box)box.hidden=!hasCheckin&&!preferredDate;
    if(!hasCheckin&&!preferredDate)return;
    date=preferredDate||date;
    visibleDate=date;draw();
    const revision=(revisions.get(date)||0)+1;revisions.set(date,revision);
    // Restore only. Opening/reloading the dashboard never makes a paid call.
    json('/api/ai/daily-reviews/'+encodeURIComponent(date)).then(view=>{
      if(!active.has(date)&&revisions.get(date)===revision)update(date,{view,status:view?describe(view):'No interpretation saved for this check-in.'});
    }).catch(()=>{if(!active.has(date)&&revisions.get(date)===revision)update(date,{status:'Could not load the saved interpretation. Your check-in and scores remain available.'});});
  }
  function describe(view){
    const first=view.turns?.[0];
    if(!first)return 'Context saved. AI has not interpreted it yet.';
    return first.status==='complete'?'Saved interpretation.':first.status==='pending'?'Response pending or interrupted. Open AI Coach to check it; no automatic resend.':'Response '+first.status+'. Open AI Coach to discuss or retry explicitly.';
  }
  function run(date){
    visibleDate=date;preferredDate=date;
    const box=document.getElementById('daily-coach-review');if(box)box.hidden=false;
    // A second saved edit may arrive while the old interpretation is running.
    // Recheck current server identity after it finishes; cached turns prevent a
    // duplicate paid request when the ratings did not change.
    if(active.has(date)){draw();return active.get(date).then(()=>run(date));}
    revisions.set(date,(revisions.get(date)||0)+1);
    update(date,{busy:true,status:'Check-in saved. Preparing your daily interpretation…'});
    const task=(async()=>{
      try{
        const view=await json('/api/ai/daily-reviews',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({date})});
        update(date,{view});
        const result=await WeeklyCoach.reviewPrepared(view,
          'Interpret this daily check-in briefly. Compare the current absolute ratings with my supplied personal historical range, recent check-ins, training spacing and performance. Explain what matters, what is uncertain and what to watch at my next session. Low fatigue is not a reason on its own to add volume. Keep motivation separate from fatigue. Do not change programming.',
          status=>update(date,{status}));
        update(date,{view:result,status:describe(result)});
      }catch(error){
        update(date,{status:'Check-in saved. '+error.message});
        const id=states.get(date)?.view?.id;
        if(id){try{const view=await json('/api/ai/conversations/'+encodeURIComponent(id));update(date,{view});}catch(_){/* preserve captured identity */}}
      }finally{update(date,{busy:false});active.delete(date);}
    })();
    active.set(date,task);return task;
  }
  function clear(date){
    states.delete(date);revisions.set(date,(revisions.get(date)||0)+1);
    if(preferredDate===date)preferredDate=null;
    if(visibleDate===date){visibleDate=null;const box=document.getElementById('daily-coach-review');if(box)box.hidden=true;}
  }
  return {mount,run,clear};
})();
