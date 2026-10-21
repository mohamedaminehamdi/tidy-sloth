// The stage: a sloth on a vine fetches each file from the pile, reads it, names it, and drops it in its basket.
// Purely cosmetic. The app never waits on it for state, and every run can be cancelled and snapped to the true end state.
const TRACK_TOP = 34, VINE = 28, HOLD_TOP = 104, W = 110;   // keep in sync with .sloth/.vine/.rig/.hold in index.html
const EASE = 'cubic-bezier(.45,0,.25,1)', OUT = 'cubic-bezier(.2,.8,.3,1)', IN = 'cubic-bezier(.55,0,.9,.45)';
const FAMILY = {
  image: ['jpg', 'jpeg', 'png', 'heic', 'gif', 'webp', 'tiff', 'bmp', 'svg'], video: ['mov', 'mp4', 'm4v', 'avi', 'mkv', 'webm'],
  pdf: ['pdf'], ebook: ['epub', 'mobi', 'azw3'], text: ['txt', 'md', 'rtf', 'doc', 'docx', 'pages', 'csv', 'json'],
  archive: ['zip', 'dmg', 'tar', 'gz', 'rar', '7z', 'pkg'],
};
const COLOR = { image: '#d9774b', video: '#8a63d2', pdf: '#cf4a4a', ebook: '#3f8f7a', text: '#5b7d98', archive: '#9a8653', other: '#7b7b74' };
const KIND = { image: 'photo', video: 'video', pdf: 'document', ebook: 'ebook', text: 'document', archive: 'archive', other: 'file' };
const size = (b) => (b > 1e6 ? `${(b / 1e6).toFixed(1)} MB` : `${Math.max(1, Math.round(b / 1e3))} KB`);
const ext = (name) => (name.match(/\.([^.]+)$/)?.[1] ?? '').toLowerCase();
const family = (name) => Object.keys(FAMILY).find((f) => FAMILY[f].includes(ext(name))) ?? 'other';
const reduced = matchMedia('(prefers-reduced-motion: reduce)');
const narrow = matchMedia('(max-width: 720px)');
export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function go(el, to, ms, easing = EASE) {
  const a = el.animate([to], { duration: Math.max(1, ms), easing, fill: 'forwards' });
  try { await a.finished; a.commitStyles(); } catch { /* cancelled */ } finally { a.cancel(); }
}
const done = (a) => a.finished.catch(() => {});

