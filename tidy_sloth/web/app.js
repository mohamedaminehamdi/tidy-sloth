// Tidy Sloth review screen. With ?local=1 it talks to the tidy-sloth server on this Mac; otherwise it's the demo.
import { createScene, sleep } from './scene.js';

const LOCAL = new URLSearchParams(location.search).has('local');
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const scene = createScene($('stage'));
const JSON_POST = { method: 'POST', headers: { 'Content-Type': 'application/json' } };
let plan, moved = [];

function say(h, l = '') {
  $('headline').textContent = h;
  $('lede').textContent = l;
}

function headline(s, skipped) {
  if (!s.files && !skipped) return ['Nothing to tidy.', 'Your Downloads and Desktop are already clean. Back to the hammock.'];
  const parts = [];
  if (s.moves) parts.push(`put ${s.moves} away`);
  if (s.renames) parts.push(`rename ${s.renames}`);
  if (s.left + skipped) parts.push(`leave ${s.left + skipped} alone`);
  return [`${s.files + skipped} loose files.`, `I'll ${parts.join(', ').replace(/, ([^,]*)$/, ' and $1')}.`];
}

function row(item) {
  const tag = item.by === 'gemma' ? '<span class="tag-s warm">Gemma read it</span>'
    : item.by === 'new_folder' ? '<span class="tag-s warm">new folder</span>'
    : item.by === 'tabpfn' ? `<span class="tag-s">${Math.round(item.confidence * 100)}% sure</span>` : '';
  const pick = `<input type="checkbox" checked data-pick="${item.id}" aria-label="Include ${esc(item.name)}">`;
  if (!item.new_name) return `<div class="row">${pick}<div class="file"><div class="name">${esc(item.name)}</div></div>${tag}</div>`;
  return `<div class="row">${pick}<div class="file"><div class="from">${esc(item.name)} ${tag}</div>
    <input class="to" data-id="${item.id}" value="${esc(item.new_name)}" aria-label="New name for ${esc(item.name)}"></div><span></span></div>`;
}

function renderList() {
  const byFolder = new Map();
  for (const item of plan.items.filter((i) => i.folder)) byFolder.set(item.folder_name, [...(byFolder.get(item.folder_name) ?? []), item]);
  const renamedOnly = plan.items.filter((i) => i.action === 'rename');
  const left = plan.items.filter((i) => i.action === 'leave');
  const group = (title, body, n) => `<section class="group"><h2>${title}<small>${n}</small></h2>${body}</section>`;
  $('groups').innerHTML = [
    ...[...byFolder].map(([name, items]) => group(`📁 ${esc(name)}`, items.map(row).join(''), items.length)),
    renamedOnly.length ? group('✏️ Renamed, staying put', renamedOnly.map(row).join(''), renamedOnly.length) : '',
    left.length + plan.skipped.length ? group('💤 Leaving alone', [
      ...left.map((i) => `<div class="row"><span></span><div class="name">${esc(i.name)}</div><span class="tag-s">not sure</span></div>`),
      ...plan.skipped.map((i) => `<div class="row"><span></span><div class="name">${esc(i.name)}</div><span></span><div class="why">${esc(i.why)}</div></div>`),
    ].join(''), left.length + plan.skipped.length) : '',
  ].join('');
}

function render() {
  const s = plan.summary;
  say(...headline(s, plan.skipped.length));
  $('payoff').hidden = !s.minutes_saved;
  $('payoff').textContent = `≈ ${s.minutes_saved} minutes you don't have to spend`;
  $('approve').hidden = false;
  $('approve').disabled = !(s.moves || s.renames);
  $('undo').hidden = true;
  $('show').hidden = false;
  $('rescan').hidden = !LOCAL;
  renderList();
  scene.setPlan(plan);
  if (plan.applied) {  // reopened after approving: show the tidy, offer undo
    moved = plan.items.filter((i) => i.action !== 'leave').map((i) => i.id);
    scene.finish(moved);
    return doneState(moved.length);
  }
  idle();
}

// Before Approve. The demo shows the sloth doing the whole job; on your Mac nothing goes in a basket until you approve.
async function idle() {
  if (LOCAL) return scene.look();
  moved = chosen().map((i) => i.id);
  if (await scene.work(moved)) doneState(moved.length);
}

function chosen() {
  const off = new Set([...document.querySelectorAll('[data-pick]')].filter((c) => !c.checked).map((c) => Number(c.dataset.pick)));
  const names = Object.fromEntries([...document.querySelectorAll('.to')].map((i) => [i.dataset.id, i.value]));
  return plan.items.filter((i) => i.action !== 'leave' && !off.has(i.id)).map((i) => ({ id: i.id, new_name: names[i.id] ?? i.new_name }));
}

