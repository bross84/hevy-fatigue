/* Joint coaching calls (#154): the dashboard banner and the decision card under a call in AI Coach.
   It only reads monitoring state and records the athlete's own decision tap; it never changes a plan,
   a workout or a check-in. */
const JointCall = (() => {
  const REGION = {upper: 'Upper', lower: 'Lower'};
  const PATTERNS = {upper: 'push and pull', lower: 'knee and hip'};
  const node = (tag, text, cls) => { const n = document.createElement(tag); if (text != null) n.textContent = text; if (cls) n.className = cls; return n; };
  const callUrl = () => '/?coaching_joint=1#ai';
  const openUrl = id => '/?coaching_conversation=' + encodeURIComponent(id) + '#ai';
  const shortDate = iso => new Date(iso + 'T00:00:00').toLocaleDateString(undefined, {day: 'numeric', month: 'short'});
  const plusDays = n => { const d = new Date(); d.setDate(d.getDate() + n);
    return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0'); };

  async function getJSON(path) {
    const response = await fetch(path);
    if (!response.ok) throw Error('Joint status unavailable');
    return response.json();
  }

  function regionLine(key, region) {
    const raised = region.recent.filter(r => r.above).slice(-3).map(r => r.rating).join(', ');
    const count = region.level === 'review'
      ? region.review_count + ' of your last 10 check-ins'
      : region.notice_count + ' of your last 7 check-ins';
    return REGION[key] + ' joint above your usual for ' + count + ' (usual ' + region.usual + (raised ? ', recent ' + raised : '') + ').';
  }

  let request = 0;
  async function loadNotice(box) {
    const mine = ++request;
    try {
      const status = await getJSON('/api/joint/status');
      if (mine !== request) return;
      box.replaceChildren();
      box.className = '';
      if (status.call) {
        const regions = status.call.regions;
        const saved = await fetch('/api/ai/conversations/' + encodeURIComponent(status.call.id));
        let weekly = null;
        try { const due = await fetch(trainingUrl('/api/weekly-call')); weekly = due.ok ? await due.json() : null; } catch (e) { weekly = null; }
        if (mine !== request) return;
        box.className = 'joint-call-due';
        box.append(node('h2', status.call.kind === 'review' ? 'Coaching call needed: review the movement' : 'Coaching call needed'));
        for (const key of regions) box.append(node('p', regionLine(key, status.regions[key])));
        box.append(node('p', regions.map(k => PATTERNS[k]).join(' and ').replace(/^\w/, c => c.toUpperCase()) +
          ' loads are held until the call.', 'joint-call-muted'));
        const link = node('a');
        if (weekly) {
          link.textContent = 'Discuss it in your weekly coaching call';
          link.href = AICoach.callUrl(weekly.source.id);
        } else {
          link.textContent = saved.ok ? 'Open coaching call' : 'Start coaching call';
          link.href = saved.ok ? openUrl(status.call.id) : callUrl();
        }
        box.append(link);
        box.hidden = false;
        return;
      }
      const carrying = Object.entries(status.regions).filter(([, r]) => r.level !== 'none' && r.carry_on_until);
      if (carrying.length) {
        box.className = 'joint-call-quiet';
        for (const [key, r] of carrying) box.append(node('p', REGION[key] + ' joint still above usual · carrying on until ' +
          shortDate(r.carry_on_until) + ', then the coach checks in again'));
        box.hidden = false;
        return;
      }
      box.hidden = true;
    } catch (error) {
      if (mine === request) { box.hidden = true; box.replaceChildren(); }
    }
  }

  function contextOf(view) {
    const evidence = (view && view.evidence) || {};
    return evidence.joint_context || (evidence.monitoring_context && evidence.monitoring_context.joint_call) || null;
  }

  async function mountDecision(host, view) {
    const context = contextOf(view);
    if (!context) return;
    const card = node('section', null, 'joint-decision-card');
    card.setAttribute('aria-label', 'Your joint call decision');
    host.append(card);
    let status;
    try { status = await getJSON('/api/joint/status'); } catch (e) { card.append(node('p', 'Joint status unavailable. Try again later.')); return; }
    const regions = context.regions.filter(k => status.regions[k] && status.regions[k].level !== 'none');
    const recorded = context.regions.map(k => status.regions[k] && status.regions[k].last_decision)
      .filter(d => d && d.decided_on >= status.date.slice(0, 10) && d.outcome !== 'not_now');
    card.append(node('h3', 'Your decision'));
    if (!regions.length || recorded.length) {
      const d = recorded[0];
      card.append(node('p', d ? 'Recorded: ' + describe(d) + '.' : 'Nothing to decide: the joint is back at your usual.'));
      return;
    }
    card.append(node('p', 'The coach advises; you decide. ' + regions.map(k => REGION[k]).join(' and ') + ' joint.', 'joint-call-muted'));
    const buttons = node('div', null, 'joint-decision-buttons');
    const extra = node('div');
    const error = node('p', null, 'joint-call-error');
    const send = async (outcome, until = null, note = '') => {
      for (const b of card.querySelectorAll('button')) b.disabled = true;
      error.textContent = '';
      try {
        const response = await fetch('/api/joint/decisions', {method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({id: crypto.randomUUID(), regions, outcome, until, note, conversation_id: view.id})});
        const data = await response.json();
        if (!response.ok) throw Error(typeof data.detail === 'string' ? data.detail : 'Decision not recorded.');
        card.replaceChildren(node('h3', 'Your decision'), node('p', 'Recorded: ' +
          describe({outcome, until}) + '.'));
        const notice = document.getElementById('joint-call-notice');
        if (notice) loadNotice(notice);
        if (typeof JointHold !== 'undefined') JointHold.load();
      } catch (e) {
        error.textContent = e.message;
        for (const b of card.querySelectorAll('button')) b.disabled = false;
      }
    };
    const option = (text, outcome) => {
      const b = node('button', text); b.type = 'button';
      b.addEventListener('click', () => {
        extra.replaceChildren();
        if (outcome === 'carry_on') {
          const label = node('label', 'Carry on until '); const input = node('input'); input.type = 'date';
          input.min = plusDays(1); input.value = plusDays(7); label.append(input);
          const ok = node('button', 'Record carry on'); ok.type = 'button';
          ok.addEventListener('click', () => { if (input.reportValidity() && input.value) send('carry_on', input.value); });
          extra.append(label, ok);
        } else if (outcome === 'change') {
          const label = node('label', 'What are you changing? '); const input = node('input'); input.type = 'text'; input.maxLength = 1000;
          input.placeholder = 'Box squat instead of back squat'; label.append(input);
          const ok = node('button', 'Record change'); ok.type = 'button';
          ok.addEventListener('click', () => send('change', null, input.value));
          extra.append(label, ok);
        } else send(outcome);
      });
      buttons.append(b);
    };
    option('This is my new normal', 'new_normal');
    option('Carry on until…', 'carry_on');
    option('Make a change', 'change');
    option('Not now', 'not_now');
    card.append(buttons, extra, error);
  }

  function describe(d) {
    return {new_normal: 'new normal; your usual moves up',
      carry_on: 'carry on until ' + (d.until ? shortDate(d.until) : 'the chosen date'),
      change: 'make a change' + (d.note ? ' (' + d.note + ')' : ''), not_now: 'not now'}[d.outcome] || d.outcome;
  }

  async function renderEvidence(card) {
    if (!card) return;
    card.replaceChildren(node('div', 'Loading joint evidence…', 'joint-call-muted'));
    let evidence, status;
    try { [evidence, status] = await Promise.all([getJSON('/api/joint/evidence'), getJSON('/api/joint/status')]); }
    catch (e) { card.replaceChildren(node('div', 'Joint evidence unavailable right now.', 'joint-call-muted')); return; }
    const head = node('div', null, 'joint-evidence-head');
    head.append(node('div', 'Joint evidence', 'card-title'), node('span', 'Last ' + Math.round(evidence.window_days / 7) + ' weeks', 'joint-evidence-pill'));
    card.replaceChildren(head, node('p', 'Your joint rating the morning after a lift, compared with all your other check-ins. ' +
      'It shows what tends to go together, not proof of cause.', 'joint-call-muted'));
    for (const key of ['lower', 'upper']) {
      const region = evidence.regions[key], state = status.regions[key];
      const usual = state.usual == null ? 'usual still being worked out' : 'usual ' + state.usual;
      card.append(node('p', REGION[key] + ' joint · ' + usual, 'joint-evidence-region'));
      if (!region.lines.length) { card.append(node('p', 'No lifts to compare yet.', 'joint-call-muted')); continue; }
      const table = node('table', null, 'joint-evidence-table');
      const top = node('tr'); for (const h of ['Lift', 'After lift days', 'Other days']) top.append(node('th', h));
      table.append(top);
      for (const line of region.lines) {
        const row = node('tr', null, line.kind === 'pattern' ? 'joint-evidence-pattern' : line.status === 'collecting' ? 'joint-evidence-collecting' : '');
        row.append(node('td', line.name));
        if (line.status === 'collecting') {
          const cell = node('td', 'Not enough yet (' + line.after_count + ' of ' + evidence.minimum + ' check-ins)'); cell.colSpan = 2; row.append(cell);
        } else {
          const after = node('td', line.after_average.toFixed(1) + ' ');
          after.append(node('span', line.after_count + ' check-ins' + (line.status === 'early' ? ' · early read' : ''), 'joint-evidence-pill'));
          row.append(after, node('td', line.other_average.toFixed(1) + ' (' + line.other_count + ')'));
        }
        table.append(row);
      }
      card.append(table);
    }
    const decisions = Object.values(status.regions).map(r => r.last_decision).filter(Boolean).sort((a, b) => b.decided_on.localeCompare(a.decided_on));
    if (decisions.length) card.append(node('p', 'Last call: ' + shortDate(decisions[0].decided_on) + ' · ' + describe(decisions[0]), 'joint-evidence-region'));
  }

  return {loadNotice, mountDecision, renderEvidence, callUrl, contextOf};
})();
