/* The AI Coach's browser code, shared by the dashboard, the daily card and the logger.
   Host AI requests use /api/ai; logger-owned requests still use trainingUrl. It only reads
   and requests: whether a reply may be resent is decided by the server, and it never edits a plan. */
const AICoach = (() => {
  async function json(path,options) {
    const response=await fetch(path,options),data=await response.json();
    if(!response.ok)throw Error(typeof data.detail==='string'?data.detail:'Weekly review unavailable.');
    return data;
  }
  const openUrl=id=>'/?coaching_conversation='+encodeURIComponent(id)+'#ai';
  const endUrl=id=>'/?coaching_week='+encodeURIComponent(id)+'&coaching_kind=end#ai';
  async function reviewWeek(planId,kind,sessionId=null,onStatus=()=>{},onPrepared=()=>{}) {
    onStatus('Preparing your weekly coaching context…');
    let view=await json('/api/ai/week-reviews',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({plan_id:planId,kind,session_id:sessionId})});
    onPrepared(view);
    const message=kind==='start'
      ? 'Review this planned training week before day 1. Use my confirmed motivation and note, daily check-ins, recent performance, actual spacing and previous coaching discussions. Explain whether to keep the plan or propose a change. Separate engagement from fatigue; ask a focused question where my goal or constraints matter. Do not apply programming changes.'
      : 'Review the microcycle I just finished like my remote coach. Compare the planned work with actual saved sessions, effort, motivation, check-ins and spacing; a skipped day was not trained. Use the movement progress summary, and how my earlier saved proposals turned out, as context rather than conclusions. Revisit our opening discussion if there was one, explain what worked and what is uncertain, and propose the next microcycle or phase for us to discuss. Ask focused follow-ups; do not apply changes.';
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
    const done=await readStream(response,{fallback:'Review failed.'});
    if(!done)throw Error('Review interrupted. Open AI Coach to check it; no automatic resend.');
    return json('/api/ai/conversations/'+encodeURIComponent(view.id));
  }
  // Resolves true once the server sends [DONE]; false if the stream ends first.
  // Throws on an error event. Reply text is passed to onDelta as it arrives.
  async function readStream(response, {onDelta = () => {}, fallback = 'AI response failed.'} = {}) {
    const reader = response.body.getReader(), decoder = new TextDecoder();
    let buffer = '';
    while (true) {
      const chunk = await reader.read();
      if (chunk.done) return false;
      buffer += decoder.decode(chunk.value, {stream: true});
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';
      for (const line of lines) {
        if (!line.startsWith('data:')) continue;
        const value = line.slice(5).trim();
        if (value === '[DONE]') return true;
        let event;
        try { event = JSON.parse(value); } catch (error) { continue; }
        if (event.error) throw Error(event.error.message || fallback);
        const delta = event.choices?.[0]?.delta?.content || event.choices?.[0]?.text || '';
        if (delta) onDelta(delta);
      }
    }
  }
  return {reviewWeek,reviewPrepared,readStream,openUrl,endUrl};
})();