export function createScene(stage) {
  const q = (s) => stage.querySelector(s);
  const sloth = q('#sloth'), sway = q('.sway'), vine = q('.vine'), rig = q('.rig'), hold = q('#hold');
  const tray = q('#tray'), baskets = q('#baskets'), fly = q('#fly'), thought = q('#think');
  let run = 0, mode = null, x = 40, drop = 0;
  let items = new Map(), cards = new Map(), basketOf = new Map(), hiddenBusy = [], hiddenLazy = 0;
  const off = new Set(), inBasket = new Set(), renamed = new Set();
  sloth.style.translate = `${x}px 0`;

  const rel = (el) => {
    const s = stage.getBoundingClientRect(), r = el.getBoundingClientRect();
    return { x: r.left - s.left, y: r.top - s.top, w: r.width, h: r.height, cx: r.left - s.left + r.width / 2, cy: r.top - s.top + r.height / 2 };
  };

  function card(name, badge, k) {
    const el = document.createElement('div');
    el.className = 'card' + (badge === '💤' ? ' zz' : '');
    el.innerHTML = '<span class="g"></span><span class="n"></span>';
    el.firstChild.textContent = (ext(name) || 'file').slice(0, 4).toUpperCase();
    el.firstChild.style.setProperty('--c', COLOR[family(name)]);
    el.lastChild.textContent = name;
    if (badge) el.insertAdjacentHTML('beforeend', `<span class="b">${badge}</span>`);
    el.style.setProperty('--r', `${((k * 37) % 9) - 4}deg`);
    return el;
  }

  function count(b) {
    b.querySelector('b').innerHTML = `${b.filled}<small>/${b.total}</small>`;
  }
  function bump(b) {
    b.animate([{ rotate: '0deg' }, { rotate: '-3deg' }, { rotate: '2deg' }, { rotate: '0deg' }], { duration: 420, easing: 'ease-in-out' });
    b.querySelector('b').animate([{ scale: 1 }, { scale: 1.25 }, { scale: 1 }], { duration: 300, easing: OUT });
  }
  function relabel(el, name) {
    const n = el.querySelector('.n');
    n.animate([{ opacity: 1 }, { opacity: 0 }, { opacity: 1 }], { duration: 420 });
    setTimeout(() => { n.textContent = name; }, 210);
  }

  // ---- the work itself: what the sloth is thinking, reading the file, typing its new name ----
  function think(label, text) {
    thought.querySelector('small').textContent = label;
    thought.querySelector('b').textContent = text;
    thought.classList.toggle('left', x > stage.clientWidth / 2);
    if (thought.hidden) {
      thought.hidden = false;
      thought.animate([{ opacity: 0, scale: 0.85 }, { opacity: 1, scale: 1 }], { duration: 240, easing: OUT });
    }
  }
  const unthink = () => { thought.hidden = true; };
  const describe = (i) => `${(ext(i.name) || 'file').toUpperCase()} ${KIND[family(i.name)]}${i.size ? ` · ${size(i.size)}` : ''}`;
  const verdict = (i) => (i.by === 'tabpfn' ? ['TabPFN', `${Math.round(i.confidence * 100)}% sure → ${i.folder_name}`]
    : i.by === 'gemma' ? ['Gemma 4 read it', `→ ${i.folder_name}`]
    : i.by === 'new_folder' ? ['None of your folders fit', `→ a new ${i.folder_name} folder`]
    : ['Stays where it is', 'it just needs a name']);

  async function analyse(clone, item, f, r) {
    think('Reading it…', describe(item));
    const scan = document.createElement('i');
    scan.className = 'scan';
    clone.append(scan);
    await done(scan.animate([{ top: '-15%' }, { top: '110%' }], { duration: 620 * f, iterations: 2, easing: 'ease-in-out' }));
    scan.remove();
  }

  async function retype(el, name, f, r) {
    const n = el.querySelector('.n'), old = n.textContent;
    el.classList.add('typing');
    for (let k = old.length; k > 0 && r === run; k -= Math.ceil(old.length / 12)) { n.textContent = old.slice(0, k); await sleep(24 * f); }
    for (let k = 1; k <= name.length && r === run; k += Math.ceil(name.length / 20)) { n.textContent = name.slice(0, k); await sleep(38 * f); }
    n.textContent = name;
    el.classList.remove('typing');
  }

  // ---- the sloth's three moves: along the branch, down the vine, back up ----
  async function travel(tx, f) {
    tx = Math.max(34, Math.min(stage.clientWidth - W - 34, tx));  // room for the card it carries
    const dist = Math.abs(tx - x);
    if (dist < 2) return;
    const ms = Math.max(450, dist / 0.32) * f, dir = Math.sign(tx - x);
    x = tx;
    const swing = sway.animate([{ rotate: '0deg' }, { rotate: `${-6 * dir}deg`, offset: 0.3 }, { rotate: `${3 * dir}deg`, offset: 0.78 }, { rotate: '0deg' }],
      { duration: ms + 260 * f, easing: 'ease-in-out' });
    await go(sloth, { translate: `${tx}px 0` }, ms);
    await done(swing);
  }
  async function lower(d, f) {
    d = Math.max(0, d);
    const ms = (240 + Math.abs(d - drop) * 2.2) * f;
    drop = d;
    await Promise.all([go(vine, { height: `${VINE + d}px` }, ms), go(rig, { translate: `0 ${d}px` }, ms)]);
  }
  const holdTop = () => TRACK_TOP + VINE + HOLD_TOP;

  async function grab(el, f) {
    const clone = el.cloneNode(true);
    clone.classList.remove('zz', 'off');
    const before = el.getBoundingClientRect();
    el.style.visibility = 'hidden';
    clone.style.setProperty('--r', '-3deg');
    hold.replaceChildren(clone);
    const after = clone.getBoundingClientRect();
    await done(clone.animate([{ translate: `${before.left - after.left}px ${before.top - after.top}px` }, { translate: '0 0' }],
      { duration: 280 * f, easing: OUT }));
    return clone;
  }

  async function dropInto(clone, b, f) {
    const r = rel(clone), m = rel(b.querySelector('.mouth'));
    Object.assign(clone.style, { left: `${r.x}px`, top: `${r.y}px`, width: `${r.w}px` });
    fly.append(clone);
    const s = Math.min(1, (m.w * 0.9) / r.w), dx = m.cx - r.cx, fall = m.cy - (r.y + r.h * (1 + s) / 2);
    await done(clone.animate([{ translate: '0 0', scale: 1 }, { translate: `${dx}px ${fall}px`, scale: s }], { duration: 300 * f, easing: IN, fill: 'forwards' }));
    await done(clone.animate([{ translate: `${dx}px ${fall}px`, scale: s, clipPath: 'inset(0 0 0 0)' },
      { translate: `${dx}px ${fall + r.h * s}px`, scale: s, clipPath: 'inset(0 0 100% 0)' }], { duration: 240 * f, easing: 'linear', fill: 'forwards' }));
    clone.remove();
    bump(b);
  }

  // one file, start to finish: fetch it, read it, name it, put it away (it stays put away)
  async function pick(id, f, r) {
    const el = cards.get(id), b = basketOf.get(id), item = items.get(id);
    if (!el || !b) return;
    const c = rel(el);
    await travel(c.cx - W / 2, f); if (r !== run) return;
    await lower(c.y - holdTop() + 2, f); if (r !== run) return;
    const clone = await grab(el, f); if (r !== run) return;
    settle(() => { el.hidden = true; });  // the pile closes the gap
    await lower(0, f); if (r !== run) return;
    await analyse(clone, item, f, r); if (r !== run) return;
    if (item.new_name) {
      think('Gemma 4', 'giving it a real name…');
      await retype(clone, item.new_name, f, r); if (r !== run) return;
      renamed.add(id);
    }
    think(...verdict(item));
    await sleep(1100 * f); if (r !== run) return;
    const m = rel(b.querySelector('.mouth'));
    await travel(m.cx - W / 2, f); if (r !== run) return;
    await lower(m.y - clone.offsetHeight - 12 - holdTop(), f); if (r !== run) return;
    unthink();
    inBasket.add(id);
    await dropInto(clone, b, f); if (r !== run) return;
    b.filled += 1;
    count(b);
    await lower(0, f);
  }

  // a parabola from the pile to the basket (or back again)
  async function arc(id, k, back) {
    const b = basketOf.get(id), el = cards.get(id);
    if (!b || !el) return;
    const home = rel(el), m = rel(b.querySelector('.mouth'));
    const clone = el.cloneNode(true);
    clone.classList.remove('zz', 'off');
    if (!back && items.get(id)?.new_name) clone.querySelector('.n').textContent = items.get(id).new_name;
    Object.assign(clone.style, { left: `${home.x}px`, top: `${home.y}px`, width: `${home.w}px`, visibility: 'visible' });
    fly.append(clone);
    el.style.visibility = 'hidden';
    const dx = m.cx - home.cx, dy = m.cy - home.cy, H = 90 + (k % 3) * 22;
    const frames = Array.from({ length: 11 }, (_, s) => {
      const t = back ? 1 - s / 10 : s / 10;
      return { translate: `${dx * t}px ${dy * t - 4 * H * t * (1 - t)}px`, rotate: `${t * 220}deg`, scale: `${1 - 0.45 * t}`, opacity: t > 0.92 ? 0 : 1 };
    });
    await done(clone.animate(frames, { duration: 760, delay: k * 85, easing: 'cubic-bezier(.35,0,.55,1)', fill: 'forwards' }));
    clone.remove();
    if (back) {
      el.style.visibility = '';
    } else {
      b.filled += 1;
      count(b);
      bump(b);
    }
  }

  function moreLabel() {
    const n = hiddenLazy + hiddenBusy.filter((id) => !inBasket.has(id)).length;
    tray.querySelector('.more').textContent = n ? `+${n} more` : '';
  }
  // cards that stay behind glide into the gaps instead of jumping
  function settle(change) {
    const before = [...tray.querySelectorAll('.card')].filter((el) => !el.hidden).map((el) => [el, el.getBoundingClientRect()]);
    change();
    if (reduced.matches) return;
    for (const [el, b] of before) {
      if (el.hidden) continue;
      const a = el.getBoundingClientRect();
      if (b.left !== a.left || b.top !== a.top) el.animate([{ translate: `${b.left - a.left}px ${b.top - a.top}px` }, { translate: '0 0' }], { duration: 600, easing: OUT });
    }
  }

  // ---- public ----
  function snap() {
    for (const el of [sloth, sway, vine, rig, fly, hold, baskets, tray]) el.getAnimations({ subtree: true }).forEach((a) => a.cancel());
    fly.replaceChildren();
    hold.replaceChildren();
    unthink();
    drop = 0;
    sloth.style.translate = `${x}px 0`;
    vine.style.height = `${VINE}px`;
    rig.style.translate = '0 0';
    for (const [id, el] of cards) {
      el.hidden = inBasket.has(id);
      el.style.visibility = '';
      if (renamed.has(id)) el.querySelector('.n').textContent = items.get(id).new_name;
    }
    if (tray.querySelector('.more')) moreLabel();
    for (const b of baskets.children) {
      b.filled = b.ids.filter((id) => inBasket.has(id)).length;
      count(b);
    }
  }
  function stop() {
    run += 1;
    mode = null;
    snap();
  }

  function setPlan(plan) {
    stop();
    inBasket.clear(); off.clear(); renamed.clear();
    items = new Map(plan.items.map((i) => [i.id, i]));
    const groups = new Map();
    for (const i of plan.items) if (i.folder) groups.set(i.folder_name, [...(groups.get(i.folder_name) ?? []), i]);
    const sorted = [...groups].sort((a, b) => b[1].length - a[1].length);
    const shown = sorted.slice(0, sorted.length > 4 ? 3 : 4);
    const rest = sorted.slice(shown.length);
    if (rest.length) shown.push([`+${rest.length} folders`, rest.flatMap(([, v]) => v), true]);
    basketOf = new Map();
    baskets.replaceChildren(...shown.map(([name, its, more]) => {
      const b = document.createElement('div');
      b.className = 'basket';
      b.innerHTML = '<div class="tag"><span></span></div><div class="mouth"></div><div class="weave"><b></b></div>';
      b.querySelector('.tag span').textContent = name;
      if (!more && its.some((i) => i.by === 'new_folder')) b.querySelector('.tag').insertAdjacentHTML('beforeend', '<em class="new">new</em>');
      b.ids = its.map((i) => i.id);
      b.total = its.length;
      b.filled = 0;
      count(b);
      for (const i of its) basketOf.set(i.id, b);
      return b;
    }));

    tray.querySelectorAll('.card, .more').forEach((e) => e.remove());
    cards = new Map();
    const cap = narrow.matches ? 9 : 16;
    const busy = plan.items.filter((i) => i.action !== 'leave').map((i) => ({ id: i.id, name: i.name }));
    const lazy = [...plan.items.filter((i) => i.action === 'leave').map((i) => ({ id: i.id, name: i.name, badge: '💤' })),
      ...plan.skipped.map((s) => ({ name: s.name, badge: /secret|key/i.test(s.why) ? '🔒' : '💤' }))];
    const nLazy = Math.min(lazy.length, 3);
    const pile = [...busy.slice(0, cap - nLazy), ...lazy.slice(0, nLazy)];
    pile.splice(3, 0, ...pile.splice(pile.length - nLazy, nLazy));  // mix a couple of sleepers into the pile
    const order = [];
    pile.forEach((p, k) => {
      const el = card(p.name, p.badge, k);
      tray.append(el);
      if (p.id !== undefined && !p.badge) { cards.set(p.id, el); order.push(p.id); }
    });
    const more = document.createElement('span');
    more.className = 'more';
    more.textContent = '+99 more';
    tray.append(more);
    const top = tray.getBoundingClientRect().top + 26;
    while (order.length && tray.querySelector('.card').getBoundingClientRect().top < top) {  // fit the pile to the tray
      const id = order.pop();
      cards.get(id).remove();
      cards.delete(id);
    }
    hiddenBusy = busy.map((b) => b.id).filter((id) => !cards.has(id));
    hiddenLazy = lazy.length - nLazy;
    moreLabel();
    if (!reduced.matches) {
      tray.querySelectorAll('.card').forEach((el, k) =>
        el.animate([{ opacity: 0, translate: '0 -40px' }, { opacity: 1, translate: '0 0' }], { duration: 520, delay: 60 + k * 35, easing: OUT, fill: 'backwards' }));
      [...baskets.children].forEach((b, k) =>
        b.animate([{ opacity: 0, scale: 0.85 }, { opacity: 1, scale: 1 }], { duration: 480, delay: 200 + k * 80, easing: OUT, fill: 'backwards' }));
    }
  }

  // the demo: the sloth works through the pile on its own, slowly, file by file
  async function work(ids) {
    stop();
    const r = run;
    mode = 'work';
    const mine = () => ids.filter((id) => !off.has(id));
    if (reduced.matches || document.hidden) { finish(mine()); return true; }
    await sleep(1200);
    let f = 1;
    for (const id of ids.filter((i) => cards.has(i) && basketOf.has(i))) {
      if (r !== run) return false;
      if (off.has(id) || inBasket.has(id)) continue;
      await pick(id, f, r);
      f = Math.max(0.6, f * 0.9);
      await sleep(600 * f);
    }
    for (const id of ids.filter((i) => cards.has(i) && !basketOf.has(i) && !off.has(i))) {  // renamed, staying put
      if (r !== run) return false;
      await retype(cards.get(id), items.get(id).new_name, 1, r);
      renamed.add(id);
    }
    if (r !== run) return false;
    finish(mine());
    return true;
  }

  // waiting for you: the sloth ambles along the branch and peers at the pile
  async function look() {
    if (mode === 'look') return;
    stop();
    const r = run;
    mode = 'look';
    if (reduced.matches) return;
    while (r === run) {
      await travel(Math.random() * (stage.clientWidth - W), 1.5); if (r !== run) return;
      await lower(40, 1.3); if (r !== run) return;
      await sleep(600);
      await lower(0, 1.3);
      await sleep(400);
    }
  }

  function finish(ids) {
    settle(() => {
      stop();
      for (const id of ids) {
        if (basketOf.has(id)) inBasket.add(id);
        if (items.get(id)?.new_name) renamed.add(id);
      }
      snap();
    });
  }

  // Approve: the sloth does the first few files in full, then tosses the rest in
  async function sort(ids, { solo = 2 } = {}) {
    stop();
    const r = run;
    mode = 'sort';
    if (reduced.matches || document.hidden) return finish(ids);
    const todo = ids.filter((id) => basketOf.has(id) && !inBasket.has(id));
    ids.filter((id) => !basketOf.has(id) && cards.has(id) && !renamed.has(id)).forEach((id) => {
      renamed.add(id);
      retype(cards.get(id), items.get(id).new_name, 0.7, r);
    });
    const first = todo.filter((id) => cards.has(id)).slice(0, solo);
    let f = 0.6;
    for (const id of first) {
      await pick(id, f, r);
      if (r !== run) return;
      f *= 0.8;
    }
    sway.animate([{ rotate: '0deg' }, { rotate: '-9deg' }, { rotate: '7deg' }, { rotate: '0deg' }], { duration: 760, easing: 'ease-in-out' });
    await Promise.all(todo.filter((id) => !first.includes(id)).map((id, k) => arc(id, k, false)));
    if (r === run) finish(ids);
  }

  async function unsort(ids) {
    stop();
    const r = run;
    const back = ids.filter((id) => inBasket.has(id) && cards.has(id));
    settle(() => {  // reopen the gaps so each card knows where home is, then fly them back
      for (const id of ids) { inBasket.delete(id); renamed.delete(id); }
      snap();
      for (const id of back) cards.get(id).style.visibility = 'hidden';
      for (const [id, el] of cards) el.querySelector('.n').textContent = items.get(id).name;
    });
    if (!reduced.matches && !document.hidden) {
      await Promise.all(back.map((id, k) => arc(id, k, true)));
    }
    if (r === run) snap();
  }

  function setOff(id, isOff) {
    if (isOff) off.add(id); else off.delete(id);
    cards.get(id)?.classList.toggle('off', isOff);
  }

  return { setPlan, work, look, sort, unsort, finish, stop, setOff, get busy() { return mode === 'sort' || mode === 'work'; } };
}
