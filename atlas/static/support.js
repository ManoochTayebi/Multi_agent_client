/* Human support uses the application's authenticated HTTP interfaces. */
let supportThread = null, selectedSupportId = '', operatorBusy = false, supportPollBusy = false;

function updateSupportControls() {
  const open = supportThread && supportThread.status !== 'closed';
  $('talkHuman').disabled = busy || Boolean(open);
  $('resumeAI').disabled = busy;
  $('message').placeholder = open ? 'Message human support…' : 'Ask your Atlas concierge…';
}

function resetSupport() {
  supportThread = null;
  $('humanSupport').classList.add('hidden');
  $('chat').classList.remove('hidden');
  document.querySelector('.suggestions').classList.remove('hidden');
  updateSupportControls();
}

function renderHumanMessages(target, messages) {
  // All customer/operator text is rendered as text, never as HTML.
  const atBottom = target.scrollHeight - target.scrollTop - target.clientHeight < 50;
  const previousCount = target.childElementCount;
  target.replaceChildren();
  for (const message of messages) {
    const label = {customer:'Customer', operator:'Human operator', system:'System'}[message.sender];
    const entry = node('div', message.text, 'bubble ' + (message.sender === 'customer' ? 'user' : message.sender));
    // SQLite returns naive UTC timestamps; PostgreSQL includes the UTC offset.
    const timestamp = /(?:Z|[+-]\d{2}:\d{2})$/i.test(message.created_at) ? message.created_at : message.created_at + 'Z';
    entry.append(node('small', label + ' · ' + new Date(timestamp).toLocaleTimeString()));
    target.append(entry);
  }
  if (atBottom || previousCount === 0) target.scrollTop = target.scrollHeight;
}

async function refreshSupport(force = false) {
  if (!token || (busy && !force)) return;
  const sessionToken = token;
  const data = await api('/api/support');
  if (token !== sessionToken) return;
  const previous = supportThread;
  supportThread = data.thread;
  if (!supportThread) { resetSupport(); return; }
  const open = supportThread.status !== 'closed';
  $('humanSupport').classList.remove('hidden');
  if (!previous || previous.status !== supportThread.status) $('humanHistory').open = open;
  $('chat').classList.toggle('hidden', open);
  document.querySelector('.suggestions').classList.toggle('hidden', open);
  $('resumeAI').classList.toggle('hidden', !open);
  const labels = {waiting:'Waiting for a human operator', active:'Human operator has taken over', closed:'Human conversation closed'};
  $('humanStatus').textContent = labels[supportThread.status];
  $('humanStatusText').textContent = open
    ? 'Messages stay in this human conversation. AI business actions are paused. Replies refresh automatically.'
    : 'The AI concierge is available again. Expand this section to read the saved human conversation.';
  $('connection').textContent = open ? 'Human support · ' + supportThread.status : 'Connected';
  renderHumanMessages($('humanMessages'), data.messages);
  if (previous && previous.status !== 'closed' && !open) {
    const last = data.events.at(-1);
    bubble('Human conversation closed. ' + (last?.reason || '') + ' The AI concierge is available again.');
  }
  updateSupportControls();
}

async function loadSupportQueue() {
  const rows = await api('/admin/support', {headers:adminHeaders()});
  $('supportQueue').replaceChildren();
  if (!rows.length) $('supportQueue').append(node('p', 'No open human conversations.'));
  for (const row of rows) {
    const card = node('div', '', 'review');
    card.append(node('strong', row.customer_id + ' · ' + row.status), node('p', 'Reason: ' + row.reason));
    const button = node('button', 'Open conversation', 'primary');
    button.onclick = () => { selectedSupportId = row.id; loadSupportDetail().catch(showSupportError); };
    card.append(button);
    $('supportQueue').append(card);
  }
  $('supportOpsStatus').textContent = rows.length + ' open human conversation(s)';
}

function showSupportError(error) { $('supportOpsStatus').textContent = error.message; }

async function loadSupportDetail() {
  if (!selectedSupportId) return;
  const threadId = selectedSupportId;
  const data = await api('/admin/support/' + threadId, {headers:adminHeaders()});
  if (selectedSupportId !== threadId) return;
  $('supportDetail').classList.remove('hidden');
  $('supportHeading').textContent = data.thread.customer_id + ' · ' + data.thread.status;
  renderHumanMessages($('operatorMessages'), data.messages);
  $('claimSupport').disabled = operatorBusy || data.thread.status !== 'waiting';
  $('replySupport').disabled = operatorBusy || data.thread.status !== 'active';
  $('closeSupport').disabled = operatorBusy || data.thread.status === 'closed';
  $('supportContext').textContent = JSON.stringify({thread:data.thread, events:data.events,
    conversation:data.conversation, runs:data.runs}, null, 2);
}

async function mutateSupport(suffix, body) {
  if (operatorBusy || !selectedSupportId) return;
  operatorBusy = true;
  const threadId = selectedSupportId;
  for (const id of ['claimSupport', 'replySupport', 'closeSupport']) $(id).disabled = true;
  try {
    await api('/admin/support/' + threadId + suffix, {method:'POST', headers:adminHeaders(),
      ...(body ? {body:JSON.stringify(body)} : {})});
    if (suffix === '/messages') $('humanReply').value = '';
    if (suffix === '/close') $('supportCloseReason').value = '';
    await loadSupportQueue();
    await refreshSupport(true);
  } catch (error) { showSupportError(error); }
  finally { operatorBusy = false; await loadSupportDetail().catch(showSupportError); }
}

function initSupport() {
  $('talkHuman').onclick = () => send('I would like to speak to a human support agent.', true);
  $('resumeAI').onclick = async () => {
    if (busy) return;
    $('resumeAI').disabled = true;
    try {
      await api('/api/support/resume', {method:'POST', body:JSON.stringify({reason:'Customer chose to return to the AI concierge'})});
      await refreshSupport(true);
    } catch (error) { bubble(error.message, 'error'); }
    finally { updateSupportControls(); }
  };
  $('loadSupport').onclick = () => loadSupportQueue().catch(showSupportError);
  $('refreshSupportDetail').onclick = () => loadSupportDetail().catch(showSupportError);
  $('claimSupport').onclick = () => mutateSupport('/claim');
  $('replySupport').onclick = () => mutateSupport('/messages', {message:$('humanReply').value});
  $('closeSupport').onclick = () => mutateSupport('/close', {reason:$('supportCloseReason').value});
  // Polling keeps this single-process application free of extra transport services.
  setInterval(async () => {
    if (supportPollBusy) return;
    supportPollBusy = true;
    try {
      await refreshSupport();
      if (!$('operations').classList.contains('hidden') && $('adminKey').value && !operatorBusy) {
        await loadSupportQueue();
        await loadSupportDetail();
      }
    } catch (error) {
      if (supportThread && supportThread.status !== 'closed') $('humanStatusText').textContent = 'Refresh failed: ' + error.message;
    } finally { supportPollBusy = false; }
  }, 3000);
}
