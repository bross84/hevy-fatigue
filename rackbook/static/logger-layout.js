/* View-only workspace. The logger owns sets, calculations, timers and save recovery. */
const LoggerLayout = (() => {
  let hooks, selectedId = null, detached = null, outlineKey = '';
  const wide = matchMedia('(min-width: 1900px)');
  const desktop = matchMedia('(min-width: 1100px)');
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
    position();
  }
  return {init, update, release, loaderFor, decorate};
})();
