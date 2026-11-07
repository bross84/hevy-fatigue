/* Host AI APIs; logger-owned requests still use trainingUrl. Never edits a plan. */
const WeeklyCoach = (() => {
  async function json(path,options) {
    const response=await fetch(path,options),data=await response.json();
    if(!response.ok)throw Error(typeof data.detail==='string'?data.detail:'Weekly review unavailable.');
    return data;
  }
  const openUrl=id=>'/?coaching_conversation='+encodeURIComponent(id)+'#ai';
  const endUrl=id=>'/?coaching_week='+encodeURIComponent(id)+'&coaching_kind=end#ai';
  async function run(planId,kind,sessionId=null,onStatus=()=>{},onPrepared=()=>{}) {
    onStatus('Preparing your weekly coaching context…');
    let view=await json('/api/ai/week-reviews',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({plan_id:planId,kind,session_id:sessionId})});
    onPrepared(view);
    const message=kind==='start'
      ? 'Review this planned training week before day 1. Use my confirmed motivation and note, daily check-ins, recent performance, actual spacing and previous coaching discussions. Explain whether to keep the plan or propose a change. Separate engagement from fatigue; ask a focused question where my goal or constraints matter. Do not apply programming changes.'
      : 'Review the completed training week like my remote coach. Compare the planned work with actual saved sessions, effort, motivation, check-ins and spacing. Revisit our opening discussion, explain what worked and what is uncertain, and propose the next week or phase for us to discuss. Ask focused follow-ups; do not apply changes.';
    return reviewPrepared(view,message,onStatus);
  }
  async function reviewPrepared(view,message,onStatus=()=>{},expectedSequence=0,retryPendingTurnId=null) {
    // A stale daily turn needs explicit Retry and the server's matching turn ID.
    if(view.turns.length!==expectedSequence)return view;
    if(retryPendingTurnId && view.retry_pending_turn_id!==retryPendingTurnId)return view;
    if(view.turns.some(turn=>!['failed','interrupted'].includes(turn.status) &&
      turn.id!==retryPendingTurnId))return view;
    const settings=await json('/api/settings/ai');
    if(!settings.configured)throw Error('Configure AI in Settings. Your check-in and workout logging remain available.');
    const model=localStorage.getItem('ai_preferred_model') || settings.default_model;
    if(!model)throw Error('Select a model in AI Coach first.');
    onStatus('AI Coach is reviewing your check-in and training context…');
    const response=await fetch('/api/ai/conversations/'+encodeURIComponent(view.id)+'/messages',{
      method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:crypto.randomUUID(),message,model,expected_sequence:expectedSequence,
        ...(retryPendingTurnId ? {retry_pending_turn_id:retryPendingTurnId} : {})})});
    if(response.status===409)return json('/api/ai/conversations/'+encodeURIComponent(view.id));
    if(!response.ok){const err=await response.json();throw Error(typeof err.detail==='string'?err.detail:'Weekly review failed.');}
    if(!response.body)throw Error('Review response interrupted. Open AI Coach to check its saved status.');
    const reader=response.body.getReader(),decoder=new TextDecoder();let buffer='',done=false;
    while(!done){
      const chunk=await reader.read();if(chunk.done)break;
      buffer+=decoder.decode(chunk.value,{stream:true});const lines=buffer.split('\n');buffer=lines.pop() || '';
      for(const line of lines){
        if(!line.startsWith('data:'))continue;
        const value=line.slice(5).trim();if(value==='[DONE]'){done=true;break;}
        try {const event=JSON.parse(value);if(event.error)throw Error(event.error.message || 'Review failed.');}
        catch(error){if(!(error instanceof SyntaxError))throw error;}
      }
    }
    if(!done)throw Error('Review interrupted. Open AI Coach to check it; no automatic resend.');
    return json('/api/ai/conversations/'+encodeURIComponent(view.id));
  }
  return {run,reviewPrepared,openUrl,endUrl};
})();
