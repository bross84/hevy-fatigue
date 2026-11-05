/* Preserved evidence and read-only display; never modifies weight calculations. */
const SessionCapture = (() => {
  let serial = 0;
  const id = () => globalThis.crypto?.randomUUID?.() || 'set-' + Date.now() + '-' + (++serial);
  const number = value => value === '' || value == null || !Number.isFinite(Number(value)) ? null : Number(value);
  function start(draft, source, chart, revision = null) {
    draft.prescription = {version:1, source, name:draft.title, plan_revision:revision,
      plan_id:draft.planned_session?.mesocycle_id || null, session_id:draft.planned_session?.session_id || null,
      rpe_chart:[...chart].map(([key, percentage])=>({rpe:Number(key.split('|')[0]),reps:Number(key.split('|')[1]),percentage})),
      exercises:source==='ad_hoc'?[]:draft.exercises.map(ex=>({id:ex.id,exercise_template_id:ex.template_id,title:ex.title,notes:ex.notes || '',
        sets:ex.sets.map(s=>({id:s.review_id ||= id(),reps:number(s.reps),rpe:number(s.rpe),weight_kg:number(s.kg),type:s.type,ts:Boolean(s.ts)}))}))};
  }
  function complete(ex, s) {
    s.review = {set_id:s.review_id ||= id(), exercise_id:ex.id ||= id(),
      suggested_weight_kg:ex.ref.autoWeights===false?null:number(s.autoSuggestion), manual_weight:Boolean(s.manual),
      ls_enabled:ex.ref.autoWeights!==false&&Boolean(ex.ref.ls), basis:ex.ref.autoWeights===false?'manual':ex.ref.basis || 'e1rm',
      completed_at:new Date().toISOString(),
      rpe_source:s.actualSource || 'unknown', actual_percentage:null};
  }
  function evidence(s, percentage) {
    return s.review ? {...s.review, rpe_source:s.arpe ? (s.actualSource || 'unknown') : 'unrated', actual_percentage:percentage || null} : null;
  }
  return {start, complete, evidence};
})();

const SessionReviewUI = (() => {
  const requests = new WeakMap();
  const node = (tag, text) => {const n=document.createElement(tag);if(text!=null)n.textContent=text;return n;};
  const amount = n => n == null ? 'unknown' : String(Math.round(n*10)/10);
  async function show(workoutId, box) {
    const request = (requests.get(box) || 0) + 1;
    requests.set(box,request);
    box.replaceChildren(node('p','Loading session review…'));
    try {
      const response=await fetch(trainingUrl('/session-reviews/')+encodeURIComponent(workoutId));
      if(!response.ok)throw Error();
      const data=await response.json();
      if(request!==requests.get(box) || !box.isConnected)return;
      box.replaceChildren(node('h2','Session review'));
      if(!data.available){box.append(node('p',data.reason));return;}
      const review=data.review;
      box.append(node('p',review.prescription_source==='ad_hoc'?'Ad hoc workout: no initial session plan to compare.':'Compared with the prescription captured when this workout was loaded.'));
      if(data.prescription?.name)box.append(node('p','Original session: '+data.prescription.name));
      for(const ex of review.movements){
        const unit=ex.weight_unit || 'kg', weight=n=>amount(n==null?null:n*(unit==='lb'?2.20462262185:1));
        const section=node('section');section.append(node('h3',ex.title));
        section.append(node('p',ex.completed_sets+' working sets completed · '+amount(ex.planned_sets)+' originally planned · '+amount(ex.omitted_sets)+' omitted · '+amount(ex.added_sets)+' added.'));
        section.append(node('p','Reps: '+amount(ex.completed_reps)+' completed / '+amount(ex.planned_reps)+' originally planned.'));
        section.append(node('p','Opening / final working-set e1RM: '+weight(ex.opening_e1rm_kg)+' / '+weight(ex.last_e1rm_kg)+' '+unit+'.'));
        if(ex.change_pct!=null)section.append(node('p','Like-for-like endpoint change: '+amount(ex.change_pct)+'%.'));
        const detail=node('details');detail.append(node('summary','Set evidence'));
        const list=node('ul');
        for(const s of ex.sets)list.append(node('li',s.role+(s.set_type&&s.set_type!=='normal'?' ('+s.set_type+')':'')+': '+weight(s.weight_kg)+' '+unit+' × '+amount(s.actual_reps)+
          ' · original '+amount(s.planned_reps)+' reps @'+amount(s.planned_rpe)+
          (s.planned_weight_kg!=null?' at '+weight(s.planned_weight_kg)+' '+unit:'')+
          ' · final target @'+amount(s.target_rpe)+' / actual @'+amount(s.actual_rpe)+' ('+s.rpe_source.replaceAll('_',' ')+')'+
          ' · suggested '+weight(s.suggested_weight_kg)+' '+unit+(s.manual_weight?' · fixed/manual weight':'')+
          ' · estimated 1RM '+weight(s.e1rm_kg)+' '+unit+
          ' · LSe1RM '+(s.ls_enabled==null?'unknown':s.ls_enabled?'on':'off')));
        detail.append(list);section.append(detail);
        for(const note of ex.notes)section.append(node('p',note));
        box.append(section);
      }
      for(const note of review.notes)box.append(node('p',note));
    } catch(error) {
      if(request===requests.get(box))box.replaceChildren(node('p','Session review unavailable. Your saved workout is unaffected; reopen the review from Recent.'));
    }
  }
  function saved(saved){const box=document.getElementById('sessionReview');if(box)show(saved.hevy_workout_id || saved.id,box);}
  function button(workoutId, box){const b=node('button','Session review');b.type='button';const detail=node('section');
    b.addEventListener('click',()=>show(workoutId,detail));box.append(b,detail);}
  return {show,saved,button};
})();
