/* AI Coach plan change card (ADR 0002). Previewing writes nothing. The plan changes only when the athlete
   taps "Accept change", and "Undo" puts the previous version back. Trained and skipped days are never
   changed and nothing is activated. Every piece of AI text is shown with textContent, never as HTML. */
const PlanChange = (() => {
  const FENCE = 'plan-change-v1';
  const COMPLETE = new RegExp('```' + FENCE + '[ \\t]*\\r?\\n[\\s\\S]*?```', 'g');
  const OPEN = new RegExp('```' + FENCE + '[\\s\\S]*$');
  const NOTE = '\n\n*(Suggested plan change shown below.)*\n\n';

  // Remove the machine-readable block from the text people read; found is true when one exists.
  function strip(text) {
    const value = String(text || '');
    const result = value.replace(COMPLETE, NOTE).replace(OPEN, NOTE);
    return {text: result, found: result !== value};
  }

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }
  function clear(node) {
    if (node.replaceChildren) node.replaceChildren(); else node.textContent = '';
  }

  async function post(path, body) {
    const response = await fetch(trainingUrl(path), {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(body || {})});
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw Error(typeof data.detail === 'string' ? data.detail : 'The plan change request failed.');
    return data;
  }

  function list(items) {
    const ul = el('ul', 'plan-proposal-list');
    for (const item of items) ul.append(el('li', '', item));
    return ul;
  }

  function planLink(plan) {
    const link = el('a', 'plan-proposal-open', 'Open ' + (plan.name || 'the plan') + ' in the builder');
    link.href = trainingUrl('/microcycles?plan=' + encodeURIComponent(plan.id));
    return link;
  }

  function describe(card, result) {
    clear(card);
    card.append(el('h4', 'plan-proposal-title', 'Suggested change' + (result.title ? ': ' + result.title : '')));
    if (result.rationale) card.append(el('p', 'plan-proposal-rationale', result.rationale));
    if (result.plan) card.append(el('p', 'plan-proposal-note', 'For ' + result.plan.name + (result.plan.active ? ' (your active microcycle)' : '')));
    for (const day of result.days || []) {
      card.append(el('h5', 'plan-proposal-session', 'Day ' + day.day + ' · ' + day.name));
      card.append(list(day.changes));
    }
  }

  function render(card, result, request) {
    describe(card, result);
    if (!result.valid) {
      card.append(el('p', 'plan-proposal-note', 'This change cannot be applied as written:'));
      card.append(list(result.issues));
      return;
    }
    const status = el('p', 'plan-proposal-status');
    if (result.status === 'undone') {
      status.textContent = 'Undone. The plan is back to how it was before this change.';
      card.append(status, planLink(result.plan));
      return;
    }
    if (result.status === 'applied') {
      status.textContent = 'Applied to ' + result.plan.name + '.';
      card.append(status);
      undoControl(card, result, request);
      card.append(planLink(result.plan));
      return;
    }
    card.append(el('p', 'plan-proposal-note', 'Nothing changes until you tap Accept. Finished days stay as they are, and you can undo it afterwards.'));
    const button = el('button', 'plan-proposal-save', 'Accept change');
    button.type = 'button';
    button.addEventListener('click', async () => {
      button.disabled = true;
      status.textContent = 'Applying…';
      try {
        const saved = await post('/api/plan-changes/accept', request);
        render(card, saved.change, request);
      } catch (error) {
        status.textContent = (error.message || 'Could not apply the change.') + ' Nothing was changed.';
        button.disabled = false;
      }
    });
    card.append(button, status);
  }

  function undoControl(card, result, request) {
    if (!result.can_undo) {
      if (result.undo_problem) card.append(el('p', 'plan-proposal-note', result.undo_problem));
      return;
    }
    const status = el('p', 'plan-proposal-status');
    const button = el('button', 'plan-proposal-save', 'Undo');
    button.type = 'button';
    button.addEventListener('click', async () => {
      button.disabled = true;
      status.textContent = 'Undoing…';
      try {
        const undone = await post('/api/plan-changes/' + encodeURIComponent(result.change_id) + '/undo');
        render(card, undone.change, request);
      } catch (error) {
        status.textContent = (error.message || 'Could not undo the change.') + ' The plan was not changed.';
        button.disabled = false;
      }
    });
    card.append(button, status);
  }

  // Adds a card after the reply when it contains a plan change. Resolves to the card or null.
  async function mount(host, {text, conversationId, turnId}) {
    if (!strip(text).found) return null;
    const request = {text: String(text), conversation_id: conversationId, turn_id: turnId};
    const card = el('div', 'plan-proposal plan-change');
    card.append(el('p', 'plan-proposal-status', 'Checking the suggested change…'));
    host.append(card);
    try {
      render(card, await post('/api/plan-changes/preview', request), request);
    } catch (error) {
      clear(card);
      card.append(el('p', 'plan-proposal-status', (error.message || 'Could not check the change.') + ' Reload the saved review to try again.'));
    }
    return card;
  }

  return {strip, mount};
})();