function doneState(n) {
  say('All tidy.', `${n} files handled${LOCAL ? '' : ' (demo: nothing really moved)'}. Nothing was deleted.`);
  $('approve').hidden = true;
  $('payoff').hidden = true;
  $('show').hidden = true;
  $('groups').hidden = true;
  $('undo').hidden = false;
  $('undo').disabled = false;
}

function asleep() {
  scene.stop();
  say('The sloth went back to sleep.', 'Open Tidy Sloth again to pick up where you left off.');
  for (const id of ['approve', 'undo', 'show', 'rescan']) $(id).hidden = true;
  $('payoff').hidden = true;
}

async function approve() {
  $('approve').disabled = true;
  const items = chosen();
  moved = items.map((i) => i.id);
  if (LOCAL) {
    const res = await fetch('/api/apply', { ...JSON_POST, body: JSON.stringify({ token: plan.token, items }) }).catch(() => null);
    if (!res) return asleep();
    const data = await res.json();
    if (!res.ok) {
      say('Something changed.', data.error ?? 'Look again to get a fresh plan.');
      return;
    }
    moved = data.moved;
  }
  $('approve').hidden = true;
  $('show').hidden = true;
  $('groups').hidden = true;
  $('payoff').hidden = true;
  say('Putting things away…', 'Slowly. Steadily. Tap the forest to skip.');
  await Promise.race([scene.sort(moved, { solo: LOCAL ? 2 : 1 }), sleep(15000)]);
  scene.finish(moved);
  doneState(moved.length);
}

async function undo() {
  $('undo').disabled = true;
  let text = 'Everything is back where it was.';
  if (LOCAL) {
    const res = await fetch('/api/undo', { ...JSON_POST, body: '{}' }).catch(() => null);
    if (!res) return asleep();
    const r = await res.json();
    text = `Put ${r.restored} files back.${r.problems?.length ? ' ' + r.problems.join(' ') : ''}`;
  }
  await Promise.race([scene.unsort(moved), sleep(6000)]);
  scene.stop();
  say('Undone.', text);
  $('undo').hidden = true;
  $('approve').hidden = false;
  $('approve').disabled = false;
  $('show').hidden = false;
  await sleep(1200);
  idle();
}

async function load() {
  if (!LOCAL) {
    plan = await (await fetch('demo-plan.json')).json();
    return render();
  }
  for (;;) {
    let data;
    try {
      data = await (await fetch('/api/plan', { cache: 'no-store' })).json();
    } catch {
      return asleep();
    }
    if (data.building) {
      say('Looking at your files…', data.step);
      scene.look();
      await sleep(900);
      continue;
    }
    if (data.error) {
      scene.stop();
      say('The sloth needs a hand.', data.error);
      $('rescan').hidden = false;
      $('approve').hidden = true;
      $('show').hidden = true;
      return;
    }
    plan = data;
    return render();
  }
}

async function rescan() {
  $('rescan').hidden = true;
  $('approve').disabled = true;
  $('groups').hidden = true;
  const res = await fetch('/api/rescan', { ...JSON_POST, body: '{}' }).catch(() => null);
  if (!res) return asleep();
  load();
}

function setupInstall() {
  const dialog = $('install'), cmd = $('cmd').textContent, copy = $('copy');
  async function copyCmd() {
    try {
      await navigator.clipboard.writeText(cmd);
      copy.textContent = 'Copied ✓';
    } catch {  // no clipboard permission: select it so ⌘C works
      getSelection().selectAllChildren($('cmd'));
      copy.textContent = 'Press ⌘C';
    }
  }
  $('install-open').addEventListener('click', () => { dialog.showModal(); copyCmd(); });
  copy.addEventListener('click', copyCmd);
  $('install-close').addEventListener('click', () => dialog.close());
  dialog.addEventListener('click', (e) => { if (e.target === dialog) dialog.close(); });
}

document.body.classList.toggle('local', LOCAL);
if (LOCAL) $('where').textContent = 'On this Mac only';
$('approve').addEventListener('click', approve);
$('undo').addEventListener('click', undo);
$('rescan').addEventListener('click', rescan);
$('show').addEventListener('click', () => { $('groups').hidden = !$('groups').hidden; });
$('groups').addEventListener('change', (e) => {
  if (e.target.dataset.pick !== undefined) scene.setOff(Number(e.target.dataset.pick), !e.target.checked);
});
$('stage').addEventListener('click', () => { if (scene.busy) { scene.finish(moved); doneState(moved.length); } });
if (!LOCAL) setupInstall();
document.fonts.ready.then(load);
