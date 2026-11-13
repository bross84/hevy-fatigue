/* View-only workspace. The logger owns sets, calculations, timers and save recovery. */
const LoggerLayout = (() => {
  let hooks, selectedId = null, detached = null, outlineKey = '';
  const wide = matchMedia('(min-width: 1900px)');
  const desktop = matchMedia('(min-width: 1100px)');
  const mobile = matchMedia('(max-width: 599px)');
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
    if (card === detached.card && card?.isConnected) (card.querySelector('.ex-plates') || card.querySelector('.exright')).append(detached.element);
    else detached.element.remove();
    detached = null;
  }

  function loaderFor(id) { return detached?.id === id ? detached.element : null; }

  // The form no longer leaves its home; this returns it if an older page state moved it.
  function releaseMotivation() {
    const form = byId('sessionMotivation'), home = byId('sessionMotivationHome');
    if (form.parentElement === home) return null;
    const focused = form.contains(document.activeElement) ? document.activeElement : null;
    home.append(form);
    return focused;
  }

  // Motivation is one check-in for the day and stays at the top of the workout. On phones each card's
  // next working set explains why its tick is locked and jumps back to that single check-in.
  // Once confirmed, the check-in folds to one line for the rest of the workout; tapping it opens it again.
  const LEVELS = ['Eager', 'Willing', 'Neutral', 'Reluctant', 'Dreading it'];
  const SORE = [['squat', 'Squat'], ['bench_press', 'Press'], ['deadlift', 'Hinge']];
  const SORE_LEVEL = ['none', 'mild', 'moderate', 'severe'];
  let wasReady = null;
  function checkinLine(current) {
    const parts = [];
    if (current.motivation && LEVELS[current.motivation.level]) parts.push(LEVELS[current.motivation.level]);
    for (const [key, label] of SORE) {
      const r = current.soreness?.[key];
      if (r && (Number.isInteger(r.level) || r.pain)) parts.push(label + ' ' + (Number.isInteger(r.level) ? SORE_LEVEL[r.level] : '') + (r.pain ? ' (pain)' : ''));
    }
    return 'Check-in \u2713' + (parts.length ? ' \u00b7 ' + parts.join(' \u00b7 ') : '');
  }
  function updateMotivation() {
    const current = draft();
    const home = byId('sessionMotivationHome');
    const required = Boolean(current && typeof SessionMotivation !== 'undefined' && !SessionMotivation.ready(current));
    const blocked = mobile.matches && required;
    releaseMotivation();
    home.hidden = false;
    const ready = Boolean(current) && !required;
    const summary = home.querySelector(':scope > summary');
    if (summary) summary.textContent = ready ? checkinLine(current) : 'Before you train \u00b7 today\u2019s check-in';
    home.classList.toggle('checked-in', ready);
    if (ready && wasReady !== true) home.open = false;
    if (current && !ready) home.open = true;
    wasReady = current ? ready : null;
    if (blocked) home.open = true;
    for (const ex of current?.exercises || []) {
      const card = hooks.getCard(ex.id), controls = mobileControls.get(card);
      if (!controls) continue;
      const rows = [...card.querySelectorAll('.set[data-working]')];
      const next = rows.find(row => !row.classList.contains('done'));
      if (blocked && next && controls.gate.parentElement !== next) next.insertBefore(controls.gate, next.querySelector('.tick'));
      controls.gate.hidden = !(blocked && next);
      controls.reason.textContent = current.frozenSave
        ? 'This workout is pending save recovery.' : "Do today's check-in at the top before working sets.";
      controls.trigger.hidden = Boolean(current.frozenSave);
      for (const row of rows) {
        const tick = row.querySelector('.tick');
        row.classList.toggle('next-working-set', row === next);
        tick.disabled = Boolean(blocked && !row.classList.contains('done'));
        if (tick.disabled) tick.setAttribute('aria-describedby', controls.reason.id);
        else tick.removeAttribute('aria-describedby');
      }
    }
  }

  function openCheckin() {
    const home = byId('sessionMotivationHome');
    home.hidden = false; home.open = true;
    home.scrollIntoView({block: 'start', behavior: 'instant'});
    byId('motivation-level')?.focus({preventScroll: true});
  }

  // Session advice stays in the exercise's Info sheet at every width, out of the way of the sets.
  function positionAdvice(card) {
    const controls = mobileControls.get(card);
    if (!controls?.advice) return;
    const {advice, disclosure} = controls;
    if (advice.parentElement === disclosure) {
      const left = card.querySelector('.exleft');
      left.insertBefore(advice, left.querySelector(':scope > .numbers'));
    }
    disclosure.hidden = true;
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
        if (summary) summary.textContent = setOf(ex);
      }
    });
    byId('loggerProgress').textContent = done + ' of ' + total + ' sets completed';
    updateStrip(exercises);
  }

  const working = ex => ex.sets.filter(s => s.type !== 'warmup');
  const isOpen = ex => working(ex).some(s => !s.done);
  function setOf(ex) {
    const work = working(ex), done = work.filter(s => s.done).length;
    if (!work.length) return 'No working sets';
    return done === work.length ? 'All ' + work.length + ' sets done' : 'Set ' + (done + 1) + ' of ' + work.length;
  }
  function initials(title) {
    const words = String(title).replace(/\(.*?\)/g, ' ').split(/[\s,-]+/).filter(Boolean);
    return words.slice(0, 3).map(w => w[0]).join('').toUpperCase() || '?';
  }
  // The exercise strip: one card per exercise, a tick once its working sets are done, SS for a superset.
  function updateStrip(exercises) {
    const strip = byId('exStrip');
    if (!strip) return;
    strip.replaceChildren();
    for (const ex of exercises) {
      const work = working(ex), done = work.filter(s => s.done).length, all = work.length > 0 && done === work.length;
      const button = node('button', 'ex-card' + (all ? ' complete' : '') + (ex.ss ? ' superset' : ''));
      button.type = 'button';
      button.setAttribute('aria-current', ex.id === selectedId ? 'true' : 'false');
      button.setAttribute('aria-label', ex.title + ', ' + done + ' of ' + work.length + ' sets done' + (ex.ss ? ', in a superset' : ''));
      button.title = ex.title;
      button.append(node('span', 'ex-card-short', initials(ex.title)), node('span', 'ex-card-count', done + '/' + work.length));
      if (all) button.append(node('span', 'ex-card-done', '\u2713'));
      if (ex.ss) button.append(node('span', 'ex-card-ss', 'SS'));
      button.addEventListener('click', () => select(ex.id));
      strip.append(button);
    }
    const add = node('button', 'ex-card ex-card-add', '+'); add.type = 'button';
    add.setAttribute('aria-label', 'Add exercise');
    add.addEventListener('click', () => byId('addEx').click());
    strip.append(add);
  }
  function current() { return selected() || null; }
  // Show one exercise. Opening a collapsed one reopens it.
  function select(id) {
    const ex = draft()?.exercises.find(e => e.id === id);
    if (!ex) return;
    selectedId = id;
    if (ex.collapsed) { ex.collapsed = false; hooks.save(); hooks.render(); }
    update();
    if (typeof paintPlates === 'function') paintPlates();
    const strip = byId('exStrip');
    if (strip && strip.getBoundingClientRect().top < 0) strip.scrollIntoView({block: 'start', behavior: 'instant'});
  }
  // After a working set is ticked: in a superset, go to the partner (no rest until both have done the round);
  // otherwise, once this exercise is done, the next exercise that still has sets to do.
  function afterSet(ex) {
    const list = draft()?.exercises || [];
    const doneCount = e => working(e).filter(s => s.done).length;
    const partner = ex.ss ? list.find(e => e.id === ex.ss) : null;
    if (partner && isOpen(partner)) return {next: partner.id, skipRest: doneCount(partner) < doneCount(ex)};
    if (isOpen(ex)) return null;
    const at = list.indexOf(ex);
    for (let step = 1; step < list.length; step++) {
      const e = list[(at + step) % list.length];
      if (isOpen(e)) return {next: e.id, skipRest: false};
    }
    return null;
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
    const trigger = node('button', null, 'Go to check-in');
    trigger.type = 'button';
    trigger.setAttribute('aria-controls', 'sessionMotivationHome');
    trigger.addEventListener('click', openCheckin);
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
  return {init, update, release, loaderFor, decorate, releaseMotivation, updateMotivation, current, select, afterSet};
})();
