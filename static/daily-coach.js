/* Daily interpretation is separate from saving ratings, scoring and programming. */
const DailyCoach = (() => {
  const states=new Map(), active=new Map(), revisions=new Map();
  let visibleDate=null, preferredDate=null;
  async function json(path,options){
    const response=await fetch(path,options),data=await response.json();
    if(!response.ok)throw Error(typeof data.detail==='string'?data.detail:'Daily interpretation unavailable.');
    return data;
  }
  function displayedTurn(view){
    return view?.turns.find(turn=>turn.status==='complete') || view?.turns.at(-1);
  }
  function canRetry(view){
    return !!view?.retry_pending_turn_id ||
      (!!view?.turns.length && view.turns.every(turn=>['failed','interrupted'].includes(turn.status)));
  }
  function savedStartFailure(view){
    if(!view || view.turns.length)return false;
    try{return localStorage.getItem('daily-coach-start-failed:'+view.id)==='1';}
    catch(_){return false;}
  }
  function setStartFailure(view,failed){
    if(!view || view.turns.length)return;
    try{
      const key='daily-coach-start-failed:'+view.id;
      if(failed)localStorage.setItem(key,'1');
      else localStorage.removeItem(key);
    }catch(_){/* In-memory status remains available. */}
  }
  function draw(){
    const box=document.getElementById('daily-coach-review');
    if(!box||!visibleDate)return;
    const state=states.get(visibleDate)||{};
    box.replaceChildren();
    const body=document.createElement('div');
    box.append(body);
    const title=document.createElement('h2');
    title.textContent='AI training recommendation · '+visibleDate;
    body.append(title);
    const recommendation=state.view?.daily_recommendation;
    if(recommendation){
      const action=document.createElement('strong');
      action.className='daily-coach-action';
      action.textContent=recommendation.label;
      body.append(action);
      const reason=document.createElement('p');
      reason.textContent=recommendation.reason;
      body.append(reason);
    }else{
      const status=document.createElement('p');
      status.textContent=state.status || 'Checking for a saved recommendation…';
      status.setAttribute('role','status');
      body.append(status);
    }
    if(state.view){
      const link=document.createElement('a');
      link.href="/?coaching_conversation="+encodeURIComponent(state.view.id)+"#ai";
      link.textContent='Discuss with AI Coach';
      box.append(link);
    }
    if(!state.busy && (canRetry(state.view) || (state.failed && !state.view?.turns.length))){
      const button=document.createElement('button');
      button.type='button';
      button.className='btn btn-secondary';
      button.textContent='Retry';
      const date=visibleDate;
      button.addEventListener('click',()=>run(date,{id:state.view?.id,sequence:state.view?.turns.length || 0,pendingTurnId:state.view?.retry_pending_turn_id}));
      body.append(button);
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
    return json('/api/ai/daily-reviews/'+encodeURIComponent(date)).then(view=>{
      if(active.has(date)||revisions.get(date)!==revision)return;
      const failed=savedStartFailure(view) || (!view && states.get(date)?.failed);
      if(!view?.turns.length && !failed)return run(date);
      update(date,{view,failed,status:failed?'Interpretation could not start. Retry when AI is available.':describe(view)});
    }).catch(()=>{
      if(!active.has(date)&&revisions.get(date)===revision)
        update(date,{failed:true,status:'Could not load the saved interpretation.'});
    });
  }
  function describe(view){
    const turn=displayedTurn(view);
    if(!turn)return 'Preparing your daily interpretation…';
    if(turn.status==='complete')return 'Open AI Coach to view the saved review.';
    if(view.retry_pending_turn_id)return 'The earlier request has been pending for at least five minutes. Retry to send a new request using this check-in.';
    if(turn.status==='pending')return 'AI Coach is preparing a response. Reload to check its status.';
    return 'Response '+turn.status+'. You can retry the interpretation.';
  }
  function run(date,retry=null){
    visibleDate=date;preferredDate=date;
    const box=document.getElementById('daily-coach-review');if(box)box.hidden=false;
    // A second saved edit may arrive while the old interpretation is running.
    // Recheck current server identity after it finishes; cached turns prevent a
    // duplicate paid request when the ratings did not change.
    if(active.has(date)){draw();return active.get(date).then(()=>run(date,retry));}
    revisions.set(date,(revisions.get(date)||0)+1);
    update(date,{busy:true,failed:false,view:null,status:'Check-in saved. Preparing your daily interpretation…'});
    const task=(async()=>{
      try{
        const view=await json('/api/ai/daily-reviews',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({date})});
        update(date,{view});
        const sameReview=retry && (!retry.id || retry.id===view.id);
        if(!sameReview && savedStartFailure(view)){
          update(date,{failed:true,status:'Interpretation could not start. Retry when AI is available.'});
          return;
        }
        setStartFailure(view,false);
        if(typeof AICoach==='undefined' || typeof AICoach.reviewPrepared!=='function'){
          throw Error('AI Coach did not finish updating. Reload this page, then select Retry.');
        }
        const result=await AICoach.reviewPrepared(view,
          'What should I do at my next training session?',
          status=>update(date,{status}),sameReview?retry.sequence:0,sameReview?retry.pendingTurnId:null);
        update(date,{view:result,status:describe(result)});
      }catch(error){
        update(date,{failed:true,status:'Check-in saved. '+error.message});
        const id=states.get(date)?.view?.id;
        if(id){
          try{
            const view=await json('/api/ai/conversations/'+encodeURIComponent(id));
            setStartFailure(view,true);
            update(date,{view});
          }catch(_){/* Retry rechecks the conversation before sending. */}
        }
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
