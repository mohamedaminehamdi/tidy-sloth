// Tidy Sloth review screen. With ?local=1 it talks to the tidy-sloth server on this Mac; otherwise it's the demo.
const LOCAL = new URLSearchParams(location.search).has('local');
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
let plan;

function headline(s, skipped) {
  if (!s.files && !skipped) return ['Nothing to tidy.', 'Your Downloads and Desktop are already clean. Go back to the hammock.'];
  const parts = [];
  if (s.moves) parts.push(`put ${s.moves} away`);
  if (s.renames) parts.push(`rename ${s.renames}`);
  if (s.left + skipped) parts.push(`leave ${s.left + skipped} alone`);
  return [`${s.files + skipped} loose files.`, `I'll ${parts.join(', ').replace(/, ([^,]*)$/, ' and $1')}.`];
}

function row(item) {
  const tag = item.by === 'gemma' ? '<span class="tag gemma">Gemma read it</span>'
    : item.by === 'new_folder' ? '<span class="tag gemma">new folder</span>'
    : item.by === 'tabpfn' ? `<span class="tag">${Math.round(item.confidence * 100)}% sure</span>` : '';
  const rename = item.new_name ? `<input class="to" data-id="${item.id}" value="${esc(item.new_name)}" aria-label="New name for ${esc(item.name)}">` : '';
  return `<div class="row"><input type="checkbox" checked data-pick="${item.id}" aria-label="Include ${esc(item.name)}">
    <div class="file">${item.new_name ? `<div class="from">${esc(item.name)} ${tag}</div>${rename}` : `<div class="name">${esc(item.name)}</div>`}</div>${item.new_name ? '' : tag}</div>`;
}

function render() {
  const s = plan.summary;
  const [h, l] = headline(s, plan.skipped.length);
  $('headline').textContent = h;
  $('lede').textContent = l;
  if (s.minutes_saved) {
    $('payoff').hidden = false;
    $('payoff').textContent = `≈ ${s.minutes_saved} minutes you don't have to spend`;
  }
  $('approve').disabled = !(s.moves || s.renames);
  const byFolder = new Map();
  for (const item of plan.items.filter((i) => i.folder)) {
    if (!byFolder.has(item.folder_name)) byFolder.set(item.folder_name, []);
    byFolder.get(item.folder_name).push(item);
  }
  const renamedOnly = plan.items.filter((i) => i.action === 'rename');
  const left = plan.items.filter((i) => i.action === 'leave');
  $('groups').innerHTML = [
    ...[...byFolder].map(([name, items]) => `<section class="group"><h2 class="folder">${esc(name)}<small>${items.length}</small></h2>${items.map(row).join('')}</section>`),
    renamedOnly.length ? `<section class="group"><h2 class="renamed">Renamed, staying put<small>${renamedOnly.length}</small></h2>${renamedOnly.map(row).join('')}</section>` : '',
    (left.length || plan.skipped.length) ? `<section class="group"><h2 class="left">Leaving alone<small>${left.length + plan.skipped.length}</small></h2>
      ${left.map((i) => `<div class="row"><span></span><div class="name">${esc(i.name)}</div><span class="tag">not sure</span></div>`).join('')}
      ${plan.skipped.map((i) => `<div class="row"><span></span><div class="name">${esc(i.name)}</div><span></span><div class="why">${esc(i.why)}</div></div>`).join('')}</section>` : '',
  ].join('');
}

function chosen() {
  const off = new Set([...document.querySelectorAll('[data-pick]')].filter((c) => !c.checked).map((c) => Number(c.dataset.pick)));
  const names = Object.fromEntries([...document.querySelectorAll('.to')].map((i) => [i.dataset.id, i.value]));
  return plan.items.filter((i) => i.action !== 'leave' && !off.has(i.id)).map((i) => ({ id: i.id, new_name: names[i.id] ?? i.new_name }));
}

async function approve() {
  $('approve').disabled = true;
  const items = chosen();
  let moved = items.length;
  if (LOCAL) {
    const res = await fetch('/api/apply', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ items }) });
    moved = (await res.json()).moved;
  }
  $('review').hidden = true;
  $('done').hidden = false;
  $('done-title').textContent = 'All tidy.';
  $('done-text').textContent = `${moved} files handled${LOCAL ? '' : ' (demo: nothing really moved)'}. Nothing was deleted.`;
}

async function undo() {
  let text = 'Everything is back where it was.';
  if (LOCAL) {
    const r = await (await fetch('/api/undo', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })).json();
    text = `Put ${r.restored} files back.${r.problems.length ? ' ' + r.problems.join(' ') : ''}`;
  }
  $('done-title').textContent = 'Undone.';
  $('done-text').textContent = text;
  $('undo').hidden = true;
}

async function main() {
  $('demo-note').hidden = LOCAL;
  $('where').textContent = LOCAL ? 'On this Mac only' : 'Demo';
  plan = await (await fetch(LOCAL ? '/api/plan' : 'demo-plan.json')).json();
  render();
  $('approve').addEventListener('click', approve);
  $('show').addEventListener('click', () => { $('groups').hidden = !$('groups').hidden; });
  $('undo').addEventListener('click', undo);
}

main();
