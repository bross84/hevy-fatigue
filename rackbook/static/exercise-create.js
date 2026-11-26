/* Shared catalog editor. It never adds/replaces workout sets or copies performance history. */
const ExerciseCreate = (() => {
  const KEY = 'training.exerciseCreation.v1';
  let active = false;
  async function request(path, body) {
    const response = await fetch(trainingUrl(path), body === undefined ? {} : {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
    const data = await response.json();
    if (!response.ok) {
      const error = new Error(typeof data.detail === 'string' ? data.detail : 'Check the exercise details and try again.');
      error.status = response.status; throw error;
    }
    return data;
  }
  const node = (tag, text) => { const e=document.createElement(tag); if(text!=null)e.textContent=text; return e; };
  async function open({catalog = [], duplicate = false, onCreated}) {
    if (active) return;
    active = true;
    const dialog = node('dialog'); dialog.className='exercise-create';
    const form=node('form'), title=node('h2','Create exercise'), close=node('button','✕'), head=node('div');
    head.className='dialog-head';close.className='close-x';close.setAttribute('aria-label','Close');
    let closed=false;
    const cleanup=()=>{if(closed)return;closed=true;active=false;dialog.remove();};
    const closeDialog=()=>{dialog.close();cleanup();};
    close.type='button'; close.addEventListener('click',closeDialog);
    const message=node('p'); message.setAttribute('role','status');
    head.append(title,close);
    form.append(head,node('p','Saves the exercise in this app first, then adds a copy to Hevy. New movements start with their own history and strength reference.'));
    const fields={};
    function field(key,label,values) {
      const wrap=node('label',label), input=node(values?'select':'input'); input.name=key;
      if(values)for(const value of values){const o=node('option',value.replaceAll('_',' '));o.value=value;input.append(o);}
      else {input.type='text';input.maxLength=150;}
      input.required=true;wrap.append(input);form.append(wrap);fields[key]=input;return input;
    }
    const source=node('input');source.type='hidden';source.name='source_id';fields.source_id=source;form.append(source);
    const sourceLabel=node('label','Start from'), search=node('input');
    search.type='search';search.placeholder='Search exercises';search.autocomplete='off';
    sourceLabel.append(search);form.append(sourceLabel);
    const results=node('div');results.className='exercise-source-results';
    const sourceStatus=node('p');sourceStatus.setAttribute('aria-live','polite');
    form.append(results,sourceStatus);
    function setMode(value){
      duplicate=value;
      title.textContent=duplicate?'Duplicate exercise':'Create exercise';
      sourceLabel.hidden=results.hidden=sourceStatus.hidden=!duplicate;
      search.required=duplicate;
    }
    setMode(duplicate);
    function showResults(){
      results.replaceChildren();
      if(search.disabled)return;
      const query=search.value.trim().toLocaleLowerCase();
      if(!query){sourceStatus.textContent='Type to find an exercise to copy.';return;}
      const matches=catalog.filter(ex=>ex.title.toLocaleLowerCase().includes(query));
      sourceStatus.textContent=matches.length ? (matches.length>20?'Showing the first 20 matches. Type more to narrow the search.':'Choose an exercise to copy.') : 'No matching exercises.';
      for(const ex of matches.slice(0,20)){
        const button=node('button',ex.title);button.type='button';
        button.addEventListener('click',()=>{source.value=ex.id;search.value=ex.title;results.replaceChildren();source.dispatchEvent(new Event('change'));});
        results.append(button);
      }
    }
    const submit=node('button','Save and add to Hevy'); submit.type='submit';submit.disabled=true;
    const check=node('button','Check creation status');check.type='button';check.hidden=true;
    const reset=node('button','Edit and try again');reset.type='button';reset.hidden=true;
    dialog.append(form);document.body.append(dialog);dialog.showModal();
    dialog.addEventListener('close',cleanup,{once:true});
    dialog.addEventListener('cancel',event=>{event.preventDefault();closeDialog();});
    let options, saved=null, busy=false, enabled=false;
    const persist=()=>localStorage.setItem(KEY,JSON.stringify(saved));
    const lock=value=>{for(const input of Object.values(fields))input.disabled=value;search.disabled=value;if(value)results.replaceChildren();};
    try {
      options=await request('/exercise-creation/options');enabled=options.enabled;
      field('title','Exercise name');field('exercise_type','Exercise type',options.types);
      field('equipment_category','Equipment',options.equipment);field('muscle_group','Primary muscle',options.muscles);
      const secondary=field('other_muscles','Secondary muscles (optional)',options.muscles);secondary.multiple=true;secondary.required=false;secondary.size=5;
      for(const option of secondary.options)option.selected=false;
      form.append(message,submit,check,reset);
      try {saved=JSON.parse(localStorage.getItem(KEY)||'null');}catch(e){message.textContent='Could not read the saved creation form.';}
      // A pending remote attempt must be recovered from either entry point.
      // An unsent form from the other action must not turn Create into Duplicate.
      if(saved?.sent)setMode(!!saved.body?.source_id);
      else if(saved?.body && (saved.duplicate??!!saved.body.source_id)!==duplicate)saved=null;
      const fill=body=>{for(const [key,input] of Object.entries(fields)){if(key==='other_muscles'){for(const o of input.options)o.selected=(body[key]||[]).includes(o.value);}else input.value=body[key]??'';}search.value=catalog.find(ex=>String(ex.id)===String(body.source_id))?.title||'';};
      if(saved?.body){fill(saved.body);lock(saved.sent);check.hidden=!saved.sent;if(saved.sent)message.textContent='A previous creation is awaiting confirmation. Check its status before creating another exercise.';}
      else if(duplicate){title.textContent='Duplicate exercise';message.textContent='Search under Start from and choose an exercise to copy its details.';search.focus();}
      submit.disabled=!enabled||!!saved?.sent;
      if(!enabled)message.textContent='Creating exercises is disabled in this preview or while Hevy writes are disabled.';
      search.addEventListener('input',()=>{
        source.value='';search.setCustomValidity('Choose an exercise from the search results.');showResults();remember();
      });
      source.addEventListener('change',async()=>{
        search.setCustomValidity('');
        if(!source.value){submit.disabled=!enabled;return;}
        submit.disabled=true;busy=true;lock(true);
        try {const ex=await request('/exercise-creation/template/'+encodeURIComponent(source.value));
          fill({source_id:source.value,title:ex.title+' (copy)',exercise_type:ex.type,equipment_category:ex.equipment,muscle_group:ex.primary_muscle_group,other_muscles:ex.secondary_muscle_groups});
          remember();sourceStatus.textContent='Copying '+search.value;message.textContent='Edit the name and details. History, e1RM and training max are not copied.';
        }catch(e){message.textContent=e.message;search.setCustomValidity('Could not load this exercise. Search and select it again.');}finally{busy=false;lock(false);submit.disabled=!enabled;}
      });
      function read(){return Object.fromEntries(Object.entries(fields).map(([k,input])=>[k,k==='other_muscles'?[...input.selectedOptions].map(o=>o.value):k==='source_id'?(input.value||null):input.value.trim()]));}
      function remember(){if(saved?.sent)return; saved={body:{...read(),request_id:saved?.body?.request_id||trainingUUID()},duplicate,sent:false};try{persist();}catch(e){submit.disabled=true;message.textContent='Browser storage is unavailable. Creation is blocked so a network interruption cannot lose its identity.';}}
      form.addEventListener('input',remember);form.addEventListener('change',remember);
      async function outcome(result){
        if(result.state==='complete'){
          localStorage.removeItem(KEY);message.textContent='Exercise created. It is now available in the picker.';
          await onCreated?.(result);closeDialog();return;
        }
        check.hidden=false;lock(true);submit.disabled=true;
        reset.hidden=result.state!=='rejected';
        message.textContent=result.state==='rejected'?'The exercise is saved in this app, but Hevy did not accept it. Check your key, account limits and exercise details, then edit and try again.'
          :'Creation is '+result.state+'. Check status to look for the matching exercise; nothing will be posted again.';
      }
      form.addEventListener('submit',async e=>{
        if(duplicate&&!source.value)search.setCustomValidity('Choose an exercise from the search results.');
        e.preventDefault();if(busy||!enabled||saved?.sent||!form.reportValidity())return;
        remember();if(!saved)return;
        saved.sent=true;try{persist();}catch(e){saved.sent=false;message.textContent='Could not save the creation identity. Nothing was sent.';return;}
        busy=true;lock(true);submit.disabled=true;message.textContent='Creating exercise…';
        try{await outcome(await request('/exercise-creation',saved.body));}
        catch(e){message.textContent=e.message;check.hidden=false;if([400,403,422].includes(e.status)){saved.sent=false;persist();lock(false);submit.disabled=!enabled;}}
        finally{busy=false;}
      });
      check.addEventListener('click',async()=>{
        if(busy||!saved)return;busy=true;check.disabled=true;
        try{await outcome(await request('/exercise-creation/'+saved.body.request_id+'/reconcile',{}));}
        catch(e){message.textContent=e.message;if(e.status===404){saved.sent=false;persist();lock(false);submit.disabled=!enabled;message.textContent='No attempt was recorded. You can submit again using the same creation ID.';}}
        finally{busy=false;check.disabled=false;}
      });
      reset.addEventListener('click',()=>{// Same ID: the app's saved copy is updated and resent, not duplicated.
        saved.sent=false;persist();lock(false);submit.disabled=!enabled;check.hidden=reset.hidden=true;});
    }catch(e){form.append(message);message.textContent=e.message;}
  }
  return {open};
})();
