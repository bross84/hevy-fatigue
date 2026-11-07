/* View-only workspace. The logger owns sets, calculations, timers and save recovery. */
const LoggerLayout = (() => {
  let hooks, selectedId = null, detached = null, outlineKey = '';
  let inlineExerciseId = null;
  const wide = matchMedia('(min-width: 1900px)');
  const desktop = matchMedia('(min-width: 1100px)');
  const mobile = matchMedia('(max-width: 767px)');
  const mobileControls = new WeakMap();
  const byId = id => document.getElementById(id);
  const node = (tag, cls, text) => {
    const element = document.createElement(tag);
    if (cls) element.className = cls;
    if (text != null) element.textContent = text;
    return element;
  };
  const draft = () => hooks?.getDraft();
  const selected = () => draft()?.exercises.find(ex => ex.id === selectedId);
  const counts = ex => [ex.sets.filter(s => s.done).length, ex.sets.length];

  function release(id) {
    if (!detached || (id != null && detached.id !== id)) return;
    // Return the same live control before its exercise is replaced or the viewport narrows.
    const card = hooks.getCard(detached.id);
    if (card === detached.card && card?.isConnected) card.querySelector('.exright').append(detached.element);
    else detached.element.remove();
    detached = null;
  }

  function loaderFor(id) { return detached?.id === id ? detached.element : null; }

  function releaseMotivation(id) {
    if (id != null && inlineExerciseId !== id) return null;
    const form = byId('sessionMotivation'), home = byId('sessionMotivationHome');
    if (form.parentElement === home) return null;
    const focused = form.contains(document.activeElement) ? document.activeElement : null;
    home.append(form);
    return focused;
  }

  function updateMotivation() {
    const current = draft();
    const home = byId('sessionMotivationHome'), form = byId('sessionMotivation');
    const required = Boolean(current && typeof SessionMotivation !== 'undefined' && !SessionMotivation.ready(current));
    const blocked = mobile.matches && required;
    let inlineRow = null, returnFocus = null;
    for (const ex of current?.exercises || []) {
      const card = hooks.getCard(ex.id), controls = mobileControls.get(card);
      if (!controls) continue;
      const rows = [...card.querySelectorAll('.set[data-working]')];
      const next = rows.find(row => !row.classList.contains('done'));
      const open = blocked && !current.frozenSave && !ex.collapsed && inlineExerciseId === ex.id && next;
      if (open) inlineRow = next;
      if (inlineExerciseId === ex.id) returnFocus = next?.querySelector('.tick');
      if (blocked && next && controls.gate.parentElement !== next) next.insertBefore(controls.gate, next.querySelector('.tick'));
      controls.gate.hidden = !(blocked && next);
      controls.reason.textContent = current.frozenSave
        ? 'This workout is pending save recovery.' : 'Confirm motivation before working sets.';
      controls.trigger.hidden = Boolean(current.frozenSave);
      controls.trigger.textContent = open ? 'Close' : 'Check in';
      controls.trigger.setAttribute('aria-expanded', String(Boolean(open)));
      for (const row of rows) {
        const tick = row.querySelector('.tick');
        row.classList.toggle('next-working-set', row === next);
        tick.disabled = Boolean(blocked && !row.classList.contains('done'));
        if (tick.disabled) tick.setAttribute('aria-describedby', controls.reason.id);
        else tick.removeAttribute('aria-describedby');
      }
    }
    if (inlineRow) {
      home.hidden = true;
      if (form.parentElement !== inlineRow) inlineRow.insertBefore(form, inlineRow.querySelector('.tick'));
    } else {
      home.hidden = false;
      inlineExerciseId = null;
      const focused = releaseMotivation();
      if (focused && !mobile.matches) focused.focus({preventScroll: true});
      else if (!required) returnFocus?.focus();
    }
  }

  function positionAdvice(card) {
    const controls = mobileControls.get(card);
    if (!controls?.advice) return;
    const {advice, disclosure} = controls;
    if (mobile.matches && advice.parentElement !== disclosure) disclosure.append(advice);
    else if (!mobile.matches && advice.parentElement === disclosure) {
      const left = card.querySelector('.exleft');
      left.insertBefore(advice, left.querySelector('.refbar'));
    }
    disclosure.hidden = !mobile.matches || !card.querySelector('.set[data-working]');
  }

  function renderPrevious(ex) {
    const box = byId('loggerPrevious');
    box.replaceChildren();
    const state = ex.ref?.state;
    if (!state) { box.append(node('p', 'muted', 'Loading previous performance…')); return; }
    if (state.error) { box.append(node('p', 'muted', 'Previous performance unavailable')); return; }
    const sets = state.previous || [];
    if (!sets.length) { box.append(node('p', 'muted', 'No previous sets available')); return; }
    const table = node('table');
    const caption = node('caption', 'muted', 'Previous sets · ' + hooks.unitFor(ex.ref));
    table.append(caption);
    const body = node('tbody');
    let work = 0, warm = 0;
    for (const set of sets) {
      const tr = node('tr');
      const label = set.type === 'warmup' ? 'Warm-up ' + (++warm) : 'Set ' + (++work);
      const weight = set.weight_lb == null ? null : Number(set.weight_lb);
      const display = weight == null || !Number.isFinite(weight) ? '—' :
        hooks.format(hooks.unitFor(ex.ref) === 'kg' ? weight / 2.20462262185 : weight);
      tr.append(node('th', null, label), node('td', null, display + ' × ' + (set.reps ?? '—') +
        (set.rpe == null ? '' : ' @ ' + set.rpe)));
      body.append(tr);
    }
    table.append(body); box.append(table);
  }

  function updateOutline(exercises) {
    const outline = byId('loggerOutline');
    const key = JSON.stringify(exercises.map(ex => ex.id));
    if (key !== outlineKey) {
      outline.replaceChildren();
      for (const ex of exercises) {
        const button = node('button', 'logger-outline-item'); button.type = 'button';
        button.append(node('span', 'logger-outline-name'), node('span', 'logger-outline-count'));
        button.addEventListener('click', () => {
          selectedId = ex.id;
          if (ex.collapsed) { ex.collapsed = false; hooks.save(); hooks.render(); }
          update();
          hooks.getCard(ex.id)?.scrollIntoView({block: 'nearest', behavior: 'instant'});
        });
        outline.append(button);
      }
      outlineKey = key;
    }
    let total = 0, done = 0;
    exercises.forEach((ex, index) => {
      const [completed, size] = counts(ex); total += size; done += completed;
      const button = outline.children[index];
      button.querySelector('.logger-outline-name').textContent = (index + 1) + '. ' + ex.title;
      button.querySelector('.logger-outline-count').textContent = completed + '/' + size;
      button.setAttribute('aria-current', ex.id === selectedId ? 'true' : 'false');
      button.setAttribute('aria-label', ex.title + ', ' + completed + ' of ' + size + ' sets completed');
      const card = hooks.getCard(ex.id);
      if (card) {
        card.dataset.selected = String(ex.id === selectedId);
        const summary = card.querySelector('.exercise-progress');
        if (summary) summary.textContent = completed + ' of ' + size + ' sets completed';
      }
    });
    byId('loggerProgress').textContent = done + ' of ' + total + ' sets completed';
  }

  function update() {
    if (!hooks) return;
    const current = draft();
    const exercises = current?.exercises || [];
    if (!exercises.some(ex => ex.id === selectedId)) {
      selectedId = (exercises.find(ex => ex.sets.some(s => !s.done)) || exercises[0])?.id ?? null;
    }
    updateOutline(exercises);
    updateMotivation();
    const ex = selected();
    byId('loggerTools').hidden = !wide.matches || !ex || byId('workout').hidden;
    if (!wide.matches || !ex || byId('workout').hidden) { release(); return; }
    const card = hooks.getCard(ex.id);
    if (detached && (detached.id !== ex.id || detached.card !== card)) release();
    const loader = loaderFor(ex.id) || card?.querySelector('.loader');
    if (loader && !detached) {
      detached = {id: ex.id, card, element: loader};
      byId('loggerLoader').append(loader);
    }
    byId('loggerToolsTitle').textContent = ex.title;
    // Never replace a focused note or set input during autosave/async refresh.
    const notes = byId('loggerNotes');
    if (document.activeElement !== notes) notes.value = ex.notes || '';
    notes.setAttribute('aria-label', 'Exercise notes for ' + ex.title);
    notes.disabled = Boolean(current.frozenSave);
    renderPrevious(ex);
  }

  function position() {
    if (!hooks) return;
    const overview = byId('workoutOverview'), actions = byId('workoutActions'), bar = byId('bar');
    if (wide.matches) {
      byId('loggerSession').prepend(overview);
      byId('loggerSession').append(actions, bar);
    } else {
      byId('workout').prepend(overview);
      byId('exercises').after(actions);
      document.querySelector('main').after(bar);
      release();
    }
    if (desktop.matches) closeMenu(false);
    update();
  }

  function closeMenu(focus = true) {
    byId('loggerNav').classList.remove('is-open');
    byId('loggerMenu').setAttribute('aria-expanded', 'false');
    byId('loggerNavScrim').hidden = true;
    document.querySelector('main').inert = false;
    byId('bar').inert = false;
    if (focus && !desktop.matches) byId('loggerMenu').focus();
  }

  function decorate(card, ex) {
    card.dataset.exerciseId = ex.id;
    const summary = node('span', 'exercise-progress');
    const [done, total] = counts(ex); summary.textContent = done + ' of ' + total + ' sets completed';
    card.querySelector('.exhead').append(summary);
    const gate = node('div', 'mobile-set-gate');
    gate.hidden = true;
    const reason = node('p');
    reason.id = 'set-checkin-' + ex.id;
    const trigger = node('button', null, 'Check in');
    trigger.type = 'button';
    trigger.setAttribute('aria-controls', 'sessionMotivation');
    trigger.addEventListener('click', () => {
      inlineExerciseId = inlineExerciseId === ex.id ? null : ex.id;
      updateMotivation();
      if (inlineExerciseId === ex.id) byId('motivation-level')?.focus();
    });
    gate.append(reason, trigger);
    const advice = card.querySelector('[data-session-advice]');
    const disclosure = node('details', 'mobile-session-advice');
    disclosure.hidden = true;
    if (advice) {
      disclosure.append(node('summary', null, 'Session advice · optional'));
      const right = card.querySelector('.exright');
      right.insertBefore(disclosure, right.querySelector('.loader'));
    }
    mobileControls.set(card, {gate, reason, trigger, advice, disclosure});
    positionAdvice(card);
  }

  function init(options) {
    hooks = options;
    byId('loggerMenu').addEventListener('click', () => {
      const open = byId('loggerMenu').getAttribute('aria-expanded') !== 'true';
      byId('loggerMenu').setAttribute('aria-expanded', String(open));
      byId('loggerNav').classList.toggle('is-open', open);
      byId('loggerNavScrim').hidden = !open;
      document.querySelector('main').inert = open;
      byId('bar').inert = open;
      if (open) byId('loggerCloseMenu').focus();
    });
    byId('loggerCloseMenu').addEventListener('click', () => closeMenu());
    byId('loggerNavScrim').addEventListener('click', () => closeMenu());
    document.addEventListener('keydown', event => {
      if (event.key === 'Escape' && byId('loggerMenu').getAttribute('aria-expanded') === 'true') closeMenu();
    });
    const selectCard = event => {
      const card = event.target.closest('[data-exercise-id]');
      if (!card || card.dataset.exerciseId === selectedId) return;
      selectedId = card.dataset.exerciseId;
      update();
    };
    byId('exercises').addEventListener('focusin', selectCard);
    byId('exercises').addEventListener('click', selectCard);
    byId('loggerNotes').addEventListener('input', event => {
      const ex = selected();
      if (ex && !draft().frozenSave) { ex.notes = event.target.value; hooks.save(); }
    });
    wide.addEventListener('change', position);
    desktop.addEventListener('change', () => { if (desktop.matches) closeMenu(false); });
    const positionMobile = () => {
      byId('sessionMotivationHome').open = !mobile.matches;
      for (const ex of draft()?.exercises || []) positionAdvice(hooks.getCard(ex.id));
      updateMotivation();
    };
    mobile.addEventListener('change', positionMobile);
    positionMobile();
    position();
  }
  return {init, update, release, loaderFor, decorate, releaseMotivation, updateMotivation};
})();
