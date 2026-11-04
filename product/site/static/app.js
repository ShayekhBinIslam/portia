/* Portia: the single-page UI. Routes: #/ (cases), #/case/<id>, #/job/<id>, #/new, #/history, #/how. */
'use strict';

// ------------------------------------------------------------------ helpers
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const fmtInt = (n) => (n == null ? '—' : Number(n).toLocaleString('en-US'));
const mmss = (s) => { s = Math.max(0, Math.round(s || 0)); const m = Math.floor(s / 60); return `${m}:${String(s % 60).padStart(2, '0')}`; };
const shortTok = (n) => (n >= 1e6 ? `${(n / 1e6).toFixed(1)}M` : n >= 1e3 ? `${Math.round(n / 1e3)}k` : String(n || 0));
// The static gallery (GitHub Pages, product/build_static.py) sets window.PORTIA_STATIC = {live: "<live app URL>"}:
// every read comes from an exported JSON file, and runs are recorded investigations replayed in the browser.
const STATIC = window.PORTIA_STATIC || null;
function staticPath(path) {
  const fixed = { '/api/library': 'library', '/api/corpus': 'corpus', '/api/proof': 'proof', '/api/health': 'health', '/api/demo': 'demo',
    '/api/jobs': 'jobs', '/api/collections': 'collections', '/api/batches': 'batches' };
  if (fixed[path]) return `data/${fixed[path]}.json`;
  const rules = [[/^\/api\/titles\/(.+)$/, 'titles'], [/^\/api\/footage\/(.+)$/, 'footage'], [/^\/api\/case\/([^/]+)\/truth$/, 'truth'], [/^\/api\/case\/([^/]+)$/, 'case'],
    [/^\/api\/jobs\/([^/]+)\/events\.json$/, 'events'], [/^\/api\/jobs\/([^/]+)$/, 'job'], [/^\/api\/batches\/([^/]+)$/, 'batch']];
  for (const [rx, dir] of rules) { const m = path.match(rx); if (m) return `data/${dir}/${m[1]}.json`; }
  return null;
}
const media = (src) => (STATIC ? String(src || '').replace(/^\//, '') : src);
// public mode: starting work needs the access code from the submission (server.py access_gate); it is kept per device
const codeStore = { get: () => { try { return localStorage.getItem('portia-code') || ''; } catch (e) { return ''; } },
  set: (c) => { try { localStorage.setItem('portia-code', c); } catch (e) { /* private window: ask again next time */ } } };
function askCode(again) {
  return new Promise((resolve) => {
    let d = document.getElementById('codedlg');
    if (!d) { d = document.createElement('dialog'); d.id = 'codedlg'; d.className = 'card codedlg'; document.body.appendChild(d); }
    d.innerHTML = `<form method="dialog"><div class="h3">Access code</div>
      <p class="small muted" style="margin:8px 0 12px">${again ? 'That code did not work. ' : ''}Starting new runs on this public demo needs an access code, since every run uses Muse Glimmer compute. Browsing and replaying every recorded investigation needs none.</p>
      <input id="codein" autocomplete="off" spellcheck="false" placeholder="access code" style="width:100%">
      <div class="row" style="justify-content:flex-end;gap:8px;margin-top:14px"><button value="cancel" class="btn">Cancel</button><button value="ok" class="btn primary">Continue</button></div></form>`;
    d.onclose = () => resolve(d.returnValue === 'ok' ? d.querySelector('#codein').value.trim() : null);
    d.showModal();
  });
}
async function api(path, opts, tries = 0) {
  if (STATIC) {
    if (opts && opts.method && opts.method !== 'GET') {
      throw new Error(`This is the static gallery of recorded investigations. New runs need the live app${STATIC.live ? `: ${STATIC.live}` : '.'}`);
    }
    const f = staticPath(path);
    const r = f ? await fetch(f) : null;
    if (!r || !r.ok) throw new Error('This is not part of the static gallery.');
    return r.json();
  }
  const write = opts && opts.method && opts.method !== 'GET';
  const r = await fetch(path, write ? { ...opts, headers: { ...(opts.headers || {}), 'X-Portia-Code': codeStore.get() } } : opts);
  if (r.status === 401 && write && tries < 3) {
    const code = await askCode(tries > 0 || !!codeStore.get());
    if (!code) throw new Error('Starting new runs on the live demo needs the access code.');
    codeStore.set(code);
    return api(path, opts, tries + 1);
  }
  if (!r.ok) {
    let msg = r.statusText;
    try {
      const d = (await r.json()).detail;
      msg = Array.isArray(d) ? d.map((x) => `${(x.loc || []).slice(-1)[0] || 'input'}: ${x.msg}`).join('; ') : d || msg;
    } catch (e) { /* not JSON */ }
    throw new Error(msg);
  }
  return r.json();
}
const S = { lib: null, corpus: null, health: null, titles: {}, opts: { agents: 3, resolve: 'glimmer', quick: false }, stream: null, clock: null,
  filter: { domain: STATIC ? 'Recorded' : 'All', q: '' }, showAll: false };

const svg = (p) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${p}</svg>`;
const IC = {
  search: svg('<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>'),
  zoom: svg('<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5M11 8v6M8 11h6"/>'),
  burst: svg('<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M7 5v14M17 5v14M3 9h4M3 15h4M17 9h4M17 15h4"/>'),
  sheet: svg('<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>'),
  doc: svg('<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5M9 13h6M9 17h6"/>'),
  grep: svg('<path d="M4 6h16M4 12h10M4 18h7"/><circle cx="18" cy="16" r="3"/><path d="m22 20-1.8-1.8"/>'),
  frames: svg('<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="2"/><path d="m21 16-5-5-9 9"/>'),
  list: svg('<path d="M9 6h12M9 12h12M9 18h12"/><circle cx="4" cy="6" r="1"/><circle cx="4" cy="12" r="1"/><circle cx="4" cy="18" r="1"/>'),
  video: svg('<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m10 9 5 3-5 3z"/>'),
  answer: svg('<circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/>'),
  arrow: svg('<path d="M5 12h14M13 6l6 6-6 6"/>'),
  play: svg('<path d="M7 4v16l13-8z"/>'),
};
const TOOL = {
  search: ['search', 'Search all videos'], search_video: ['video', 'Search one video'], grep_transcripts: ['grep', 'Grep transcripts'],
  read_transcript: ['doc', 'Read transcript'], view_frames: ['frames', 'View frames'], contact_sheet: ['sheet', 'Contact sheet'],
  zoom: ['zoom', 'Zoom'], burst: ['burst', 'Burst'], list_videos: ['list', 'List videos'], answer: ['answer', 'Answer'],
};
function toolArg(name, a) {
  a = a || {};
  const vid = (v) => { const id = String(v || '').split('@')[0]; const t = S.titles[id]; return t ? `${t.slice(0, 48)}${t.length > 48 ? '…' : ''}` : id; };
  if (name === 'search' || name === 'grep_transcripts') return `"${a.query || a.pattern || ''}"`;
  if (name === 'search_video') return `${vid(a.video)} · "${a.query || ''}"`;
  if (name === 'zoom') return `${vid(a.video)} @ ${a.t ?? ''}${a.region ? ` · ${a.region}` : ''}`;
  if (name === 'burst') return `${vid(a.video)} @ ${a.t ?? ''}`;
  if (name === 'contact_sheet' || name === 'read_transcript') return `${vid(a.video || a.handle)} ${a.start ?? ''}${a.end ? `-${a.end}` : ''}`;
  if (name === 'view_frames') return vid(a.handle);
  if (name === 'answer') return `${a.verdict || ''}`;
  return Object.values(a).join(' · ');
}

// ------------------------------------------------------------------ theme + status
(function theme() {
  const k = 'portia-theme';
  try { const t = localStorage.getItem(k); if (t) document.documentElement.dataset.theme = t; } catch (e) { /* storage off */ }
  $('#theme').onclick = () => {
    const cur = document.documentElement.dataset.theme || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
    const nx = cur === 'dark' ? 'light' : 'dark';
    document.documentElement.dataset.theme = nx;
    try { localStorage.setItem(k, nx); } catch (e) { /* storage off */ }
    if (S.mapResize) S.mapResize();                     // the search map paints with the theme's colours
  };
})();
async function health() {
  if (STATIC) {
    S.health = { spark: { available: false } };
    $('#status').innerHTML = `<span class="pill"><i class="dot up"></i>Gallery of recorded investigations</span>${STATIC.live ? `<a class="pill" href="${esc(STATIC.live)}" target="_blank" rel="noopener">Live app ↗</a>` : ''}`;
    return;
  }
  try { S.health = await api('/api/health'); } catch (e) { S.health = null; }
  const h = S.health, el = $('#status');
  if (!h) { el.innerHTML = '<span class="pill"><i class="dot down"></i>server offline</span>'; return; }
  const up = h.servers.filter((s) => s.up).length, running = h.servers.reduce((a, s) => a + (s.running || 0), 0);
  const srv = `<span class="pill" title="Muse Glimmer 30B: ${up} of ${h.servers.length} servers answering, ${running} requests running"><i class="dot ${up ? 'up' : 'down'}"></i>Muse Glimmer</span>`;
  const sp = h.spark, s13 = h.spark13 || { available: false };
  const spTip = (name, x) => `${name}: ${x.available ? `ready; product spend $${x.product_spent_usd.toFixed(3)} of $${x.product_budget_usd.toFixed(2)}` : 'locked or budget reached'}`;
  const spLabel = sp.available && s13.available ? 'Spark ready' : sp.available ? 'Spark Open ready' : s13.available ? 'Spark 1.3 ready' : 'Spark off';
  el.innerHTML = srv + `<span class="pill opt" title="the query encoder for search"><i class="dot ${h.encoder ? 'up' : 'down'}"></i>Search index</span>`
    + `<span class="pill opt" title="optional adjudicators for splits. ${esc(spTip('Muse Spark Open (Baseten)', sp))}. ${esc(spTip('Muse Spark 1.3 (Meta Model API)', s13))}."><i class="dot ${sp.available || s13.available ? 'up' : ''}"></i>${spLabel}</span>`;
}
health();
if (!STATIC) setInterval(health, 15000);

// ------------------------------------------------------------------ lightbox
const LB = { list: [], i: 0 };
function openLightbox(list, i) {
  LB.list = list; LB.i = i;
  showLB();
  $('#lightbox').classList.add('on');
}
function showLB() {
  const s = LB.list[LB.i];
  if (!s) return;
  $('#lightbox img').src = s.src;
  $('#lightbox .cap').textContent = `${s.cap || ''}  ·  ${LB.i + 1} / ${LB.list.length}`;
}
$('#lightbox').addEventListener('click', (e) => {
  if (e.target.classList.contains('nav-l')) { LB.i = (LB.i - 1 + LB.list.length) % LB.list.length; showLB(); return; }
  if (e.target.classList.contains('nav-r')) { LB.i = (LB.i + 1) % LB.list.length; showLB(); return; }
  if (e.target.tagName !== 'IMG') $('#lightbox').classList.remove('on');
});
document.addEventListener('keydown', (e) => {
  if (!$('#lightbox').classList.contains('on')) return;
  if (e.key === 'Escape') $('#lightbox').classList.remove('on');
  if (e.key === 'ArrowLeft') { LB.i = (LB.i - 1 + LB.list.length) % LB.list.length; showLB(); }
  if (e.key === 'ArrowRight') { LB.i = (LB.i + 1) % LB.list.length; showLB(); }
});
document.addEventListener('click', (e) => {
  const shot = e.target.closest('.shot');
  if (!shot) return;
  const box = shot.closest('[data-gallery]') || shot.parentElement;
  const all = $$('.shot', box);
  openLightbox(all.map((x) => ({ src: x.dataset.src, cap: x.dataset.cap })), all.indexOf(shot));
});
const shotsHTML = (imgs, cap, wide) => `<div class="shots${wide ? ' wide' : ''}">${(imgs || []).map((im) =>
  `<div class="shot" data-src="${esc(media(im.src))}" data-cap="${esc(`${cap}${im.label ? ` · ${im.label}` : ''}`)}"><img loading="lazy" src="${esc(media(im.src))}" alt="">${im.label ? `<span>${esc(im.label)}</span>` : ''}</div>`).join('')}</div>`;

// ------------------------------------------------------------------ router
async function demoPage() {
  const d = await api('/api/demo');
  location.replace(d.job ? `#/job/${d.job}?play=4` : `#/case/${d.case}`);   // replace, so Back returns to the page before
}
const ROUTES = { '': home, case: casePage, job: jobPage, new: newPage, history: historyPage, how: howPage, proof: proofPage, demo: demoPage,
  audit: batchesPage, batch: batchPage };
function route() {
  if (S.stream) { S.stream.close(); S.stream = null; }
  if (S.clock) { clearInterval(S.clock); S.clock = null; }
  if (S.replay) { clearTimeout(S.replay); S.replay = null; }
  if (S.hero) { clearTimeout(S.hero); S.hero = null; }
  const [path, qs] = location.hash.replace(/^#\/?/, '').split('?');
  const [name, arg] = path.split('/');
  const r = ROUTES[name] ? name : '';
  $$('#nav a').forEach((a) => a.classList.toggle('on', a.dataset.r === ({ '': 'home', case: 'home', job: 'home', batch: 'audit' }[r] || r)));
  window.scrollTo(0, 0);
  ROUTES[r](arg ? decodeURIComponent(arg) : undefined, new URLSearchParams(qs || '')).catch((e) => {
    $('#app').innerHTML = `<div class="banner err">${esc(e.message || e)}</div>`;
  });
}
window.addEventListener('hashchange', route);
async function loadLib() {
  if (!S.lib) S.lib = await api('/api/library');
  if (!S.corpus) S.corpus = await api('/api/corpus');
}

// ------------------------------------------------------------------ home
const FLOW = `<svg viewBox="0 0 560 300" role="img" aria-label="Three investigators, a vote, an adjudicator on disagreement, a verdict">
  <defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0 10 5 0 10z" style="fill:var(--muted)"/></marker></defs>
  <g font-family="Inter, sans-serif" font-size="12.5">
    ${[0, 1, 2].map((i) => `<g transform="translate(14 ${28 + i * 86})"><rect width="168" height="62" rx="14" style="fill:var(--surface);stroke:var(--line-2)"/>
      <rect x="12" y="13" width="36" height="36" rx="11" style="fill:var(--brand)"/><text x="30" y="37" text-anchor="middle" fill="#fff" font-family="Instrument Serif, serif" font-size="21">${i + 1}</text>
      <text x="58" y="29" font-weight="600" style="fill:var(--ink)">Investigator</text><text x="58" y="46" font-size="11.5" style="fill:var(--muted)">Muse Glimmer</text></g>`).join('')}
    <path d="M182 59 C 228 59, 228 150, 262 150 M182 145 L262 150 M182 231 C 228 231, 228 150, 262 150" stroke-width="2" fill="none" style="stroke:var(--line-2)"/>
    <g transform="translate(262 120)"><rect width="88" height="60" rx="14" style="fill:var(--brand-soft);stroke:var(--brand)"/>
      <text x="44" y="27" text-anchor="middle" font-weight="700" style="fill:var(--brand)">Vote</text><text x="44" y="44" text-anchor="middle" font-size="11" style="fill:var(--brand)">agree?</text></g>
    <path d="M350 138 C 390 138, 392 64, 430 64" stroke-width="2" fill="none" marker-end="url(#ah)" style="stroke:var(--ok)"/>
    <text x="382" y="92" text-anchor="end" font-size="11" font-weight="600" style="fill:var(--ok)">yes · 74%</text>
    <path d="M350 162 C 390 162, 392 230, 430 230" stroke-width="2" fill="none" marker-end="url(#ah)" style="stroke:var(--warn)"/>
    <text x="382" y="222" text-anchor="end" font-size="11" font-weight="600" style="fill:var(--warn)">split · 26%</text>
    <g transform="translate(432 34)"><rect width="116" height="60" rx="14" style="fill:var(--ok-soft);stroke:var(--ok)"/>
      <text x="58" y="27" text-anchor="middle" font-weight="700" style="fill:var(--ok)">Verdict</text><text x="58" y="44" text-anchor="middle" font-size="11" style="fill:var(--ok)">A or B</text></g>
    <g transform="translate(432 200)"><rect width="116" height="62" rx="14" style="fill:var(--surface);stroke:var(--line-2)"/>
      <text x="58" y="25" text-anchor="middle" font-weight="600" style="fill:var(--ink)">Adjudicator</text><text x="58" y="42" text-anchor="middle" font-size="10.5" style="fill:var(--muted)">checks the evidence,</text><text x="58" y="55" text-anchor="middle" font-size="10.5" style="fill:var(--muted)">not the votes</text></g>
    <path d="M490 200 L490 98" stroke-width="2" fill="none" marker-end="url(#ah)" stroke-dasharray="4 4" style="stroke:var(--line-2)"/>
  </g></svg>`;

async function home() {
  $('#app').innerHTML = `<section class="hero">
      <div>
        <div class="tag brand">Built on Meta's Muse Glimmer (open weights; runs on Modal or Fireworks) and Muse Spark</div>
        <h1 class="display" style="margin-top:16px">Which answer does the <em>video</em> actually support?</h1>
        <p class="lede" style="margin-top:18px">Teams building video AI compare model answers about long footage every day, and the answers differ in small details: a count, a colour, a caption that was never there.
          Portia is the judge. Give it a question and two answers; three Muse Glimmer agents search hours of footage, zoom into the frames that matter and rule, Muse Spark 1.3 double-checks,
          and the verdict comes back with the exact frames and a measured trust level.</p>
        <a class="card catch" href="#/demo"><span class="tag ok">Caught</span><span>All three agents said the notebook held sketches of human ears. Muse Spark 1.3 checked the page a few seconds earlier: <b>cubes and boxes</b>.</span><span class="go">${IC.play}</span></a>
        <div class="cta"><a class="btn primary big" href="#/demo">${IC.play} Watch Portia catch a mistake</a><a class="btn big" href="#/audit">Audit a batch</a><a class="btn big" href="#/proof">See the proof</a></div>
        <div class="stats" id="stats"></div>
      </div>
      <a class="card heromap" id="heromap" href="#/demo" aria-label="A replay of a recorded investigation: where the agents looked, and the frame the verdict cites. Opens the full case."><div class="skeleton"></div><div class="skeleton" style="width:70%"></div></a>
    </section>
    <div class="section-head" style="margin-top:6px"><div><div class="h3">Meta's models in Portia</div><h2 class="h2">Three Muse models, each where it measured best</h2></div></div>
    <div class="metastrip">
      <div class="card pad mstack"><b class="mname">Muse Glimmer 30B</b><div class="mwhere">Open weights · deployed on Modal and Fireworks</div>
        <p>The three investigators: they search the footage, read transcripts and zoom into frames, up to 8 turns each. Also the default adjudicator.</p><div class="mnum"><b>$0</b>API cost per case</div></div>
      <div class="card pad mstack"><b class="mname">Muse Spark 1.3</b><div class="mwhere">Meta Model API</div>
        <p>Re-checks every verdict on the investigators' own evidence, including the ones all three agreed on.</p><div class="mnum"><b>82.0%</b>right in development, 81.6% held-out · about $0.004 per case</div></div>
      <div class="card pad mstack"><b class="mname">Muse Spark Open</b><div class="mwhere">Open weights on Baseten</div>
        <p>An adjudicator for the cases where the investigators split.</p><div class="mnum"><b>80.5%</b>right · $0.017 per case</div></div>
    </div>
    <div class="whofor">
      <div class="card pad"><div class="h3">Video-AI evaluation teams</div><p>A pairwise judge for a model's answers about long videos: upload an evaluation run as a CSV or call the API, get a verdict per case with the frames that justify it, for about $4 per 1,000 cases (or no API cost on Muse Glimmer alone) instead of people watching footage.</p></div>
      <div class="card pad"><div class="h3">Media and compliance</div><p>Check an AI-written account of a broadcast, lecture or meeting against a variant before it goes out: Portia shows which details the footage supports and which it does not.</p></div>
      <div class="card pad"><div class="h3">Anyone who has to trust it</div><p>Every verdict says how far to trust it, from a measured track record: auto-accept the reliable ones (93% right) and send the rest to a person with the cited frames.</p></div>
    </div>
    <div class="section-head"><div><div class="h3">Featured cases</div><h2 class="h2">Hand-picked from the development set</h2></div></div>
    <div class="grid3" id="featured"><div class="skeleton"></div></div>
    <div id="uploaddemo"></div>
    <div class="section-head"><div class="grow"><div class="h3">Case library</div><h2 class="h2">220 development cases, 7 domains</h2></div>
      <label class="search">${IC.search}<input id="q" placeholder="Search questions" value="${esc(S.filter.q)}"></label></div>
    <div class="row" id="chips" style="margin-bottom:12px"></div>
    <div class="card list" id="list"><div class="pad"><div class="skeleton"></div></div></div>`;
  heroMap();
  await loadLib();
  if (STATIC && !S.recorded) S.recorded = new Set((await api('/api/jobs')).jobs.map((j) => j.case_id));
  const st = Object.entries(S.corpus).filter(([d]) => !d.startsWith('Your video:')).map(([, v]) => v);
  const vids = st.reduce((s, d) => s + d.videos, 0), hrs = st.reduce((s, d) => s + d.hours, 0);
  $('#stats').innerHTML = [[fmtInt(vids), 'videos indexed'], [`${Math.round(hrs)} h`, 'of footage to search'], ['81%', 'right on held-out data, Muse Glimmer alone (no API cost)'], ['88.6%', 'right when marked safe to accept (held-out)']]
    .map(([b, s]) => `<div class="stat"><b>${b}</b><span>${s}</span></div>`).join('');
  const byId = Object.fromEntries(S.lib.cases.map((c) => [c.id, c]));
  $('#featured').innerHTML = S.lib.featured.map((id) => byId[id]).filter(Boolean).map((c) => `<a class="card case-card" href="#/case/${esc(c.id)}">
      <div class="row"><span class="tag brand">${esc(domName(c.domain))}</span><span class="tag">${esc(caseNo(c.id))}</span></div>
      <div class="q" title="${esc(c.question)}">${esc(c.gloss || c.question)}</div>${disputedHTML(c, 1)}<div class="foot">Open case <span style="margin-left:auto;display:inline-flex;width:16px">${IC.arrow}</span></div></a>`).join('');
  const chips = [...(STATIC ? ['Recorded'] : []), 'All', ...S.lib.domains];
  $('#chips').innerHTML = chips.map((d) => `<button class="chip${S.filter.domain === d ? ' on' : ''}" data-d="${esc(d)}">${esc(d)}</button>`).join('');
  $('#chips').onclick = (e) => {
    const b = e.target.closest('[data-d]');
    if (!b) return;
    S.filter.domain = b.dataset.d;
    S.showAll = false;
    $$('#chips .chip').forEach((x) => x.classList.toggle('on', x === b));
    drawList();
  };
  $('#q').oninput = (e) => { S.filter.q = e.target.value; drawList(); };
  api('/api/demo').then((d) => {                    // an uploaded film (CC BY 3.0) with a Muse Voice Transcribe transcript
    if (!d.upload_job || !$('#uploaddemo')) return;
    $('#uploaddemo').innerHTML = `<a class="card catch wide" href="#/job/${esc(d.upload_job)}?play=2"><span class="tag brand">Uploaded video</span>`
      + '<span>Blender\'s open film <i>Tears of Steel</i> (CC BY 3.0), transcribed by Muse Voice Transcribe. Which actor plays the man with the mechanical eyepiece, and what colour is his jacket? The three agents and Muse Spark 1.3 agree on the frame at 3:17 and the closing credits.</span>'
      + `<span class="go">${IC.play}</span></a>`;
  }).catch(() => {});
  drawList();
}
function drawList() {
  const q = S.filter.q.trim().toLowerCase();
  const rows = S.lib.cases.filter((c) => (S.filter.domain === 'All' || c.domain === S.filter.domain
    || (S.filter.domain === 'Recorded' && S.recorded && S.recorded.has(c.id))) && (!q || c.question.toLowerCase().includes(q) || (c.gloss || '').toLowerCase().includes(q)));
  const shown = S.showAll ? rows : rows.slice(0, window.innerWidth < 720 ? 12 : 40);
  $('#list').innerHTML = (shown.map((c) => `<a href="#/case/${esc(c.id)}"><span class="tag${S.recorded && S.recorded.has(c.id) ? ' brand' : ''}" title="${S.recorded && S.recorded.has(c.id) ? 'has a recorded investigation' : ''}">${S.recorded && S.recorded.has(c.id) ? '▶ ' : ''}${esc(domName(c.domain))}</span><span class="id">${esc(caseNo(c.id).replace('Case ', '#'))}</span><span class="q" title="${esc(c.question)}">${esc(c.gloss || c.question)}${c.disputed && c.disputed.length ? `<span class="dline">Disputed: ${esc(c.disputed.slice(0, 1).map(([a, b]) => `${a} vs ${b}`).join(''))}</span>` : ''}</span><span style="display:inline-flex;width:16px;color:var(--muted)">${IC.arrow}</span></a>`).join('')
    || '<div class="pad muted">No case matches.</div>')
    + (rows.length > shown.length ? `<div class="pad" style="text-align:center"><button class="btn" id="more">Show all ${rows.length}</button></div>` : '');
  const m = $('#more');
  if (m) m.onclick = () => { S.showAll = true; drawList(); };
}

// ------------------------------------------------------------------ hero: the demo run's search, replayed in a loop
// Fable's review: show the product on the first screen. The recorded demo run's tool calls land on the search
// map in order, the moments the verdict cites ring, then the frame it cites appears; about 12 seconds, looping only
// while the card is in view. Reduced motion: the finished map, still. Click: the full replay (#/demo).
const HERO = { lead: 300, search: 6800, settle: 450, cited: 1700, frame: 3400, fade: 550 };
async function heroMap() {
  const card = $('#heromap');
  const fallback = () => { if (card && card.isConnected) { card.className = 'card flow'; card.innerHTML = FLOW; } };
  try {
    const d = await api('/api/demo');
    if (!d.job) { fallback(); return; }
    const [meta, { events }] = await Promise.all([api(`/api/jobs/${d.job}`), api(`/api/jobs/${d.job}/events.json`)]);
    const [f] = await Promise.all([api(`/api/footage/${encodeURIComponent(meta.case.domain)}`), loadTitles(meta.case.domain)]);
    if (!card.isConnected) return;
    // the run, read without a board: the tool calls the map shows, the frames they returned, the rationales, the verdict
    const J = { c: meta.case, cfg: meta.config || {}, jid: d.job, meta, shots: [], rat: {}, play: 1 };
    const calls = [];
    let fin = null, vote = null;
    for (const ev of events) {
      if (ev.type === 'tool') {
        const mo = shotMoment(ev.tool, ev.args);
        if (mo) (ev.images || []).forEach((im) => J.shots.push({ vid: mo[0], t0: mo[1], t1: mo[2], src: im.src, tool: ev.tool, label: im.label }));
        if (LOOK[ev.tool] && MAPWHO[ev.role]) calls.push(ev);
      } else if (ev.type === 'agent_done') J.rat[ev.role] = { v: ev.verdict, text: cleanText(ev.rationale) };
      else if (ev.type === 'adj_start') J.adj = { model: ev.model };
      else if (ev.type === 'adj_done') J.rat.adj = { v: ev.verdict, text: cleanText(ev.rationale) };
      else if (ev.type === 'vote') vote = ev;
      else if (ev.type === 'final') fin = ev;
    }
    if (!fin || !calls.length) { fallback(); return; }
    const cited = citedShots(J, fin);
    const M = (J.map = { looks: [], done: 0, cells: new Map(), cited: cited.map((s) => ({ vid: s.vid, t: s.at != null ? s.at : s.t0 })),
      citedCells: [], hide: new Set(), pings: [], ev: 0, hover: -1, f, off: {}, starts: [] });
    let n = 0;
    f.videos.forEach((v, k) => { const c = Math.max(1, Math.ceil(v.dur / f.seg)); M.off[v.id] = [n, c, k]; M.starts.push(n); n += c; });
    M.n = n;
    calls.forEach((ev, k) => looksOf(ev).forEach(([vid, t]) => M.looks.push({ role: ev.role, tool: ev.tool, kind: LOOK[ev.tool][0], vid, t, e: k })));
    M.citedCells = [...new Set(M.cited.map((q) => cellOf(M, q.vid, q.t)).filter((i) => i >= 0))];

    const span = f.hours >= 1 ? `${Math.round(f.hours)} hours` : `${Math.max(1, Math.round(f.hours * 60))} minutes`;
    const adjName = { spark: 'Muse Spark Open', spark13: 'Muse Spark 1.3' }[J.adj && J.adj.model] || 'The Muse Glimmer adjudicator';
    const adjShort = { spark: 'Muse Spark Open', spark13: 'Muse Spark 1.3' }[J.adj && J.adj.model] || 'Glimmer adjudicator';
    const v = fin.verdict, k = M.citedCells.length;
    const CAP = {
      search: `Three Muse Glimmer agents search ${span} of footage`,
      adj: vote && !vote.contested ? `All three chose answer ${vote.vote}. ${adjName} re-checks their evidence` : `The agents split. ${adjName} checks the disputed details`,
      cited: `The verdict rests on ${k} moment${k === 1 ? '' : 's'} out of ${span}`,
      end: { spark13_overturn: `${adjName} overturned all three: answer ${v} is better supported`,
        spark13_confirm: `${adjName} confirmed the agents: answer ${v}`, unanimous: `All three agents agreed: answer ${v}` }[fin.how]
        || (['glimmer', 'spark', 'spark13'].includes(fin.how) ? `${adjName} ruled: answer ${v}` : `Verdict: answer ${v}`),
    };
    const sw = (r) => `<i style="background:var(${roleVar(r)})"></i>`;
    card.innerHTML = `<div class="hm-top"><span class="tag brand">Replay</span><b>${esc(caseNo(J.c.id))}</b><span class="muted">the recorded search, sped up</span></div>
      <div class="hm-cap" id="hm-cap"></div>
      <div class="hm-wrap"><canvas id="hm-cv" aria-hidden="true"></canvas>${cited[0] ? `<figure class="hm-frame" id="hm-frame"><img alt="The frame the verdict cites" src="${esc(media(cited[0].src))}"><figcaption>${esc(mmss(cited[0].at))} · the frame the verdict cites</figcaption></figure>` : ''}</div>
      <div class="hm-now" id="hm-now"></div>
      <div class="hm-legend"><span>${sw('inv0')}${sw('inv1')}${sw('inv2')}Muse Glimmer agents</span>${calls.some((e) => e.role === 'adj') ? `<span>${sw('adj')}${esc(adjShort)}</span>` : ''}<span><i class="ring"></i>cited by the verdict</span><span class="go">Open the full replay ${IC.arrow}</span></div>`;
    card.setAttribute('aria-label', `A replay of ${caseNo(J.c.id)}: where the agents looked in ${span} of footage, and the frame the verdict cites. Opens the full replay.`);
    M.cv = $('#hm-cv');
    const capEl = $('#hm-cap'), fig = $('#hm-frame'), now = $('#hm-now');
    const place = () => {                                // the frame sits on the side away from the ringed squares
      if (!fig || !k || !M.g) return;
      fig.classList.toggle('left', (M.citedCells[0] % M.g.cols) * M.g.p > M.g.W / 2);
    };
    S.mapResize = () => { if (M.cv.isConnected) requestAnimationFrame(() => { heroGeo(J); place(); }); };
    heroGeo(J); place();
    const setCap = (s) => { if (capEl.textContent !== s) capEl.textContent = s; };
    const putCall = (e, live) => {
      const col = cssVar(roleVar(calls[e].role));
      M.looks.forEach((L) => { if (L.e === e) { const i = mapPut(M, L); if (live && i >= 0) ping(J, i, col, { r: 10, dur: 700 }); } });
    };
    if (matchMedia('(prefers-reduced-motion: reduce)').matches) {
      calls.forEach((_, e) => putCall(e, false));
      M.citedOn = k > 0; mapPaint(J); setCap(CAP.end);
      if (fig) fig.classList.add('on');
      return;
    }
    const R = { e: 0, vis: true };
    const io = new IntersectionObserver((es) => { R.vis = es.some((x) => x.isIntersecting); }, { threshold: 0.15 });
    io.observe(card);
    const later = (fn, ms) => {                          // pauses while the card is off screen or the tab is hidden
      S.hero = setTimeout(() => {
        if (!M.cv.isConnected) { io.disconnect(); return; }
        if (document.hidden || !R.vis) { later(fn, 500); return; }
        fn();
      }, ms);
    };
    const step = HERO.search / calls.length;
    const start = () => {
      M.cells = new Map(); M.citedOn = false; M.pings = [];
      card.classList.remove('fading');
      if (fig) fig.classList.remove('on');
      now.classList.remove('on');
      setCap(CAP.search); mapPaint(J);
      R.e = 0; later(tick, HERO.lead);
    };
    const tick = () => {
      const ev = calls[R.e];
      if (ev.role === 'adj') setCap(CAP.adj);
      const [, name] = TOOL[ev.tool] || ['', ev.tool];
      now.innerHTML = `${sw(ev.role)}<b>${esc(ev.role === 'adj' ? adjShort : MAPWHO[ev.role])}</b><span>${esc(name)}</span><span class="arg">${esc(trunc(toolArg(ev.tool, ev.args), 64))}</span>`;
      now.classList.add('on');
      putCall(R.e, true); mapPaint(J);
      R.e += 1;
      later(R.e < calls.length ? tick : cite, R.e < calls.length ? step : HERO.settle);
    };
    const cite = () => {
      now.classList.remove('on');
      if (!k) { setCap(CAP.end); later(fade, HERO.frame); return; }
      M.citedOn = true; mapPaint(J); mapPulse(J); setCap(CAP.cited);
      later(frame, HERO.cited);
    };
    const frame = () => { if (fig) fig.classList.add('on'); setCap(CAP.end); later(fade, HERO.frame); };
    const fade = () => { card.classList.add('fading'); later(start, HERO.fade); };
    start();
  } catch (e) { fallback(); }
}
function heroGeo(J) {                                    // the whole collection in a short band (whole device pixels)
  const M = J.map, W = M.cv.parentElement.clientWidth || 480, dpr = window.devicePixelRatio || 1;
  const raw = Math.sqrt((W * (W < 520 ? 170 : 230)) / M.n);
  const p = Math.max(2, Math.min(9, dpr >= 2 ? Math.round(raw * 2) / 2 : Math.max(3, Math.floor(raw))));
  const cols = Math.max(1, Math.floor(W / p)), rows = Math.ceil(M.n / cols);
  const o = 16;                                          // drawn margin: the ringed squares' pulses are not cut at the edge
  M.g = { p, cols, s: p >= 7 ? p - 2 : p >= 3 ? p - 1 : p - 0.5, W: cols * p, H: rows * p, dpr, o };
  M.cv.width = Math.round((M.g.W + 2 * o) * dpr); M.cv.height = Math.round((M.g.H + 2 * o) * dpr);
  M.cv.style.width = `${M.g.W + 2 * o}px`; M.cv.style.height = `${M.g.H + 2 * o}px`; M.cv.style.margin = `-${o}px`;
  M.layer = document.createElement('canvas'); M.layer.width = M.cv.width; M.layer.height = M.cv.height;
  mapPaint(J);
}

// ------------------------------------------------------------------ case
// changed words are marked; rewording that touches no facts (no third flag, or false) gets a lighter mark
const marked = (spans, on) => (spans || []).map(([t, ch, fact]) => (ch && on ? `<mark${fact === false ? ' class="minor"' : ''}>${esc(t)}</mark>` : esc(t))).join(' ');
function answersHTML(c, opts = {}) {
  const on = opts.highlight !== false;
  return `<div class="answers">${['A', 'B'].map((s) => `<div class="card answer ${s}" id="ans${s}">
      <div class="head"><span class="letter ${s}">${s}</span><b>Answer ${s}</b><span class="grow"></span><span class="muted small" data-expand="${s}" style="cursor:pointer">expand</span></div>
      <div class="body">${marked(s === 'A' ? c.diff_a : c.diff_b, on)}</div></div>`).join('')}</div>`;
}
function bindAnswers() {
  $$('[data-expand]').forEach((el) => { el.onclick = () => { const card = el.closest('.answer'); card.classList.toggle('open'); el.textContent = card.classList.contains('open') ? 'collapse' : 'expand'; }; });
}
function haystackHTML(c) {
  const h = c.haystack;
  return `<div class="haystack"><span class="tag brand">${esc(domName(c.domain))}</span>${h ? `<span>Search space: ${h.playlists.length} playlist${h.playlists.length > 1 ? 's' : ''} · ${fmtInt(h.videos)} video${h.videos === 1 ? '' : 's'} · ${h.hours >= 1 ? `${h.hours} hours` : `${Math.max(1, Math.round(h.hours * 60))} min`} of footage</span>` : ''}</div>`;
}
function optsHTML(library) {
  const sp = S.health && S.health.spark;
  const spOk = sp && sp.available;
  const sp13Ok = S.health && S.health.spark13 && S.health.spark13.available;
  const o = S.opts;
  return `<div class="opts">
      <div class="opt"><label>Investigators</label><div class="seg" data-k="agents">
        <button data-v="3" class="${o.agents === 3 ? 'on' : ''}">Three <small>recommended</small></button><button data-v="1" class="${o.agents === 1 ? 'on' : ''}">One <small>fast</small></button></div></div>
      <div class="opt"><label>Adjudication</label><div class="seg" data-k="resolve">
        <button data-v="glimmer" class="${o.resolve === 'glimmer' ? 'on' : ''}" title="evidence-only adjudicator on Muse Glimmer, no API cost">Glimmer adjudicator <small>open weights</small></button>
        <button data-v="spark" class="${o.resolve === 'spark' ? 'on' : ''}" ${spOk ? '' : 'disabled'} title="${spOk ? 'Muse Spark Open on Baseten, only on splits: about $0.07 per adjudication, $0.017 per case on average' : 'Baseten key locked or budget reached'}">Spark Open <small>~$0.017/case</small></button>
        <button data-v="spark13" class="${o.resolve === 'spark13' ? 'on' : ''}" ${sp13Ok ? '' : 'disabled'} title="${sp13Ok ? 'Muse Spark 1.3 Contributor on the Meta Model API, only on splits: about $0.004 per adjudication, $0.001 per case on average. Contributor tier: Meta may train on what is sent.' : 'Meta Model API key locked or budget reached'}">Spark 1.3 <small>Meta API ~$0.001/case</small></button>
        <button data-v="spark13all" class="${o.resolve === 'spark13all' ? 'on' : ''}" ${sp13Ok ? '' : 'disabled'} title="${sp13Ok ? 'Muse Spark 1.3 re-checks every verdict, agreed ones too: 82.0% on 880 development runs and 81.6% on the 316 held-out contests (Muse Glimmer alone: 81.0% there), about $0.004 per case' : 'Meta Model API key locked or budget reached'}">Spark 1.3 checks all <small>best · ~$0.004/case</small></button>
        <button data-v="vote" class="${o.resolve === 'vote' ? 'on' : ''}">Majority vote <small>instant</small></button></div></div>
      <div class="opt"><label>Effort</label><div class="seg" data-k="quick">
        <button data-v="0" class="${!o.quick ? 'on' : ''}" title="8 turns per investigator: 75.2% on the development set">Thorough <small>8 turns</small></button>
        <button data-v="1" class="${o.quick ? 'on' : ''}" title="6 turns per investigator with lighter reasoning: about 30% fewer tokens and much faster; 73.2% for the jury on the development set">Quick <small>6 turns, lighter</small></button></div></div>
    </div>
    <div class="small muted" style="margin-top:12px">${library ? 'Library case: recorded investigations replay in seconds.' : 'Live run on Muse Glimmer: about 3 to 6 minutes for three investigators.'}
      ${o.resolve === 'spark' ? ' Spark Open runs only if the investigators split.' : ''}${o.resolve === 'spark13' ? ' Spark 1.3 runs only if the investigators split; on the Contributor tier Meta may train on what is sent.' : ''}${o.resolve === 'spark13all' ? ' Spark 1.3 re-checks every verdict on the investigators\' evidence, agreed ones too; on the Contributor tier Meta may train on what is sent.' : ''}</div>`;
}
function bindOpts(rerender) {
  $$('.seg[data-k]').forEach((seg) => {
    seg.onclick = (e) => {
      const b = e.target.closest('button[data-v]');
      if (!b || b.disabled) return;
      const k = seg.dataset.k;
      S.opts[k] = k === 'agents' ? Number(b.dataset.v) : k === 'quick' ? b.dataset.v === '1' : b.dataset.v;
      rerender();
    };
  });
}
async function casePage(cid) {
  if (!S.health) await health();
  const c = await api(`/api/case/${encodeURIComponent(cid)}`);
  await loadTitles(c.domain);
  if (STATIC) {                                          // the gallery: the recorded investigation of this case, if any
    const { jobs } = await api('/api/jobs');
    const rec = jobs.find((j) => j.case_id === c.id && j.final);
    $('#app').innerHTML = `<div class="crumbs"><a href="#/">Cases</a><span>›</span><span>${esc(domName(c.domain))}</span><span>›</span><span>${esc(c.id)}</span></div>
      ${questionHTML(c)}${haystackHTML(c)}${answersHTML(c)}
      <div class="card runbox"><div class="small muted">${rec ? 'A recorded investigation of this case: three Muse Glimmer agents, the vote, and the adjudicator when they split.'
        : `This case has no recorded investigation in the gallery.${STATIC.live ? ' Run it on the live app.' : ''}`}</div>
        ${rec ? `<a class="btn primary big" href="#/job/${esc(rec.id)}?play=2">${IC.play} Watch the investigation</a>`
          : (STATIC.live ? `<a class="btn big" href="${esc(STATIC.live)}" target="_blank" rel="noopener">Open the live app ↗</a>` : '')}</div>`;
    bindAnswers();
    return;
  }
  const draw = () => {
    $('#app').innerHTML = `<div class="crumbs"><a href="#/">Cases</a><span>›</span><span>${esc(domName(c.domain))}</span><span>›</span><span>${esc(caseNo(c.id))}</span></div>
      ${questionHTML(c)}${disputedHTML(c)}${haystackHTML(c)}
      ${answersHTML(c)}
      <div class="card runbox"><div id="opts">${optsHTML(true)}</div>
        <button class="btn primary big" id="run">${IC.play} Convene the jury</button></div>
      <p class="small muted" style="margin-top:10px">Highlighted words differ between the two answers. The agents see the same question and answers, then search the whole ${esc(domName(c.domain))} collection themselves.</p>`;
    bindAnswers();
    const rebind = () => { $('#opts').innerHTML = optsHTML(true); bindOpts(rebind); };
    bindOpts(rebind);
    $('#run').onclick = async () => {
      $('#run').disabled = true;
      try {
        const j = await api('/api/jobs', { method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ case_id: c.id, agents: S.opts.agents, resolve: S.opts.resolve, quick: S.opts.quick }) });
        location.hash = `#/job/${j.id}`;
      } catch (e) { $('#run').disabled = false; alert(e.message); }
    };
  };
  draw();
}
async function loadTitles(domain) {
  if (!domain || S.titles.__d === domain) return;
  try { S.titles = { ...(await api(`/api/titles/${encodeURIComponent(domain)}`)), __d: domain }; } catch (e) { /* titles are optional */ }
}

// ------------------------------------------------------------------ job (the live board)
const ROLE = { inv0: 'Investigator 1', inv1: 'Investigator 2', inv2: 'Investigator 3' };
const PACE = { start: 200, agent_start: 250, first_look: 900, status: 0, turn: 1100, tool: 450, agent_done: 900, vote: 1600,
  adj_start: 900, evidence: 600, adj_done: 1300, final: 1500, notice: 300 };       // ms between events in a replay at 1x
// model text as shown: Muse Glimmer's tool-call format sometimes leaks into rationales and replies
// ("<|start|>assistant to=zoom<|message|>", "<atem:function_calls>", or a cut "ame="rationale">" at the start)
function cleanText(s) {
  return String(s || '')
    .replace(/<\|[^|>]{0,40}\|>(?:assistant)?(?:\s*to=[\w.]+)?/g, ' ')
    .replace(/<\/?atem:[^>]*>/g, ' ')
    .replace(/<\/?(?:parameter|invoke|function_calls|antml:[a-z_]+)[^>]*>/g, ' ')
    .replace(/^\s*[a-z_]{0,12}="?[a-z_]{0,20}"?>\s*/i, '')
    .replace(/[ \t]{2,}/g, ' ')
    .trim();
}

// the verdict's cited moments as one short clip (server.py /api/jobs/{id}/evidence.mp4; the gallery ships it as a file)
function playClip(jid) {
  const src = STATIC ? `media/${jid}/evidence.mp4` : `/api/jobs/${jid}/evidence.mp4`;
  let d = document.getElementById('clipdlg');
  if (!d) { d = document.createElement('dialog'); d.id = 'clipdlg'; d.className = 'card clipdlg'; document.body.appendChild(d); }
  d.innerHTML = `<div class="row" style="align-items:center;margin-bottom:10px"><b class="grow">The moments the verdict cites</b><a class="btn" href="${src}" download="portia_${jid}_evidence.mp4">Download</a><button class="btn" id="clipx">Close</button></div>
    <video src="${src}" controls autoplay playsinline muted style="width:100%;border-radius:10px;background:#000"></video>
    <div class="small muted" style="margin-top:8px">About six seconds of footage around each moment the deciding text cites, cut from the original videos.</div>`;
  d.querySelector('#clipx').onclick = () => d.close();
  d.querySelector('video').onerror = () => { d.querySelector('video').outerHTML = '<div class="banner err">No clip could be cut for this verdict.</div>'; };
  d.onclose = () => { const v = d.querySelector('video'); if (v) v.pause(); };
  d.showModal();
}

// check one answer: which side is the user's, and what the variant changed
function variantHTML(s) {
  const mine = s.original_side, other = mine === 'A' ? 'B' : 'A';
  return `<div class="card pad variantcard"><b>The submitted answer is ${mine}.</b> To test it against the footage, Muse Glimmer wrote answer ${other}: the same text with ${s.changes.length} detail${s.changes.length > 1 ? 's' : ''} changed.
    <div class="disp" style="margin-top:8px"><span class="k">Changed</span>${s.changes.map(([a, b]) => `<span><b class="da">${esc(mine === 'A' ? a : b)}</b> → <b class="db">${esc(mine === 'A' ? b : a)}</b></span>`).join('<span class="sep">·</span>')}</div></div>`;
}

// a case at a glance: its number and the details the two answers dispute
const domName = (d) => String(d || '').replace(/^Your video: /, 'Uploaded video: ');   // stored names keep their prefix
// the benchmark's questions are long riddles: show Muse Glimmer's one-line version first, the full question on demand
const questionHTML = (c) => (c.gloss
  ? `<h1 class="question">${esc(c.gloss)}</h1><details class="fullq"><summary>Full question <span class="muted">· the line above is shortened by Muse Glimmer</span></summary><p>${esc(c.question)}</p></details>`
  : `<h1 class="question">${esc(c.question)}</h1>`);
const caseNo = (id) => (String(id || '').match(/_(\d+)$/) ? `Case ${String(id).match(/_(\d+)$/)[1]}` : 'New case');
const disputedHTML = (c, n = 2) => (c.disputed && c.disputed.length ? `<div class="disp"><span class="k">Disputed</span>${c.disputed.slice(0, n).map(([a, b]) => `<span><b class="da">${esc(a)}</b> vs <b class="db">${esc(b)}</b></span>`).join('<span class="sep">·</span>')}</div>` : '');

// ------------------------------------------------------------------ trust tiers (plan 016)
// Every verdict path has a measured development accuracy (analysis/trust_tiers.py); it decides whether a verdict can
// be accepted as is, deserves a quick look, or should go to a person with its cited frames.
const TIER = {
  accept: { label: 'Safe to accept', cls: 'ok', icon: svg('<path d="M20 6 9 17l-5-5"/>') },
  spot: { label: 'Spot-check', cls: 'warn', icon: svg('<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>') },
  review: { label: 'Needs review', cls: 'bad', icon: svg('<path d="M4 22V4"/><path d="M4 4h12l-2 4 2 4H4"/>') },
};
async function loadTrust() {
  if (S.trust === undefined) { try { const P = await api('/api/proof'); S.trust = P.trust || null; S.kinds = P.kinds || null; } catch (e) { S.trust = null; } }
  return S.trust;
}
function trustPath(how, forced) {
  const settled = forced != null && forced <= 1;
  return { unanimous: settled ? 'agreed_settled' : 'agreed_turnlimit', glimmer: 'split_glimmer', spark: 'split_spark',
    spark13: 'split_spark13', vote: 'split_vote', single: 'single',
    spark13_confirm: settled ? 's13_confirm_settled' : 's13_confirm_turnlimit', spark13_overturn: 's13_overturn' }[how];
}
function tierOf(pct) {
  const L = (S.trust && S.trust.levels) || { accept: 85, spot: 75 };
  return pct >= L.accept ? 'accept' : pct >= L.spot ? 'spot' : 'review';
}
// kind: what the answers dispute (engine.dispute_kind). Plan 019: on quoted or on-screen text and on positions the
// agents are right only 56-67% of the time even when they agree on their own, so such a verdict is never "safe to accept"
function trustFor(final, quick, custom, kind) {  // final: the final event (how, forced, track); quick: Quick mode; custom: a new question
  if (!S.trust || !final || !final.verdict) return null;
  let r = trustFor0(final, quick);
  if (r && (kind === 'text' || kind === 'position') && r.level === 'accept') r = { ...r, level: 'spot', capped: kind };
  return r && custom ? { ...r, uncal: true } : r;
}
function trustFor0(final, quick) {
  if (!S.trust || !final || !final.verdict) return null;
  const p = S.trust.paths[trustPath(final.how, final.forced)];
  if (quick || !p) {                             // Quick mode: only the coarse track record was measured
    const pct = final.track && final.track.pct;
    return pct == null ? null : { level: tierOf(pct), pct, label: final.track.basis, quick: true };
  }
  return { level: tierOf(p.pct), pct: p.pct, share: p.share, n: p.n, label: p.label };
}
const tierTag = (tr) => (tr ? `<span class="tag tier ${TIER[tr.level].cls}" title="${esc(`${tr.pct}% right on the development set${tr.uncal ? '; calibrated on library questions, a guide for new ones' : ''}`)}">${TIER[tr.level].icon}${tr.uncal ? '≈ ' : ''}${TIER[tr.level].label}</span>` : '');
function weakRange(K) {                         // the measured accuracy of agreed verdicts on text and position disputes
  const rows = ((K || S.kinds) && (K || S.kinds).rows || []).filter((r) => r.kind === 'text' || r.kind === 'position').map((r) => r.local_settled);
  return rows.length ? `${Math.round(Math.min(...rows))}-${Math.round(Math.max(...rows))}%` : 'under 70%';
}
function tierLine(tr) {
  const base = `Verdicts reached this way were right ${tr.pct}% of the time on the development set${tr.share ? ` (${tr.share}% of cases)` : ''}.${tr.uncal ? ' Calibrated on the library\'s two-hop questions: a guide for a new question.' : ''}`;
  if (tr.capped) return `${base} But these answers disagree about ${tr.capped === 'text' ? 'words on screen' : 'where things are'}, which the agents read worst (${weakRange()} right even when they agree on their own), so take a quick look at the cited frames.`;
  return tr.level === 'accept' ? `${base} Portia's most reliable kind of verdict.`
    : tr.level === 'spot' ? `${base} Worth a quick look at the cited frames.`
      : `${base} A person should confirm it; the cited frames below make that a short check.`;
}

async function jobPage(jid, params) {
  await loadTrust();
  const meta = await api(`/api/jobs/${jid}`);
  const play = params && params.get('play') ? Math.max(1, Number(params.get('play')) || 2) : 0;
  const c = meta.case, cfg = meta.config;
  await loadTitles(c.domain);
  const lib = c.library;
  $('#app').innerHTML = `<div class="crumbs"><a href="#/">Cases</a><span>›</span>${lib ? `<a href="#/case/${esc(c.id)}">${esc(caseNo(c.id))}</a>` : '<span>new case</span>'}<span>›</span><span>run ${esc(jid)}</span></div>
    ${questionHTML(c)}${haystackHTML(c)}
    <div id="verdict"></div><div id="truth"></div>
    <div id="variant">${meta.single ? variantHTML(meta.single) : ''}</div>
    <div id="answersbox">${cfg.single && !meta.single ? '<div class="banner info">Muse Glimmer is writing a variant of the answer to test it against…</div>' : answersHTML(c)}</div>
    <div id="replaybar"></div>
    <div class="stage" id="stage">
      <span class="step" data-s="investigate"><i>1</i>Investigate</span><span class="step-sep"></span>
      <span class="step" data-s="vote"><i>2</i>Compare</span><span class="step-sep"></span>
      <span class="step" data-s="adjudicate"><i>3</i>Adjudicate</span><span class="step-sep"></span>
      <span class="step" data-s="verdict"><i>4</i>Verdict</span>
      <span class="clock" id="clock">0:00</span></div>
    <div id="banners"></div><div id="smap"></div>
    <div class="board${cfg.agents === 1 ? ' one' : ''}" id="board"></div>
    <div id="vote"></div><div id="adj"></div>`;
  bindAnswers();
  const J = { t0: null, adj: null, c, cfg, lib, jid, next: 0, shots: [], rat: {}, play, single: meta.single || null, meta };
  mapInit(J);
  S.clock = setInterval(() => { if (J.t0 && !J.ended) $('#clock').textContent = mmss(Date.now() / 1000 - J.t0); }, 500);
  if (play) { replay(J); setTimeout(() => $('#replaybar').scrollIntoView({ behavior: 'smooth', block: 'start' }), 400); return; }
  if (STATIC) {
    const { events } = await api(`/api/jobs/${jid}/events.json`);
    events.forEach((ev) => handle(J, ev));
    $('#replaybar').innerHTML = `<div class="replaybar"><span>Recorded investigation.</span><a class="btn" href="#/job/${esc(jid)}?play=2">${IC.play} Replay it</a></div>`;
    return;
  }
  if (meta.done) {
    $('#replaybar').innerHTML = `<div class="replaybar"><span>Finished run.</span><a class="btn" href="#/job/${esc(jid)}?play=2">${IC.play} Replay the investigation</a></div>`;
  }
  S.stream = new EventSource(`/api/jobs/${jid}/events`);
  S.stream.onmessage = (m) => { try { handle(J, JSON.parse(m.data)); } catch (e) { console.error(e); } };
  S.stream.onerror = () => { if (J.ended && S.stream) { S.stream.close(); S.stream = null; } };
}
async function replay(J) {
  const { events } = await api(`/api/jobs/${J.jid}/events.json`);
  const R = { i: 0, speed: J.play };
  const bar = () => {
    $('#replaybar').innerHTML = `<div class="replaybar"><span class="live">Replaying a recorded investigation</span>
      <div class="seg">${[1, 2, 4].map((s) => `<button data-sp="${s}" class="${R.speed === s ? 'on' : ''}">${s}×</button>`).join('')}</div>
      <button class="btn primary" id="skip">Skip to the verdict</button><a class="btn" href="#/job/${esc(J.jid)}">Exit replay</a></div>`;
    $$('#replaybar [data-sp]').forEach((b) => { b.onclick = () => { R.speed = Number(b.dataset.sp); bar(); }; });
    $('#skip').onclick = () => { clearTimeout(S.replay); while (R.i < events.length) handle(J, events[R.i++]); };
  };
  bar();
  const tick = () => {
    if (R.i >= events.length) return;
    const ev = events[R.i++];
    handle(J, ev);
    S.replay = setTimeout(tick, (PACE[ev.type] ?? 150) / R.speed);
  };
  tick();
}
function stage(name, state) {
  const el = $(`#stage .step[data-s="${name}"]`);
  if (!el) return;
  el.classList.remove('on', 'done');
  if (state) el.classList.add(state);
}
function agentCol(role, label, sub, cls) {
  return `<div class="card agent" id="col-${role}"><div class="agent-head"><div class="avatar ${cls || `r-${role}`}">${esc(label.slice(-1))}</div>
      <div class="who"><b>${esc(label)}</b><span>${esc(sub)}</span></div><div class="state" id="st-${role}"><span class="muted">waiting</span></div></div>
    <div class="progress"><i id="pg-${role}"></i></div><div id="fl-${role}"></div><div class="turns" id="tu-${role}"><div class="turn"><div class="skeleton"></div><div class="skeleton" style="width:70%"></div></div></div>
    <div id="ft-${role}"></div></div>`;
}
function handle(J, ev) {
  if (ev.i < J.next) return;                        // already shown (a reconnect replays from the last id)
  J.next = ev.i + 1;
  const r = ev.role;
  switch (ev.type) {
    case 'start':
      J.t0 = J.play ? Date.now() / 1000 : ev.t;
      J.turns = (ev.plan[0] && ev.plan[0].turns) || 8;
      J.models = Object.fromEntries(ev.plan.map((p) => [p.role, p.model || 'Muse Glimmer 30B']));
      $('#board').innerHTML = ev.plan.map((p) => agentCol(p.role, ROLE[p.role], `${J.models[p.role]} · seed ${p.seed}${J.turns !== 8 ? ` · ${J.turns} turns` : ''}`)).join('');
      stage('investigate', 'on');
      break;
    case 'queued':
      $('#banners').innerHTML = '<div class="banner info">Both Muse Glimmer servers are busy; this run starts as soon as one frees up.</div>';
      break;
    case 'agent_start':
      $('#banners').innerHTML = '';
      setState(r, '<span class="live">starting</span>');
      break;
    case 'first_look':
      $(`#fl-${r}`).innerHTML = `<details class="firstlook" data-gallery><summary>${IC.sheet.replace('<svg', '<svg width="14" height="14"')} First look: ${ev.images.length} overview sheets of the most relevant footage</summary>${shotsHTML(ev.images, `${ROLE[r] || r} · first look`)}</details>`;
      break;
    case 'variant':
      J.single = ev; J.c = ev.case;
      $('#variant').innerHTML = variantHTML(ev);
      $('#answersbox').innerHTML = answersHTML(ev.case);
      bindAnswers();
      $('#banners').innerHTML = '';
      break;
    case 'status':
      if (!r) { $('#banners').innerHTML = `<div class="banner info">${esc(ev.message || '')}</div>`; break; }
      setState(r, `<span class="live">${r === 'adj' ? 'checking' : 'thinking'}</span><br>turn ${ev.step + 1}`);
      if (ROLE[r]) $(`#pg-${r}`).style.width = `${Math.min(100, ((ev.step + 1) / ((J.turns || 8) + 1)) * 100)}%`;
      break;
    case 'turn': addTurn(J, r, ev); break;
    case 'tool': addTool(J, r, ev); break;
    case 'agent_done': agentDone(J, r, ev); break;
    case 'vote': showVote(J, ev); break;
    case 'adj_start': buildAdj(J, ev); break;
    case 'evidence': addEvidence(J, ev); break;
    case 'adj_done': adjDone(J, ev); break;
    case 'notice': $('#banners').innerHTML = `<div class="banner info">${esc(ev.message)}</div>`; break;
    case 'final': showVerdict(J, ev); break;
    case 'error': $('#banners').innerHTML = `<div class="banner err"><b>The run failed.</b> ${esc(ev.message)}</div>`; break;
    case 'end':
      J.ended = true;
      if (S.stream) { S.stream.close(); S.stream = null; }
      if (J.t0 && !J.play) $('#clock').textContent = mmss((J.final ? J.final.t : ev.t) - J.t0);
      if (J.play) { const rb = $('#replaybar .live'); if (rb) rb.textContent = 'Replay finished'; }
      break;
    default: break;
  }
}
function setState(role, html) { const el = $(`#st-${role}`); if (el) el.innerHTML = html; }
function turnsBox(role) {
  const box = $(`#tu-${role}`);
  if (box && box.querySelector('.skeleton')) box.innerHTML = '';
  return box;
}
function addTurn(J, role, ev) {
  if (ev.replay) J.anyReplay = true;                    // served from the response cache
  if (role === 'adj') {                                // the adjudicator's own tokens: its API cost when a record lacks it
    const a = (J.adjTok = J.adjTok || { in: 0, out: 0, live: false });
    a.in += (ev.tokens && ev.tokens.in) || 0; a.out += (ev.tokens && ev.tokens.out) || 0; if (!ev.replay) a.live = true;
  }
  const box = turnsBox(role);
  if (!box) return;
  const el = document.createElement('div');
  el.className = 'turn';
  el.dataset.gallery = '';
  const calls = (ev.calls || []).map((c) => {
    const [ic, name] = TOOL[c.name] || ['search', c.name];
    if (c.name === 'answer') {
      const v = String((c.args || {}).verdict || '').toUpperCase().slice(0, 1);
      return `<div class="call"><div class="call-head">${IC.answer}<span class="what">Answers</span>${v ? `<span class="letter ${v}" style="width:20px;height:20px;font-size:11px">${v}</span>` : ''}</div></div>`;
    }
    return `<div class="call" data-name="${esc(c.name)}"><div class="call-head">${IC[ic]}<span class="what">${esc(name)}</span><span class="arg" title="${esc(JSON.stringify(c.args))}">${esc(toolArg(c.name, c.args))}</span><span class="toggle">result</span></div><div class="out muted">running…</div></div>`;
  }).join('');
  const think = cleanText(ev.reasoning).replace(/^#+\s*/gm, '').trim();          // markdown headings read as noise in the excerpt
  const text = cleanText(ev.content);
  const model = role === 'adj' ? ({ spark: 'Muse Spark Open', spark13: 'Muse Spark 1.3' }[J.adj && J.adj.model] || 'Muse Glimmer 30B')
    : (J.models && J.models[role]) || 'Muse Glimmer 30B';            // every model call names its model
  el.innerHTML = `<div class="turn-head"><b>Turn ${ev.step + 1}</b><span class="mdl">${esc(model)}</span><span>${ev.latency}s</span><span>${shortTok(ev.tokens && ev.tokens.in)} in · ${shortTok(ev.tokens && ev.tokens.out)} out</span>${ev.replay && !J.play ? '<span class="replay">replayed</span>' : ''}</div>
    ${think ? `<div class="think" title="click to read the full reasoning">${esc(think)}</div>` : ''}
    ${text && !calls ? `<div class="think open" style="font-style:normal">${esc(text)}</div>` : ''}
    ${calls ? `<div class="calls">${calls}</div>` : ''}`;
  box.appendChild(el);
  const th = el.querySelector('.think');
  if (th) th.onclick = () => th.classList.toggle('open');
  el.querySelectorAll('.call .toggle').forEach((t) => { t.onclick = () => t.closest('.call').classList.toggle('open'); });
}
const parseT = (x) => { if (x == null || x === '') return null; if (typeof x === 'number') return x;
  const p = String(x).trim().split(':').map(Number); return p.some(isNaN) ? null : p.reduce((a, v) => a * 60 + v, 0); };
function shotMoment(tool, a) {                       // (video, t0, t1) a tool image shows, or null
  a = a || {};
  const vid = String(a.video || a.handle || '').split('@')[0];
  if (!/^[A-Za-z0-9_-]{11}$/.test(vid)) return null;
  if (tool === 'view_frames') { const s = Number(String(a.handle).split('@')[1]); return isNaN(s) ? null : [vid, s, s + 30]; }
  if (tool === 'contact_sheet') { const s = parseT(a.start), e = parseT(a.end); return s == null ? null : [vid, s, e == null ? s + 600 : e]; }
  const t = parseT(a.t);
  return t == null ? null : [vid, t, t];
}
function addTool(J, role, ev) {
  mapAdd(J, role, ev);
  const mo = shotMoment(ev.tool, ev.args);
  if (mo) (ev.images || []).forEach((im) => J.shots.push({ vid: mo[0], t0: mo[1], t1: mo[2], src: im.src, tool: ev.tool, label: im.label }));
  if (role === 'evidence') {
    const grp = J.adj && J.adj.cur;
    if (grp) grp.insertAdjacentHTML('beforeend', shotsHTML(ev.images, `${grp.dataset.cap} · ${TOOL[ev.tool] ? TOOL[ev.tool][1] : ev.tool}`, true));
    return;
  }
  const box = $(`#tu-${role}`);
  if (!box) return;
  const turn = box.lastElementChild;
  let call = turn && [...turn.querySelectorAll('.call[data-name]')].find((x) => x.dataset.name === ev.tool && !x.dataset.done);
  if (!call && turn) {
    const [ic, name] = TOOL[ev.tool] || ['search', ev.tool];
    turn.insertAdjacentHTML('beforeend', `<div class="calls"><div class="call" data-name="${esc(ev.tool)}"><div class="call-head">${IC[ic]}<span class="what">${esc(name)}</span><span class="arg">${esc(toolArg(ev.tool, ev.args))}</span><span class="toggle">result</span></div><div class="out"></div></div></div>`);
    call = turn.querySelector('.call:last-child');
    call.querySelector('.toggle').onclick = () => call.classList.toggle('open');
  }
  if (!call) return;
  call.dataset.done = '1';
  const out = call.querySelector('.out');
  out.classList.remove('muted');
  out.textContent = ev.text || '(no text)';
  if ((ev.images || []).length) call.insertAdjacentHTML('beforeend', shotsHTML(ev.images, `${ROLE[role] || 'Adjudicator'} · ${TOOL[ev.tool] ? TOOL[ev.tool][1] : ev.tool} ${toolArg(ev.tool, ev.args)}`));
}
function agentDone(J, role, ev) {
  const v = ev.verdict;
  J.rat[role] = { v, text: cleanText(ev.rationale) };
  (J.agentHow = J.agentHow || {})[role] = ev.how;
  setState(role, v ? `<span class="tag" style="gap:6px">says <span class="letter ${v}" style="width:18px;height:18px;font-size:11px">${v}</span></span>` : '<span class="tag bad">no verdict</span>');
  const pg = $(`#pg-${role}`);
  if (pg) { pg.style.width = '100%'; pg.style.background = v === 'A' ? 'var(--a)' : v === 'B' ? 'var(--b)' : 'var(--muted)'; }
  const how = { tool: 'answered', forced: 'answered at the turn limit', text: 'answered in text', error: 'failed' }[ev.how] || ev.how || '';
  const ft = $(`#ft-${role}`);
  if (ft) {
    ft.innerHTML = `<div class="agent-foot"><div class="says">${v ? `<span class="letter ${v}">${v}</span> Answer ${v} is better supported` : 'No verdict'}</div>
      <div class="small muted" style="margin-top:4px">${esc(how)} · ${ev.steps} turns · ${ev.images ?? 0} images · ${mmss(ev.wall)}</div>
      ${ev.rationale ? `<div class="why" title="click to expand">${esc(cleanText(ev.rationale))}</div>` : ''}</div>`;
    const w = ft.querySelector('.why');
    if (w) w.onclick = () => w.classList.toggle('open');
  }
  const box = $(`#tu-${role}`);
  if (box && box.querySelector('.skeleton')) box.innerHTML = '';
}
function showVote(J, ev) {
  stage('investigate', 'done');
  stage('vote', 'done');
  if (J.cfg.agents === 1) { stage('adjudicate'); return; }
  const vs = ev.verdicts;
  const ballots = vs.map((v, i) => `<div class="ballot"><span class="letter ${v || 'none'}" style="width:34px;height:34px;font-size:16px;border-radius:10px">${v || '–'}</span>#${i + 1}</div>`).join('');
  const checkAll = J.cfg.resolve === 'spark13all';
  const msg = !ev.contested ? (checkAll ? `<b>All three agree: answer ${esc(ev.vote)}.</b> Muse Spark 1.3 now double-checks the agreed verdict on their evidence.`
      : `<b>All three agree: answer ${esc(ev.vote)}.</b> No adjudication needed.`)
    : `<b>Split ${vs.filter((v) => v === ev.vote).length}-${vs.filter((v) => v && v !== ev.vote).length}.</b> The adjudicator now checks the disputed details on the investigators' own evidence.`;
  $('#vote').innerHTML = `<div class="card vote"><div class="ballots">${ballots}</div><div class="msg grow">${msg}</div></div>`;
  if (ev.contested || checkAll) stage('adjudicate', 'on');
}
function buildAdj(J, ev) {
  const spark = ev.model === 'spark' || ev.model === 'spark13';
  const who = { spark: 'Muse Spark Open · Baseten', spark13: 'Muse Spark 1.3 · Meta Model API' }[ev.model] || 'Muse Glimmer · open weights';
  $('#adj').innerHTML = `<div class="card agent adj"><div class="agent-head"><div class="avatar ${spark ? 'spark' : 'adj'}">J</div>
      <div class="who"><b>Adjudicator</b><span>${who} · sees the evidence, not the votes</span></div>
      <div class="state" id="st-adj"><span class="live">preparing</span></div></div>
    <div class="grid"><div class="evidence" id="evidence"><div class="h3" style="margin-bottom:10px">Evidence it was shown</div></div>
      <div><div class="turns" id="tu-adj"><div class="turn"><div class="skeleton"></div><div class="skeleton" style="width:60%"></div></div></div><div id="ft-adj"></div></div></div></div>`;
  J.adj = { model: ev.model, cur: null };
}
function addEvidence(J, ev) {
  const box = $('#evidence');
  if (!box) return;
  const cap = `Report ${ev.report + 1}`;
  box.insertAdjacentHTML('beforeend', `<div class="rep" data-gallery data-cap="${esc(cap)}"><div class="rep-head"><b style="color:var(--ink)">${esc(cap)}</b><span>${(ev.looks || []).length} look(s) from ${esc(ROLE[ev.from] || ev.from)}; its verdict is hidden</span></div></div>`);
  J.adj.cur = box.lastElementChild;
}
function adjDone(J, ev) {
  J.rat.adj = { v: ev.verdict, text: cleanText(ev.rationale) };
  stage('adjudicate', 'done');
  const v = ev.verdict;
  setState('adj', v ? `rules <span class="letter ${v}" style="width:18px;height:18px;font-size:11px">${v}</span>` : '<span class="tag bad">no ruling</span>');
  $('#ft-adj').innerHTML = `<div class="agent-foot"><div class="says">${v ? `<span class="letter ${v}">${v}</span> Ruling: answer ${v}` : 'No ruling'}</div>
    <div class="small muted" style="margin-top:4px">${ev.steps} turns · ${mmss(ev.wall)}</div>${ev.rationale ? `<div class="why open">${esc(cleanText(ev.rationale))}</div>` : ''}</div>`;
  const box = $('#tu-adj');
  if (box && box.querySelector('.skeleton')) box.innerHTML = '<div class="pad small muted">No extra looks needed.</div>';
}
function showVerdict(J, ev) {
  J.final = ev;
  ['investigate', 'vote'].forEach((s) => stage(s, 'done'));
  if (String(ev.how).startsWith('spark13_')) stage('adjudicate', 'done');
  else if (!ev.contested) stage('adjudicate');
  stage('verdict', 'done');
  const v = ev.verdict;
  const how = { single: 'One investigator (fast mode) decided.', unanimous: 'All three investigators agreed.',
    vote: 'The investigators split; the majority decided.', glimmer: 'The investigators split; the Muse Glimmer adjudicator checked the disputed details and ruled.',
    spark: 'The investigators split; Muse Spark Open checked the disputed details and ruled.',
    spark13: 'The investigators split; Muse Spark 1.3 (Meta Model API) checked the disputed details and ruled.',
    spark13_confirm: 'All three investigators agreed, and Muse Spark 1.3 (Meta Model API) confirmed it on their evidence.',
    spark13_overturn: 'All three investigators agreed, but Muse Spark 1.3 (Meta Model API) re-checked their evidence and overturned them.' }[ev.how] || '';
  const forced = ev.forced != null ? ev.forced : Object.values(J.agentHow || {}).filter((h) => h === 'forced').length;
  const tr = trustFor({ ...ev, forced }, J.cfg.quick, !J.lib, J.c && J.c.kind);
  const tpct = tr && !tr.quick ? tr.pct : ev.track.pct;
  const tbasis = tr && !tr.quick ? `${tr.label} (${tr.n} dev cases)` : ev.track.basis;
  const u = ev.usage || {};
  const tokens = (u.glimmer_in || 0) + (u.glimmer_out || 0);
  const sparkName = String(ev.how).startsWith('spark13') ? 'Spark 1.3' : 'Spark Open';
  const rate = String(ev.how).startsWith('spark13') ? [0.10e-6, 0.20e-6] : [1.25e-6, 4.25e-6];   // USD per input, output token
  const est = J.adjTok && J.adjTok.live ? J.adjTok.in * rate[0] + J.adjTok.out * rate[1] : 0;     // records without spark_usd
  const cost = u.spark_usd > 0 ? `$${u.spark_usd.toFixed(4)} (${sparkName})` : est > 0 ? `about $${est.toFixed(4)} (${sparkName})`
    : String(ev.how).startsWith('spark') ? `$0 (${sparkName} replayed from cache)` : '$0 · Muse Glimmer, no API cost';
  const runKind = J.play ? 'recorded, replayed' : J.anyReplay ? 'replayed from cache (live: 3 to 6 min)' : 'live';
  const cited = citedShots(J, ev);
  mapCite(J, cited);
  $('#verdict').innerHTML = `<div class="card verdict"><span class="letter lg ${v || 'none'}">${v || '?'}</span>
      <div><div class="k">Verdict</div><h2>${ev.single ? (ev.single.supported ? 'The submitted answer held up' : 'The submitted answer did not hold up') : v ? `Answer ${v} is better supported by the video` : 'No verdict'}</h2>
        ${ev.single ? `<div class="disp" style="margin:6px 0 2px">${ev.single.changes.map(([a, b]) => { const mine = ev.single.original_side === 'A' ? a : b; return `<span>${ev.single.supported ? '✓' : '✗'} <b>${esc(mine)}</b></span>`; }).join('<span class="sep">·</span>')}</div>
          <div class="small muted">${ev.single.supported ? 'On these details the footage fits the submitted answer better than the changed copy. Portia tests the details it changed, not every claim in the answer.' : 'On at least one of these details the footage fits the changed copy better than the submitted answer: check the cited frames.'}</div>` : ''}
        <div class="how">${esc(how)}</div>
        ${tr ? `<div class="trust ${TIER[tr.level].cls}"><span class="ticon">${TIER[tr.level].icon}</span><div><b>${TIER[tr.level].label}</b><span>${esc(tierLine(tr))}</span></div></div>` : ''}
        <div class="meter"><div class="bar"><i style="width:${tpct || 0}%"></i></div><div class="cap"><span>Track record: <b style="color:var(--ink)">${tpct == null ? 'being measured' : `${tpct}%`}</b>${tpct == null ? '' : ' right'}</span><span>${esc(tbasis)}, development set</span></div></div></div>
      <div class="facts"><span>Time</span><b>${mmss(ev.wall)}</b><span>Model tokens</span><b>${shortTok(tokens)}</b><span>API cost</span><b>${esc(cost)}</b><span>Run</span><b>${runKind}</b>
        ${J.lib ? '<span></span><b><button class="btn" id="reveal" style="padding:7px 12px">Reveal the answer key</button></b>' : ''}
        <span></span><b><button class="btn noprint" id="report" style="padding:7px 12px">Download report (PDF)</button></b></div>
      ${cited.length ? `<div class="cited" data-gallery><div class="row" style="align-items:center;margin-bottom:10px"><div class="k grow" style="margin:0">Evidence the verdict cites</div>${!STATIC || (J.meta && J.meta.clip) ? `<button class="btn" id="clipbtn">${IC.play} Watch the moments</button>` : ''}</div>${shotsHTML(cited.map((s) => ({ src: s.src, label: s.cap })), 'Cited evidence', true)}</div>` : ''}</div>`;
  if (v) { const card = $(`#ans${v}`); if (card) card.classList.add('won'); }
  if (J.play) $('#verdict').scrollIntoView({ behavior: 'smooth', block: 'start' });
  const rb = $('#reveal');
  if (rb) rb.onclick = () => reveal(J, v);
  if ($('#clipbtn')) $('#clipbtn').onclick = () => playClip(J.jid);
  $('#report').onclick = () => {                       // the browser's print dialog: "Save as PDF" makes the report
    document.title = `Portia report: ${J.c.id || 'case'} (run ${J.jid})`;
    window.print();
    document.title = 'Portia · every verdict turns on a detail';
  };
}
function citedShots(J, ev) {
  // the deciding text: the adjudicator's ruling on a split, else the rationales of the agents on the winning side
  const winners = Object.entries(J.rat).filter(([k, r]) => k !== 'adj' && r.v === ev.verdict).map(([, r]) => r.text);
  const adjudicated = ['glimmer', 'spark', 'spark13', 'spark13_confirm', 'spark13_overturn'].includes(ev.how);
  const texts = adjudicated ? [J.rat.adj && J.rat.adj.text, ...winners] : winners;   // the ruling first, then the winning agents
  const known = new Set(J.shots.map((s) => s.vid));
  // video@time, "video at 20:33", "video around 20:33-20:41", "video from 1:02" (only videos the agents looked at count)
  const rx = /([A-Za-z0-9_-]{11})(?:@|[\s,]+(?:(?:at|around|near|from|between|about|to)\s+){0,2})(\d{1,2}:\d{2}(?::\d{2})?|\d{1,5}(?:\.\d+)?)/g;
  const out = [], seen = new Set();
  for (const text of texts.filter(Boolean)) {
    for (const m of text.matchAll(rx)) {
      const vid = m[1], t = parseT(m[2]);
      if (!known.has(vid) || t == null) continue;
      const near = J.shots.filter((s) => s.vid === vid && t >= s.t0 - 25 && t <= s.t1 + 25)
        .sort((a, b) => (['zoom', 'burst'].includes(b.tool) - ['zoom', 'burst'].includes(a.tool)) || Math.abs(a.t0 - t) - Math.abs(b.t0 - t));
      const s = near.find((x) => !seen.has(x.src) && !seen.has(`${x.vid}@${Math.round(x.t0 / 3)}`));
      if (!s) continue;
      seen.add(s.src);
      seen.add(`${s.vid}@${Math.round(s.t0 / 3)}`);                 // one frame per moment (3-second buckets)
      const title = S.titles[vid] ? S.titles[vid].slice(0, 42) + (S.titles[vid].length > 42 ? '…' : '') : vid;
      out.push({ ...s, at: t, cap: `${mmss(t)} · ${title}` });
      if (out.length >= 4) return out;
    }
  }
  return out;
}

// ------------------------------------------------------------------ search map (plan 017)
// The whole searchable collection as squares of 30 seconds, its videos end to end in playlist order. Every look an
// agent takes lands on the squares it covers, in that agent's colour; the moments the verdict cites ring in ink, and a
// close-up shows the deciding video's own timeline. Live, in replays and in the static gallery.
const LOOK = { search: [1, 'came up in a search'], search_video: [1, 'came up in a search of the video'],
  grep_transcripts: [2, 'matched a transcript search'], read_transcript: [2, 'read the transcript'], view_frames: [3, 'viewed frames'],
  contact_sheet: [3, 'contact-sheet frame'], zoom: [3, 'zoomed in'], burst: [3, 'burst of frames'] };
const MAPWHO = { inv0: 'Investigator 1', inv1: 'Investigator 2', inv2: 'Investigator 3', adj: 'Adjudicator' };
const isVid = (v) => /^[A-Za-z0-9_-]{11}$/.test(String(v || ''));
const cssVar = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const roleVar = (r) => `--${r === 'adj' ? 'invadj' : r}`;
const trunc = (s, n) => (String(s).length > n ? `${String(s).slice(0, n - 1)}…` : String(s));
function looksOf(ev) {                                   // [video, seconds] pairs that one tool call touched
  const a = ev.args || {}, out = [];
  const handle = (h) => { const [v, s] = String(h || '').split('@'); if (isVid(v) && s && !isNaN(Number(s))) out.push([v, Number(s)]); };
  if (['search', 'search_video', 'grep_transcripts'].includes(ev.tool)) {
    for (const m of String(ev.text || '').matchAll(/^- ([A-Za-z0-9_-]{11})@(\d+)/gm)) out.push([m[1], Number(m[2])]);
  } else if (ev.tool === 'read_transcript') (a.handles || []).forEach(handle);
  else if (ev.tool === 'view_frames') handle(a.handle);
  else if (ev.tool === 'contact_sheet') {                // the sheet's frames, spread over its range
    const s = parseT(a.start), e = parseT(a.end), n = Math.max(1, Math.min(48, Number(a.n) || 12));
    if (isVid(a.video) && s != null) { const e2 = e == null || e <= s ? s + 600 : e; for (let i = 0; i < n; i++) out.push([a.video, s + ((i + 0.5) * (e2 - s)) / n]); }
  } else if (ev.tool === 'zoom' || ev.tool === 'burst') { const t = parseT(a.t); if (isVid(a.video) && t != null) out.push([a.video, t]); }
  return out;
}
const cellOf = (M, vid, t) => { const o = M.off[vid]; return o ? o[0] + Math.min(o[1] - 1, Math.max(0, Math.floor(t / M.f.seg))) : -1; };
function mapPut(M, L) {
  const i = cellOf(M, L.vid, L.t);
  if (i >= 0) { let c = M.cells.get(i); if (!c) M.cells.set(i, (c = { looks: [] })); c.looks.push(L); }
  return i;
}
function mapInit(J) {
  const M = (J.map = { looks: [], done: 0, cells: new Map(), cited: [], citedCells: [], hide: new Set(), pings: [], ev: 0, hover: -1 });
  const el = $('#smap');
  api(`/api/footage/${encodeURIComponent(J.c.domain)}`).then((f) => {
    if (!el.isConnected) return;
    M.f = f; M.off = {}; M.starts = [];
    let n = 0;
    f.videos.forEach((v, k) => { const c = Math.max(1, Math.ceil(v.dur / f.seg)); M.off[v.id] = [n, c, k]; M.starts.push(n); n += c; });
    M.n = n;
    const span = f.hours >= 1 ? `${f.hours} hours` : `${Math.max(1, Math.round(f.hours * 60))} minutes`;
    el.innerHTML = `<div class="card smap"><div class="smap-head"><div class="grow"><div class="h3">Where the agents looked</div>
        <div class="smap-sub">Each square is ${f.seg} seconds of the footage they could search: ${fmtInt(f.videos.length)} video${f.videos.length === 1 ? '' : 's'}, ${span}, end to end.</div></div>
        <button class="btn noprint" id="smap-play">${IC.play} Replay the search</button></div>
      <div class="smap-legend" id="smap-legend"></div>
      <div class="smap-wrap"><canvas id="smap-cv" role="img" aria-label="Map of the searchable footage: each square is ${f.seg} seconds; coloured squares are where the agents looked; ringed squares are the moments the verdict cites."></canvas><div class="smap-tip" id="smap-tip" hidden></div></div>
      <div class="smap-now" id="smap-now" aria-live="polite"></div><div class="smap-stats" id="smap-stats"></div><div id="smap-zoom"></div></div>`;
    M.cv = $('#smap-cv'); M.tip = $('#smap-tip');
    M.cv.onmousemove = (e) => mapHover(J, e);
    M.cv.onmouseleave = () => { M.tip.hidden = true; M.hover = -1; mapFrame(J); };
    M.cv.onclick = (e) => { mapHover(J, e); if (M.citedCells.includes(M.hover) && (!STATIC || (J.meta && J.meta.clip))) playClip(J.jid); };
    $('#smap-play').onclick = () => mapReplay(J);
    S.mapResize = () => { if (M.cv.isConnected) requestAnimationFrame(() => mapGeo(J)); };
    mapGeo(J);
    for (; M.done < M.looks.length; M.done++) mapPut(M, M.looks[M.done]);
    mapLegend(J);
    if (M.cited.length) mapShowCited(J); else { mapPaint(J); mapStats(J); }
  }).catch(() => { el.innerHTML = ''; });
}
function mapGeo(J) {                                     // square size and columns for the card's width
  const M = J.map, W = M.cv.parentElement.clientWidth || 600;
  const p = Math.max(3, Math.min(18, Math.floor(Math.sqrt((W * (W < 600 ? 330 : 250)) / M.n))));
  const cols = Math.max(1, Math.floor(W / p)), rows = Math.ceil(M.n / cols), dpr = window.devicePixelRatio || 1;
  M.g = { p, cols, s: p - (p >= 7 ? 2 : 1), W: cols * p, H: rows * p, dpr };
  M.cv.width = M.g.W * dpr; M.cv.height = M.g.H * dpr;
  M.cv.style.width = `${M.g.W}px`; M.cv.style.height = `${M.g.H}px`;
  M.layer = document.createElement('canvas'); M.layer.width = M.cv.width; M.layer.height = M.cv.height;
  mapPaint(J);
}
function topLook(c, hide) {                              // the strongest look at a square among the shown agents (latest wins a tie)
  let best = null;
  for (const L of c.looks) if (!hide.has(L.role) && (!best || L.kind >= best.kind)) best = L;
  return best;
}
function mapPaint(J) {                                   // the still layer: footage, looks, cited rings
  const M = J.map, g = M.g;
  if (!g) return;
  const cx = M.layer.getContext('2d'), xy = (i) => [(i % g.cols) * g.p, Math.floor(i / g.cols) * g.p], o = g.o || 0;
  cx.setTransform(g.dpr, 0, 0, g.dpr, o * g.dpr, o * g.dpr);    // o: a margin pulses can grow into (the hero's map)
  cx.clearRect(-o, -o, g.W + 2 * o, g.H + 2 * o);
  const tone = [cssVar('--cell-a'), cssVar('--cell-b')], hi = cssVar('--cell-hi');
  const deciding = new Set(M.citedOn ? M.cited.map((q) => q.vid) : []);
  M.f.videos.forEach((v, k) => {
    const [o, c] = M.off[v.id];
    cx.fillStyle = deciding.has(v.id) ? hi : tone[k % 2];
    for (let i = o; i < o + c; i++) { const [x, y] = xy(i); cx.fillRect(x, y, g.s, g.s); }
  });
  const col = Object.fromEntries(Object.keys(MAPWHO).map((r) => [r, cssVar(roleVar(r))]));
  const framed = [];                                   // squares an agent looked at frame by frame, for the demo recorder
  for (const [i, c] of M.cells) {
    const L = topLook(c, M.hide);
    if (!L) continue;
    const [x, y] = xy(i);
    if (L.kind === 3 && framed.length < 12) framed.push(`${x + g.s / 2},${y + g.s / 2}`);
    cx.globalAlpha = [0, 0.4, 0.68, 1][L.kind];
    cx.fillStyle = col[L.role] || col.adj;
    cx.fillRect(x, y, g.s, g.s);
  }
  cx.globalAlpha = 1;
  M.cv.dataset.looks = framed.join(' ');
  if (M.citedOn) {                                      // one ring around each run of cited squares side by side in a row
    cx.strokeStyle = cssVar('--ink'); cx.lineWidth = 2;
    const runs = [];
    [...M.citedCells].sort((a, b) => a - b).forEach((i) => {
      const r = runs[runs.length - 1];
      if (r && i === r[1] + 1 && i % g.cols !== 0) r[1] = i; else runs.push([i, i]);
    });
    runs.forEach(([a, b]) => { const [x, y] = xy(a); cx.strokeRect(x - 2.5, y - 2.5, (b - a) * g.p + g.s + 5, g.s + 5); });
  }
  mapFrame(J);
}
function ping(J, i, color, o) {                          // a ring that grows from a square and fades
  const M = J.map;
  if (M.pings.length > 60) return;
  M.pings.push({ i, color, r: o.r || 12, dur: o.dur || 800, w: o.w || 1.5, t0: performance.now() + (o.delay || 0) });
  if (!M.raf) M.raf = requestAnimationFrame(() => mapFrame(J));
}
function mapFrame(J) {
  const M = J.map, g = M.g;
  M.raf = 0;
  if (!g || !M.cv.isConnected) { M.pings = []; return; }
  const cx = M.cv.getContext('2d'), now = performance.now();
  cx.setTransform(1, 0, 0, 1, 0, 0);
  cx.clearRect(0, 0, M.cv.width, M.cv.height);
  cx.drawImage(M.layer, 0, 0);
  cx.setTransform(g.dpr, 0, 0, g.dpr, (g.o || 0) * g.dpr, (g.o || 0) * g.dpr);
  const mid = (i) => [(i % g.cols) * g.p + g.s / 2, Math.floor(i / g.cols) * g.p + g.s / 2];
  if (M.hover >= 0) { const [x, y] = mid(M.hover); cx.strokeStyle = cssVar('--ink-2'); cx.lineWidth = 1; cx.strokeRect(x - g.s / 2 - 1.5, y - g.s / 2 - 1.5, g.s + 3, g.s + 3); }
  M.pings = M.pings.filter((p) => now - p.t0 < p.dur);
  for (const p of M.pings) {
    if (now < p.t0) continue;
    const k = (now - p.t0) / p.dur, [x, y] = mid(p.i);
    cx.globalAlpha = 1 - k; cx.strokeStyle = p.color; cx.lineWidth = p.w;
    cx.beginPath(); cx.arc(x, y, g.s / 2 + 1 + k * p.r, 0, Math.PI * 2); cx.stroke();
  }
  cx.globalAlpha = 1;
  if (M.pings.length) M.raf = requestAnimationFrame(() => mapFrame(J));
}
function mapAdd(J, role, ev) {                           // a tool call: its looks land on the map (evidence re-shows the agents' own looks)
  const M = J.map, kind = LOOK[ev.tool];
  if (!M || !kind || !MAPWHO[role]) return;
  const fresh = !!J.play || (!STATIC && ev.t && Date.now() / 1000 - ev.t < 10);
  M.ev += 1;
  const first = role === 'adj' && !M.looks.some((L) => L.role === 'adj');
  looksOf(ev).forEach(([vid, t]) => M.looks.push({ role, tool: ev.tool, kind: kind[0], vid, t, e: M.ev }));
  (M.calls = M.calls || {})[M.ev] = { role, tool: ev.tool, args: ev.args };
  if (!M.f) return;
  if (fresh) mapNow(J, M.ev);
  const col = cssVar(roleVar(role));
  for (; M.done < M.looks.length; M.done++) {
    const i = mapPut(M, M.looks[M.done]);
    if (i >= 0 && fresh && !M.hide.has(role)) ping(J, i, col, { r: 12 });
  }
  if (first) mapLegend(J);
  mapPaint(J); mapStats(J);
}
function mapCite(J, cited) {
  const M = J.map;
  if (!M) return;
  M.cited = cited.map((s) => ({ vid: s.vid, t: s.at != null ? s.at : s.t0 }));
  if (M.f) mapShowCited(J);
}
function mapShowCited(J) {                               // ring the cited squares, open the close-up, pulse once the map is in view
  const M = J.map;
  M.citedCells = [...new Set(M.cited.map((q) => cellOf(M, q.vid, q.t)).filter((i) => i >= 0))];
  M.citedOn = M.citedCells.length > 0;
  const g = M.g;                                          // where the cited squares are, for keyboard-free tests and the demo recorder
  M.cv.dataset.cited = M.citedCells.map((i) => `${(i % g.cols) * g.p + g.s / 2},${Math.floor(i / g.cols) * g.p + g.s / 2}`).join(' ');
  mapPaint(J); mapStats(J); mapZoom(J);
  if (!M.citedOn) return;
  if (M.obs) M.obs.disconnect();
  M.obs = new IntersectionObserver((es) => {
    if (es.some((e) => e.isIntersecting)) { M.obs.disconnect(); M.obs = null; mapPulse(J); }
  }, { threshold: 0.6 });
  M.obs.observe(M.cv);
}
function mapPulse(J) {
  const M = J.map, ink = cssVar('--ink');
  M.citedCells.forEach((i) => [0, 650, 1300].forEach((d) => ping(J, i, ink, { r: 30, dur: 1300, delay: d, w: 2.5 })));
}
function mapStats(J) {
  const M = J.map, el = $('#smap-stats');
  if (!el) return;
  let seen = 0, framed = 0;
  for (const c of M.cells.values()) { if (topLook(c, M.hide)) seen += 1; if (c.looks.some((L) => L.kind === 3 && !M.hide.has(L.role))) framed += 1; }
  const pct = (seen / M.n) * 100, vids = new Set(M.cited.map((q) => q.vid)).size;
  const span = M.f.hours >= 1 ? `${M.f.hours} hours` : `${Math.max(1, Math.round(M.f.hours * 60))} minutes`;
  el.innerHTML = `${M.citedOn ? `<span class="cite">Out of ${span}, the verdict rests on <b>${M.cited.length} moment${M.cited.length > 1 ? 's' : ''}</b> in ${vids} video${vids > 1 ? 's' : ''}</span>` : ''}<span><b>${fmtInt(seen)}</b> of ${fmtInt(M.n)} squares touched (${seen && pct < 1 ? pct.toFixed(1) : Math.round(pct)}%)</span><span><b>${fmtInt(framed)}</b> looked at frame by frame</span>`;
}
function mapLegend(J) {
  const M = J.map, el = $('#smap-legend');
  if (!el) return;
  const roles = [...(J.cfg.agents === 1 ? ['inv0'] : ['inv0', 'inv1', 'inv2']), ...(M.looks.some((L) => L.role === 'adj') ? ['adj'] : [])];
  el.innerHTML = `${roles.map((r) => `<button class="chip${M.hide.has(r) ? ' off' : ''}" data-r="${r}" title="Show or hide this agent's looks"><i style="background:var(${roleVar(r)})"></i>${MAPWHO[r]}</button>`).join('')}
    <span class="kinds"><span><i class="k1"></i>came up in a search</span><span><i class="k2"></i>transcript read</span><span><i class="k3"></i>frames viewed</span><span><i class="ring"></i>cited by the verdict</span></span>`;
  el.querySelectorAll('[data-r]').forEach((b) => {
    b.onclick = () => { const r = b.dataset.r; if (M.hide.has(r)) M.hide.delete(r); else M.hide.add(r); mapLegend(J); mapPaint(J); mapStats(J); mapZoom(J); };
  });
}
function mapHover(J, e) {
  // rendered pixels -> the canvas's CSS pixels (they differ under CSS zoom, e.g. the demo recorder's 1.5x page)
  const M = J.map, g = M.g, r = M.cv.getBoundingClientRect(), k = M.cv.offsetWidth / (r.width || 1);
  const x = (e.clientX - r.left) * k, y = (e.clientY - r.top) * k;
  const i = Math.floor(y / g.p) * g.cols + Math.floor(x / g.p);
  if (x < 0 || y < 0 || x >= g.W || y >= g.H || i >= M.n) { M.tip.hidden = true; M.hover = -1; mapFrame(J); return; }
  let lo = 0, hi = M.starts.length - 1;                  // the video this square belongs to
  while (lo < hi) { const m = (lo + hi + 1) >> 1; if (M.starts[m] <= i) lo = m; else hi = m - 1; }
  const v = M.f.videos[lo], t0 = (i - M.starts[lo]) * M.f.seg, c = M.cells.get(i), by = {};
  (c ? c.looks : []).filter((L) => !M.hide.has(L.role)).forEach((L) => { (by[L.role] = by[L.role] || new Set()).add(LOOK[L.tool][1]); });
  const cites = M.citedOn ? M.cited.filter((q) => cellOf(M, q.vid, q.t) === i) : [];
  M.tip.innerHTML = `<b>${esc(trunc(v.title || v.id, 64))}</b><span class="muted">${mmss(t0)}-${mmss(Math.min(v.dur, t0 + M.f.seg))} · ${esc(M.f.playlists[v.pl] || '')}</span>
    ${Object.entries(by).map(([rl, s]) => `<span><i style="background:var(${roleVar(rl)})"></i>${MAPWHO[rl]}: ${[...s].join(', ')}</span>`).join('') || '<span class="muted">Not looked at</span>'}
    ${cites.length ? `<span class="cite">Cited by the verdict at ${cites.map((q) => mmss(q.t)).join(', ')}${!STATIC || (J.meta && J.meta.clip) ? ' · click to watch' : ''}</span>` : ''}`;
  M.tip.hidden = false;
  const wrap = M.cv.parentElement, wr = wrap.getBoundingClientRect(), kw = wrap.offsetWidth / (wr.width || 1), tw = M.tip.offsetWidth;
  const ex = (e.clientX - wr.left) * kw, ey = (e.clientY - wr.top) * kw;
  let lx = ex + 14;
  if (lx + tw > wrap.offsetWidth) lx = Math.max(0, ex - tw - 14);
  M.tip.style.left = `${lx}px`; M.tip.style.top = `${ey + 16}px`;
  M.cv.style.cursor = cites.length ? 'pointer' : 'crosshair';
  if (M.hover !== i) { M.hover = i; mapFrame(J); }
}
function mapZoom(J) {                                    // close-up: the deciding video's own timeline with every look at it
  const M = J.map, box = $('#smap-zoom');
  if (!box) return;
  const vids = M.citedOn ? [...new Set(M.cited.map((q) => q.vid))].filter((v) => M.off[v]).slice(0, 2) : [];
  box.innerHTML = vids.map((vid) => {
    const v = M.f.videos[M.off[vid][2]], dur = Math.max(1, v.dur), pct = (t) => Math.max(0, Math.min(100, (t / dur) * 100));
    const looks = M.looks.filter((L) => L.vid === vid && !M.hide.has(L.role));
    let prev = -99, row = 0;
    const pins = M.cited.filter((q) => q.vid === vid).sort((a, b) => a.t - b.t).map((q) => {
      row = pct(q.t) - prev < 9 ? 1 - row : 0; prev = pct(q.t);
      return `<span class="pin${row ? ' up' : ''}" style="left:${pct(q.t).toFixed(2)}%"><em>${mmss(q.t)}</em></span>`;
    });
    return `<div class="zoomv"><div class="zt"><span class="k">Close-up</span><b>${esc(trunc(v.title || vid, 80))}</b><span class="muted">${mmss(dur)} long · ${looks.length} look${looks.length === 1 ? '' : 's'} by the agents</span></div>
      <div class="zbar" style="transform-origin:${pct(M.cited.find((q) => q.vid === vid).t).toFixed(2)}% 50%">${looks.map((L) => `<i class="k${L.kind}" style="left:${pct(L.t).toFixed(2)}%;background:var(${roleVar(L.role)})"></i>`).join('')}${pins.join('')}</div>
      <div class="zaxis"><span>0:00</span><span>${mmss(dur)}</span></div></div>`;
  }).join('');
}
function mapNow(J, e, last) {                           // "Investigator 2 · Zoom · <video> @ 04:33" under the map while it fills
  const M = J.map, el = $('#smap-now'), c = M.calls && M.calls[e];
  if (!el || !c) return;
  const [, name] = TOOL[c.tool] || ['', c.tool];
  el.innerHTML = `<i style="background:var(${roleVar(c.role)})"></i><b>${MAPWHO[c.role]}</b><span>${esc(name)}</span><span class="arg">${esc(trunc(toolArg(c.tool, c.args), 90))}</span>`;
  el.classList.add('on');
  clearTimeout(M.nowT);
  M.nowT = setTimeout(() => el.classList.remove('on'), last ? 1200 : 4000);
}
function mapReplay(J) {                                  // the search again, fast: every tool call in order, then the verdict's moments
  const M = J.map;
  if (!M.f) return;
  clearTimeout(M.rt);
  const looks = M.looks.slice(0, M.done), evs = [...new Set(looks.map((L) => L.e))];
  M.cells = new Map(); M.citedOn = false;
  $('#smap-zoom').innerHTML = '';
  mapPaint(J); mapStats(J);
  const want = Number(window.PORTIA_REPLAY_MS) || 0;     // the demo recorder times the replay to its narration
  const step = want ? want / Math.max(1, evs.length) : Math.max(70, Math.min(260, 7000 / Math.max(1, evs.length)));
  let k = 0;
  const tick = () => {
    if (!M.cv.isConnected) return;
    if (k >= evs.length) { if (M.cited.length) { mapShowCited(J); if (M.obs) { M.obs.disconnect(); M.obs = null; } mapPulse(J); } return; }
    const e = evs[k++];
    mapNow(J, e, k === evs.length);
    looks.filter((L) => L.e === e).forEach((L) => { const i = mapPut(M, L); if (i >= 0 && !M.hide.has(L.role)) ping(J, i, cssVar(roleVar(L.role)), { r: 12 }); });
    mapPaint(J); mapStats(J);
    M.rt = setTimeout(tick, step);
  };
  tick();
}
async function reveal(J, v) {
  const t = await api(`/api/case/${encodeURIComponent(J.c.id)}/truth`);
  const right = v === t.better;
  const worse = t.better === 'A' ? 'B' : 'A';
  const ch = t.changes.filter((x) => x.worse);
  $('#truth').innerHTML = `<div class="card truth"><div class="row"><span class="tag ${right ? 'ok' : 'bad'}">${right ? 'Portia got it right' : 'Portia got it wrong'}</span>
      <b>The dataset's better answer is ${t.better}</b><span class="muted small">(${esc(t.pair)})</span></div>
    ${ch.length ? `<div class="small muted" style="margin-top:10px">What was changed in answer ${worse}:</div><ul>${ch.map((x) => `<li>${esc(x.what)} <span class="tag">${esc(x.kind)}</span></li>`).join('')}</ul>` : ''}</div>`;
  $('#reveal').disabled = true;
}

// ------------------------------------------------------------------ new case
const STEPS = [['download', 'Download the video and its captions'], ['clips', 'Cut it into 30-second clips'], ['index', 'Index the clips for search'], ['ready', 'Ready']];
function stepsHTML(st) {
  const by = {};
  (st.steps || []).forEach((s) => { by[s.step] = s; });
  const err = (st.steps || []).find((s) => s.state === 'error');
  return `<ol class="steps">${STEPS.map(([k, label]) => {
    const s = by[k], state = s ? (s.state === 'done' ? 'done' : 'on') : '';
    return `<li class="${state}"><i></i><span>${esc(label)}${s && s.info ? `<small>${esc(s.info)}</small>` : ''}</span></li>`;
  }).join('')}</ol>${err ? `<div class="banner err">${esc(err.info || 'failed')}</div>` : ''}`;
}
const videoCard = (c) => `<div class="vcard"><img src="/api/collections/${esc(c.id)}/thumb" alt=""${c.source !== 'upload' ? ` onerror="this.src='https://i.ytimg.com/vi/${esc(c.vid)}/mqdefault.jpg'"` : ''}>
  <div><b>${esc(c.title)}</b><div class="small muted">${esc(c.duration_formatted)} · ${c.clips} clip${c.clips === 1 ? '' : 's'} · ${c.captions ? (c.source === 'upload' ? 'uploaded captions' : 'YouTube captions') : 'no captions (visual only)'}</div>
  ${c.url ? `<a class="small" href="${esc(c.url)}" target="_blank" rel="noopener">open on YouTube ↗</a>` : '<span class="small muted">uploaded file</span>'}</div></div>`;
async function pollCollection(st) {                      // until the ingestion ends; returns its final state
  while (st.status === 'running') {
    $('#vprog').innerHTML = stepsHTML(st);
    await new Promise((r) => setTimeout(r, 1500));
    st = await api(`/api/collections/${encodeURIComponent(st.id)}`);
  }
  $('#vprog').innerHTML = stepsHTML(st);
  return st;
}
async function newPage() {
  if (!S.health) await health();
  if (STATIC) {
    $('#app').innerHTML = `<div class="h3">New case</div><h1 class="display" style="font-size:clamp(34px,4vw,48px);margin:8px 0 10px">Ask a new question</h1>
      <div class="card pad"><p class="lede" style="margin:0">This gallery shows recorded investigations. New questions and uploaded videos run on the live app, where three Muse Glimmer agents investigate live.</p>
      ${STATIC.live ? `<div class="cta" style="margin-top:18px"><a class="btn primary big" href="${esc(STATIC.live)}" target="_blank" rel="noopener">Open the live app ↗</a></div>` : ''}</div>`;
    return;
  }
  S.corpus = null;                                       // include videos added since the last visit
  await loadLib();
  const { collections } = await api('/api/collections');
  const ready = collections.filter((c) => c.status === 'ready').map((c) => c.collection);
  const builtIn = Object.keys(S.corpus).filter((d) => !d.startsWith('Your video:')).sort();
  S.newSrc = S.newSrc || 'library';
  const d0 = S.newDomain && S.corpus[S.newDomain] ? S.newDomain : 'Documentary';
  $('#app').innerHTML = `<div class="h3">New case</div><h1 class="display" style="font-size:clamp(34px,4vw,48px);margin:8px 0 10px">Ask a new question</h1>
    <p class="lede">Ask about something visible or said in the footage, and paste two candidate answers, for example from two different models. The investigators search the footage themselves.</p>
    <div class="card pad form" style="margin-top:22px">
      <div class="seg" id="src"><button data-v="library" class="${S.newSrc === 'library' ? 'on' : ''}">Indexed collections <small>${fmtInt(builtIn.reduce((s, d) => s + S.corpus[d].videos, 0))} videos</small></button>
        <button data-v="youtube" class="${S.newSrc === 'youtube' ? 'on' : ''}">An uploaded video <small>up to 30 min</small></button></div>
      <div id="srcbox"></div>
      <div><label for="nq">Question</label><textarea id="nq" placeholder="e.g. What number is painted on the island of the floating museum ship, and how many pylons hold the bridge?"></textarea></div>
      <div class="seg" id="nmode" style="margin-top:4px"><button data-m="one" class="${S.newMode === 'one' ? 'on' : ''}">Check one answer</button><button data-m="two" class="${S.newMode !== 'one' ? 'on' : ''}">Compare two answers</button></div>
      <div class="two" id="nanswers"><div><label for="na" id="nalabel">${S.newMode === 'one' ? "The AI's answer" : 'Answer A'}</label><textarea id="na"></textarea></div><div id="nbwrap"${S.newMode === 'one' ? ' style="display:none"' : ''}><label for="nb">Answer B</label><textarea id="nb"></textarea></div></div>
      <p class="small muted" id="nmodehint" style="margin:-4px 0 0${S.newMode === 'one' ? '' : ';display:none'}">Muse Glimmer writes a copy of the answer with 2 or 3 checkable details changed (a number, a colour, an object, on-screen text), and the jury rules which version the footage fits. It tests those details, not every claim in the answer.</p>
      <div id="opts">${optsHTML(false)}</div>
      <div class="row"><button class="btn primary big" id="go">${IC.play} Convene the jury</button><button class="btn" id="ex">Fill with a library example</button></div>
      <div id="nerr" role="status" aria-live="polite"></div>
    </div>`;
  const pickDomain = () => (S.newSrc === 'library' ? ($('#dom') || {}).value : S.newVideo && S.newVideo.domain);
  const say = (text, kind = 'note') => {                 // kind: note (muted line) | err (red banner, scrolled into view)
    const el = $('#nerr');
    el.className = kind === 'err' ? 'banner err' : 'small muted';
    el.style.marginTop = kind === 'err' ? '' : '10px';
    el.textContent = text;
    if (kind === 'err') el.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  };
  const drawSrc = () => {
    $$('#src button').forEach((b) => b.classList.toggle('on', b.dataset.v === S.newSrc));
    $('#ex').disabled = S.newSrc !== 'library';
    if (S.newSrc === 'library') {
      $('#srcbox').innerHTML = `<label for="dom">Collection</label><select id="dom">${builtIn.map((d) => `<option ${d === d0 ? 'selected' : ''}>${esc(d)}</option>`).join('')}</select>
        <div class="small muted" id="domstat" style="margin-top:6px"></div>`;
      const stat = () => { const d = $('#dom').value, s = S.corpus[d]; S.newDomain = d;
        $('#domstat').textContent = s ? `${s.playlists.length} playlists · ${fmtInt(s.videos)} videos · ${s.hours} hours: ${s.playlists.slice(0, 4).join(' · ')}${s.playlists.length > 4 ? ' …' : ''}` : ''; };
      $('#dom').onchange = stat;
      stat();
      return;
    }
    S.newHow = 'file';                                    // YouTube links are off: uploads only
    $('#srcbox').innerHTML = `<div class="two"><div><label for="upf">Video file (.mp4, .mov, .mkv, .webm)</label><input id="upf" type="file" accept="video/*"></div>
        <div><label for="upc">Captions, optional (.vtt or .srt)</label><input id="upc" type="file" accept=".vtt,.srt"></div></div>
        <div class="row" style="margin-top:10px"><input id="upt" class="grow" placeholder="Title (optional)"><button class="btn" id="upv">Upload and index</button></div>
      <div class="small muted" style="margin-top:8px">Transcripts come from the uploaded caption file.</div>
      <div id="vprog"></div>
      ${ready.length ? `<div class="small muted" style="margin-top:10px">Videos added before:</div><div class="row" style="margin-top:6px">${ready.map((c) => `<button class="chip${S.newVideo && S.newVideo.id === c.id ? ' on' : ''}" data-col="${esc(c.id)}">${esc(c.title.slice(0, 40))}</button>`).join('')}</div>` : ''}
      <div id="vsel">${S.newVideo ? videoCard(S.newVideo) : ''}</div>`;
    $$('[data-col]').forEach((b) => { b.onclick = () => { S.newVideo = ready.find((c) => c.id === b.dataset.col); drawSrc(); }; });
    $$('#how [data-h]').forEach((b) => { b.onclick = () => { S.newHow = b.dataset.h; drawSrc(); }; });
    const done = async (st) => {
      st = await pollCollection(st);
      if (st.status === 'ready') {
        S.newVideo = st.collection;
        S.corpus = null; await loadLib();
        $('#vsel').innerHTML = videoCard(S.newVideo);
      }
    };
    if ($('#addv')) $('#addv').onclick = async () => {
      S.newUrl = $('#yt').value.trim();
      $('#addv').disabled = true;
      try {
        await done(await api('/api/collections', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ url: S.newUrl }) }));
      } catch (e) { $('#vprog').innerHTML = `<div class="banner err">${esc(e.message)}</div>`; }
      $('#addv').disabled = false;
    };
    if ($('#upv')) $('#upv').onclick = async () => {
      const f = $('#upf').files[0];
      if (!f) { $('#vprog').innerHTML = '<div class="banner err">Choose a video file first.</div>'; return; }
      const fd = new FormData();
      fd.append('file', f);
      if ($('#upc').files[0]) fd.append('captions', $('#upc').files[0]);
      fd.append('title', $('#upt').value.trim());
      if (S.health && S.health.access && !codeStore.get()) {        // public mode: the code first, then the upload
        const code = await askCode(false);
        if (!code) return;
        codeStore.set(code);
      }
      $('#upv').disabled = true;
      const x = new XMLHttpRequest();                    // XHR, for upload progress
      x.open('POST', '/api/collections/upload');
      x.setRequestHeader('X-Portia-Code', codeStore.get());
      x.upload.onprogress = (e) => { if (e.lengthComputable) $('#vprog').innerHTML = `<div class="small muted" style="margin-top:12px">Uploading… ${Math.round(100 * e.loaded / e.total)}%</div>`; };
      x.onload = async () => {
        $('#upv').disabled = false;
        let j = null;
        try { j = JSON.parse(x.responseText); } catch (e) { /* not JSON */ }
        if (x.status === 401) codeStore.set('');                 // a wrong code: ask again next time
        if (x.status !== 200) { $('#vprog').innerHTML = `<div class="banner err">${esc(x.status === 401 ? 'That access code did not work; try the upload again.' : (j && j.detail) || x.statusText)}</div>`; return; }
        try { await done(j); } catch (e) { $('#vprog').innerHTML = `<div class="banner err">${esc(e.message)}</div>`; }
      };
      x.onerror = () => { $('#upv').disabled = false; $('#vprog').innerHTML = '<div class="banner err">The upload failed.</div>'; };
      x.send(fd);
    };
  };
  $('#src').onclick = (e) => { const b = e.target.closest('button[data-v]'); if (!b) return; S.newSrc = b.dataset.v; drawSrc(); };
  drawSrc();
  const rebind = () => { $('#opts').innerHTML = optsHTML(false); bindOpts(rebind); };
  bindOpts(rebind);
  $('#ex').onclick = async () => {
    const pool = S.lib.cases.filter((c) => c.domain === $('#dom').value);
    const pick = pool[Math.floor(Math.random() * pool.length)];
    const c = await api(`/api/case/${encodeURIComponent(pick.id)}`);
    $('#nq').value = c.question; $('#na').value = c.answer_a; $('#nb').value = c.answer_b;
    say(`Filled from library case ${c.id}; any field can be edited.`);
  };
  $$('#nmode button').forEach((b) => { b.onclick = () => {
    S.newMode = b.dataset.m;
    $$('#nmode button').forEach((x) => x.classList.toggle('on', x === b));
    $('#nbwrap').style.display = S.newMode === 'one' ? 'none' : '';
    $('#nmodehint').style.display = S.newMode === 'one' ? '' : 'none';
    $('#nalabel').textContent = S.newMode === 'one' ? "The AI's answer" : 'Answer A';
  }; });
  $('#go').onclick = async () => {
    const domain = pickDomain();
    if (!domain) { say(S.newSrc === 'library' ? 'Pick a collection first.' : 'Pick an uploaded video above (click its card), or upload one first.', 'err'); return; }
    const one = S.newMode === 'one';
    const body = one ? { single: { domain, question: $('#nq').value, answer: $('#na').value }, agents: 3, resolve: S.opts.resolve, quick: S.opts.quick }
      : { custom: { domain, question: $('#nq').value, answer_a: $('#na').value, answer_b: $('#nb').value }, agents: S.opts.agents, resolve: S.opts.resolve, quick: S.opts.quick };
    const short = (s) => String(s || '').trim().length < 8;
    if (short($('#nq').value) || short($('#na').value) || (!one && short($('#nb').value))) {
      say(one ? 'Write a question and the answer first (at least 8 characters each).' : 'Write a question and both answers first (at least 8 characters each).', 'err');
      return;
    }
    const go = $('#go'), label = go.innerHTML;
    go.disabled = true; go.innerHTML = `${IC.play} Starting the jury…`;
    say('');
    try {
      const j = await api('/api/jobs', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      location.hash = `#/job/${j.id}`;
    } catch (e) {
      go.disabled = false; go.innerHTML = label;
      say(`Could not start the jury: ${e.message === 'Failed to fetch' ? 'the server did not answer (is it running?)' : e.message}`, 'err');
    }
  };
}

// ------------------------------------------------------------------ history
async function historyPage() {
  await loadTrust();
  const { jobs } = await api('/api/jobs');
  const how = { single: 'one investigator', unanimous: 'unanimous', vote: 'majority', glimmer: 'Glimmer adjudicator', spark: 'Spark Open adjudicator',
    spark13: 'Spark 1.3 adjudicator', spark13_confirm: 'agreed, Spark 1.3 confirmed', spark13_overturn: 'agreed, Spark 1.3 overturned' };
  const rows = jobs.map((j) => ({ j, tr: !j.running && j.final ? trustFor(j.final, j.config && j.config.quick, !String(j.case_id || '').startsWith('shard'), j.kind) : null }));
  const nrev = rows.filter((r) => r.tr && r.tr.level === 'review').length, nspot = rows.filter((r) => r.tr && r.tr.level === 'spot').length;
  S.histFilter = S.histFilter || 'all';
  const draw = () => {
    const shown = rows.filter((r) => S.histFilter === 'all' || (r.tr && r.tr.level === 'review'));
    $('#htable').innerHTML = `<table class="t"><tr><th>When</th><th>Case</th><th>Setup</th><th>Verdict</th><th>Trust</th><th class="num">Time</th></tr>
    ${shown.map(({ j, tr }) => {
      const f = j.final || {};
      const when = j.created ? new Date(j.created * 1000).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '';
      return `<tr style="cursor:pointer" onclick="location.hash='#/job/${esc(j.id)}'"><td class="small">${esc(when)}</td>
        <td><span class="tag">${esc(domName(j.domain || ''))}</span> <span class="small">${esc((j.question || '').slice(0, 120))}${(j.question || '').length > 120 ? '…' : ''}</span></td>
        <td class="small muted">${j.config ? `${j.config.single ? 'one answer · ' : ''}${j.config.agents} investigator${j.config.agents > 1 ? 's' : ''} · ${esc(j.config.resolve)}${j.config.quick ? ' · quick' : ''}` : ''}</td>
        <td>${j.running ? '<span class="tag brand">running</span>' : f.verdict ? `<span class="letter ${f.verdict}" style="width:20px;height:20px;font-size:11px">${f.verdict}</span> <span class="small muted">${esc(how[f.how] || f.how || '')}</span>` : '<span class="tag">—</span>'}</td>
        <td>${tierTag(tr)}</td>
        <td class="num small">${f.wall ? mmss(f.wall) : ''}</td></tr>`;
    }).join('') || `<tr><td colspan="6" class="muted">${S.histFilter === 'all' ? 'No runs yet.' : 'No verdict needs review right now.'}</td></tr>`}</table>`;
    $$('#hfilter button').forEach((b) => b.classList.toggle('on', b.dataset.f === S.histFilter));
  };
  $('#app').innerHTML = `<div class="h3">History</div><h1 class="h2" style="margin:6px 0 10px">Recent runs</h1>
    <div class="row" style="margin-bottom:14px;align-items:center"><div class="seg" id="hfilter"><button data-f="all">All runs</button><button data-f="review">Needs review</button></div>
      <span class="small muted grow">Of ${rows.filter((r) => r.tr).length} finished runs, ${nrev} need review and ${nspot} deserve a spot-check; the cited frames make each a short check.</span></div>
    <div class="card tablewrap" id="htable"></div>`;
  $$('#hfilter button').forEach((b) => { b.onclick = () => { S.histFilter = b.dataset.f; draw(); }; });
  draw();
}

// ------------------------------------------------------------------ batch audit (plan 016)
function parseCSV(text) {                        // RFC 4180-ish: quoted fields may hold commas, quotes ("") and newlines
  const rows = [];
  let row = [], f = '', q = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (q) { if (ch === '"') { if (text[i + 1] === '"') { f += '"'; i++; } else q = false; } else f += ch; }
    else if (ch === '"') q = true;
    else if (ch === ',') { row.push(f); f = ''; }
    else if (ch === '\n' || ch === '\r') {
      if (ch === '\r' && text[i + 1] === '\n') i++;
      row.push(f); f = '';
      if (row.some((x) => x.trim())) rows.push(row);
      row = [];
    } else f += ch;
  }
  row.push(f);
  if (row.some((x) => x.trim())) rows.push(row);
  return rows;
}
function parseBatch(text) {                      // CSV with a header row, or JSON lines; "collection" is the corpus domain
  const t = text.trim();
  if (!t) return [];
  const norm = (o) => { const x = {}; Object.entries(o).forEach(([k, v]) => { const kk = k.trim().toLowerCase().replace(/[\s-]+/g, '_'); x[kk === 'collection' ? 'domain' : kk] = String(v == null ? '' : v).trim(); }); return x; };
  if (t.startsWith('{')) return t.split(/\n+/).filter((l) => l.trim()).map((l) => norm(JSON.parse(l)));
  const [head, ...rows] = parseCSV(t);
  return rows.map((r) => norm(Object.fromEntries(head.map((h, i) => [h, r[i] || '']))));
}
const BATCH_TEMPLATE = 'collection,question,answer_a,answer_b\nDocumentary,"What number is painted on the island of the museum ship, and how many pylons hold the bridge?","The number 16, and two pylons.","The number 18, and two pylons."\n';
const apiHost = () => (STATIC ? (STATIC.live || 'https://portia.example.com') : location.origin);
function apiExamplesHTML() {
  const H = apiHost();
  return `<pre class="code">## one case: three Muse Glimmer agents, Spark 1.3 re-checks the verdict
curl -X POST ${H}/api/jobs -H 'Content-Type: application/json' -d '{
  "custom": {"domain": "Documentary", "question": "…", "answer_a": "…", "answer_b": "…"},
  "agents": 3, "resolve": "spark13all"}'          # -> {"id": "1102-093115-ab12"}

## follow it live (server-sent events: every turn, look and frame), or just fetch the verdict
curl -N ${H}/api/jobs/1102-093115-ab12/events
curl ${H}/api/jobs/1102-093115-ab12               # final: verdict, how, track record, cost

## a batch audit (up to 100 cases), then the results with a trust tier per row
curl -X POST ${H}/api/batches -H 'Content-Type: application/json' -d '{
  "name": "model v7 eval", "agents": 3, "resolve": "glimmer",
  "items": [{"domain": "Documentary", "question": "…", "answer_a": "…", "answer_b": "…"}]}'
curl ${H}/api/batches/b1102-093200-cd34/export.csv</pre>`;
}
async function batchesPage() {
  await loadLib();
  if (!S.health && !STATIC) await health();         // the Spark options' availability
  const intro = `<div class="h3">Audit a batch</div><h1 class="display" style="font-size:clamp(34px,4vw,48px);margin:8px 0 10px">Check a whole eval run at once</h1>
    <p class="lede">One row per case: a collection, a question and two candidate answers (or a library <code>case_id</code>). Portia queues every case, fills the table as verdicts land, marks which ones a person should check, and exports the results as CSV or JSON. The same thing works from code through the API.</p>`;
  if (STATIC) {
    let recorded = [];
    try { recorded = (await api('/api/batches')).batches || []; } catch (e) { /* none recorded */ }
    $('#app').innerHTML = `${intro}<div class="card pad"><p style="margin:0">Batch audits run on the live app.${recorded.length ? ' A recorded batch is below.' : ''}</p>
      ${STATIC.live ? `<div class="cta" style="margin-top:14px"><a class="btn primary big" href="${esc(STATIC.live)}#/audit" target="_blank" rel="noopener">Open the live app ↗</a></div>` : ''}</div>
      ${recorded.length ? `<div class="card tablewrap" style="margin-top:16px"><table class="t"><tr><th>Recorded batch</th><th class="num">Cases</th></tr>${recorded.map((b) => `<tr style="cursor:pointer" onclick="location.hash='#/batch/${esc(b.id)}'"><td>${esc(b.name)}</td><td class="num">${b.n}</td></tr>`).join('')}</table></div>` : ''}
      <div class="card pad" style="margin-top:16px"><div class="h3">API</div>${apiExamplesHTML()}</div>`;
    return;
  }
  const { batches } = await api('/api/batches');
  const fin = batches.find((b) => b.n && b.done === b.n);
  $('#app').innerHTML = `${intro}
    ${fin ? `<a class="card catch" style="max-width:none;margin:0 0 16px" href="#/batch/${esc(fin.id)}"><span class="tag ok">Finished</span><span>A finished audit, open to everyone: ${fin.n} cases, each with a verdict, a trust level and its cost.</span><span class="go">${IC.arrow}</span></a>` : ''}
    <div class="card pad form">
      <div><label for="btext">Cases (CSV with a header row, or JSON lines)</label><textarea id="btext" rows="8" spellcheck="false" placeholder="collection,question,answer_a,answer_b"></textarea></div>
      <div class="row" style="gap:8px;flex-wrap:wrap"><label class="btn" style="cursor:pointer">Upload a file<input type="file" id="bfile" accept=".csv,.jsonl,.json,.txt" hidden></label>
        <button class="btn" id="bex">Try 6 library cases</button>
        <a class="btn" download="portia_batch_template.csv" href="data:text/csv;charset=utf-8,${encodeURIComponent(BATCH_TEMPLATE)}">Template CSV</a>
        <span class="small muted grow" id="bcount"></span></div>
      <div><label for="bname">Name (optional)</label><input id="bname" maxlength="120" placeholder="e.g. model v7, video QA eval"></div>
      <div id="opts">${optsHTML(false)}</div>
      <div class="row"><button class="btn primary big" id="bgo">${IC.play} Run the audit</button></div>
      <div id="berr" role="status" aria-live="polite"></div>
    </div>
    ${batches.length ? `<div class="card tablewrap" style="margin-top:16px"><table class="t"><tr><th>Earlier batches</th><th>When</th><th class="num">Done</th></tr>
      ${batches.map((b) => `<tr style="cursor:pointer" onclick="location.hash='#/batch/${esc(b.id)}'"><td>${esc(b.name)}</td><td class="small">${b.created ? new Date(b.created * 1000).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : ''}</td><td class="num">${b.done}/${b.n}</td></tr>`).join('')}</table></div>` : ''}
    <div class="card pad" style="margin-top:16px"><div class="h3">API</div>${apiExamplesHTML()}</div>`;
  const rebind = () => { $('#opts').innerHTML = optsHTML(false); bindOpts(rebind); };
  bindOpts(rebind);
  const err = (m) => { $('#berr').className = m ? 'banner err' : ''; $('#berr').textContent = m || ''; if (m) $('#berr').scrollIntoView({ block: 'nearest', behavior: 'smooth' }); };
  const count = () => { try { const n = parseBatch($('#btext').value).length; $('#bcount').textContent = n ? `${n} case${n > 1 ? 's' : ''}` : ''; err(''); } catch (e) { $('#bcount').textContent = ''; } };
  $('#btext').oninput = count;
  $('#bfile').onchange = async (e) => { const f = e.target.files[0]; if (f) { $('#btext').value = await f.text(); count(); } };
  $('#bex').onclick = () => {
    // one case per domain (the first in each), a representative mix rather than the hand-picked splits of the featured set
    const ids = S.lib.domains.slice(0, 6).map((d) => S.lib.cases.filter((c) => c.domain === d).map((c) => c.id).sort()[0]).filter(Boolean);
    $('#btext').value = `case_id\n${ids.join('\n')}\n`;
    $('#bname').value = $('#bname').value || 'Library sample';
    count();
  };
  $('#bgo').onclick = async () => {
    let items;
    try { items = parseBatch($('#btext').value); } catch (e) { err(`Could not read the cases: ${e.message}`); return; }
    if (!items.length) { err('Paste or upload at least one case.'); return; }
    if (items.length > 100) { err('A batch takes at most 100 cases.'); return; }
    const go = $('#bgo'), label = go.innerHTML;
    go.disabled = true; go.innerHTML = `${IC.play} Starting…`;
    try {
      const b = await api('/api/batches', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: $('#bname').value, items, agents: S.opts.agents, resolve: S.opts.resolve, quick: S.opts.quick }) });
      location.hash = `#/batch/${b.id}`;
    } catch (e) { go.disabled = false; go.innerHTML = label; err(`Could not start the audit: ${e.message}`); }
  };
}
async function batchPage(bid) {
  await loadTrust();
  const how = { single: 'one investigator', unanimous: 'unanimous', vote: 'majority', glimmer: 'Glimmer adjudicator', spark: 'Spark Open',
    spark13: 'Spark 1.3', spark13_confirm: 'agreed, Spark 1.3 confirmed', spark13_overturn: 'agreed, Spark 1.3 overturned' };
  const draw = async () => {
    const b = await api(`/api/batches/${bid}`);
    const R = b.rows, done = R.filter((r) => r.status === 'done');
    const n = { accept: 0, spot: 0, review: 0 };
    done.forEach((r) => { if (r.trust) n[r.trust.level]++; });
    const usd = done.reduce((s, r) => s + (((r.final || {}).usage || {}).spark_usd || 0), 0);
    const pending = R.some((r) => r.status === 'queued' || r.status === 'running');
    $('#app').innerHTML = `<div class="crumbs"><a href="#/audit">Audit</a><span>›</span><span>${esc(b.name)}</span></div>
      <h1 class="h2" style="margin:6px 0 4px">${esc(b.name)}</h1>
      <div class="small muted">${R.length} cases · ${esc(`${b.config.agents} investigator${b.config.agents > 1 ? 's' : ''} · ${b.config.resolve}${b.config.quick ? ' · quick' : ''}`)}</div>
      <div class="card pad" style="margin-top:14px"><div class="row" style="align-items:center;gap:14px;flex-wrap:wrap">
        <div class="grow" style="min-width:220px"><div class="meter"><div class="bar"><i style="width:${(100 * done.length / R.length).toFixed(0)}%"></i></div>
          <div class="cap"><span><b style="color:var(--ink)">${done.length} of ${R.length}</b> done${pending ? ' · updating live' : ''}</span><span>API cost $${usd.toFixed(4)}</span></div></div></div>
        ${['accept', 'spot', 'review'].map((l) => `<span class="tag tier ${TIER[l].cls}">${TIER[l].icon}${n[l]} ${TIER[l].label.toLowerCase()}</span>`).join('')}
        ${STATIC ? '' : `<a class="btn" href="/api/batches/${esc(bid)}/export.csv">Export CSV</a>`}<button class="btn" id="bjson">Export JSON</button></div></div>
      <div class="card tablewrap" style="margin-top:14px"><table class="t"><tr><th class="num">#</th><th>Case</th><th>Verdict</th><th>Trust</th><th class="num">Time</th><th class="num">API cost</th></tr>
      ${R.map((r, i) => { const f = r.final || {}; return `<tr${r.job ? ` style="cursor:pointer" onclick="location.hash='#/job/${esc(r.job)}'"` : ''}><td class="num small">${i + 1}</td>
        <td><span class="tag">${esc(domName(r.domain || ''))}</span> <span class="small">${esc((r.question || '').slice(0, 110))}${(r.question || '').length > 110 ? '…' : ''}</span></td>
        <td>${r.status === 'done' ? `<span class="letter ${f.verdict}" style="width:20px;height:20px;font-size:11px">${f.verdict}</span> <span class="small muted">${esc(how[f.how] || f.how || '')}</span>` : `<span class="tag${r.status === 'running' ? ' brand' : ''}">${esc(r.status)}</span>`}</td>
        <td>${tierTag(r.trust)}</td><td class="num small">${f.wall ? mmss(f.wall) : ''}</td><td class="num small">${r.status === 'done' ? `$${(((f.usage || {}).spark_usd) || 0).toFixed(4)}` : ''}</td></tr>`; }).join('')}</table></div>`;
    $('#bjson').onclick = () => {
      const a = document.createElement('a');
      a.href = URL.createObjectURL(new Blob([JSON.stringify(b, null, 1)], { type: 'application/json' }));
      a.download = `portia_${bid}.json`; a.click();
    };
    return pending;
  };
  if (await draw() && !STATIC) S.clock = setInterval(async () => { if (!(await draw())) { clearInterval(S.clock); S.clock = null; } }, 3000);
}

// ------------------------------------------------------------------ proof: the track record on the library
const SERIES = ['single', 'vote', 'jury', 'spark13', 'spark'];   // an ordinal progression: one agent -> Portia + Spark Open
function dotPlot(rows, P, lo, hi) {                           // a dot plot: one row per group, one dot per setup
  // phones: the viewBox follows the screen width so the text keeps its size (a 900-wide viewBox shrinks it to ~4 px)
  const cw = ($('#app') && $('#app').clientWidth) || 900, narrow = cw < 700;
  const W = narrow ? Math.max(300, cw - 50) : 900, L = narrow ? 104 : 150, R = narrow ? 50 : 60, rd = narrow ? 5.5 : 7;
  const rowH = 34, top = 30, H = top + rows.length * rowH + 10;
  const x = (v) => L + ((v - lo) / (hi - lo)) * (W - L - R);
  const ticks = []; for (let v = lo; v <= hi; v += 10) ticks.push(v);
  return `<svg class="dots" viewBox="0 0 ${W} ${H}" role="img" aria-label="accuracy by group and setup">
    ${ticks.map((v) => `<g><line x1="${x(v)}" x2="${x(v)}" y1="${top - 8}" y2="${H - 6}" class="grid"/><text x="${x(v)}" y="${top - 14}" class="tick">${v}%</text></g>`).join('')}
    ${rows.map((r, i) => {
      const y = top + i * rowH + rowH / 2, vs = SERIES.map((s) => r[s]).filter((v) => v != null);
      return `<g class="row${r.bold ? ' bold' : ''}"><text x="${L - 14}" y="${y + 4}" class="lab">${esc(r.label)}</text>
        <line x1="${x(Math.min(...vs))}" x2="${x(Math.max(...vs))}" y1="${y}" y2="${y}" class="span"/>
        ${SERIES.map((s) => `<circle cx="${x(r[s])}" cy="${y}" r="${rd}" class="dot s-${s}"><title>${esc(P.labels[s])}: ${(+r[s]).toFixed(1)}%${r.n ? ` (${r.n} cases)` : ''}</title></circle>`).join('')}
        <text x="${x(Math.max(...vs)) + rd + 6}" y="${y + 4}" class="val">${Math.max(...vs).toFixed(1)}%</text></g>`;
    }).join('')}</svg>`;
}
const legendHTML = (P) => `<div class="legend">${SERIES.map((s) => `<span><i class="sw s-${s}"></i>${esc(P.labels[s])}</span>`).join('')}</div>`;
function trustSectionHTML(P) {
  const T = P.trust;
  const modes = [['glimmer', 'Muse Glimmer only (default, no API cost)'], ['spark13all', 'Spark 1.3 checks every verdict (~$0.004 per case)']].filter(([m]) => T.modes[m]);
  const block = ([m, title]) => {
    const M = T.modes[m];
    const share = { accept: 0, spot: 0, review: 0 };
    let an = 0, ar = 0;
    M.paths.forEach((p) => { const l = tierOf(p.pct); share[l] += p.share; if (l === 'accept') { an += p.n; ar += p.n * p.pct; } });
    const bar = ['accept', 'spot', 'review'].filter((l) => share[l] > 0)
      .map((l) => `<i class="tseg ${TIER[l].cls}" style="flex:${share[l]}" title="${TIER[l].label}: ${share[l].toFixed(1)}% of cases"></i>`).join('');
    const rows = M.paths.map((p) => `<tr><td>${esc(p.label)}</td><td class="num">${p.share}%</td><td class="num">${p.pct}%</td><td>${tierTag({ level: tierOf(p.pct), pct: p.pct })}</td></tr>`).join('');
    return `<div class="tblock"><div class="row" style="align-items:baseline;gap:8px"><b class="grow">${esc(title)}</b><span class="small muted">${M.overall}% right overall</span></div>
      <div class="tierbar" role="img" aria-label="share of cases per tier">${bar}</div>
      <div class="small muted">${['accept', 'spot', 'review'].filter((l) => share[l] > 0).map((l) => `${TIER[l].label} ${share[l].toFixed(0)}%`).join(' · ')}</div>
      <p class="small" style="margin:8px 0 10px">Auto-accept only the green tier: <b>${share.accept.toFixed(0)}% of cases at ${(ar / Math.max(an, 1)).toFixed(1)}% right</b>. Everything else goes to review with the cited frames attached.</p>
      <div class="tablewrap"><table class="t"><tr><th>How the verdict was reached</th><th class="num">Share</th><th class="num">Right</th><th>Tier</th></tr>${rows}</table></div></div>`;
  };
  return `<div class="card pad" style="margin-top:16px"><h2 class="h2" style="font-size:24px">When to trust a verdict</h2>
    <p class="small muted" style="margin:6px 0 14px">Portia states which of its verdicts to trust. Every verdict carries a tier from the measured accuracy of the path that produced it: did the three agents agree, did they settle it within their turns, and what did the adjudicator do. Safe to accept: at least ${T.levels.accept}% right on the development set; spot-check: ${T.levels.spot} to ${T.levels.accept}%; below that, it needs review by a person.</p>
    <div class="tgrid">${modes.map(block).join('')}</div>
    <p class="small muted" style="margin:12px 0 0">One more rule, from what the answers disagree about: when it is words on screen or where things are, the agents are right only ${weakRange(P.kinds)} of the time even when they agree on their own (Muse Glimmer jury${P.kinds ? `, ${P.kinds.triples_local} investigator triples` : ''}), so Portia never marks such a verdict safe to accept; it asks for a quick look instead.</p>
    ${P.kinds ? `<div class="tablewrap" style="margin-top:10px"><table class="t"><tr><th>What the answers disagree about</th><th class="num">Share</th><th class="num">Muse Glimmer jury</th><th class="num">Agreed on their own</th><th class="num">Spark 1.3 checks all</th></tr>${P.kinds.rows.map((r) => `<tr><td>${esc(r.label)}</td><td class="num">${r.share}%</td><td class="num">${r.local}%</td><td class="num">${r.local_settled}%<span class="muted small"> · ${r.settled_contests} cases</span></td><td class="num">${r.spark13all}%</td></tr>`).join('')}</table></div>
      <p class="small muted" style="margin:6px 0 0">Development set: the Muse Glimmer jury over ${P.kinds.triples_local} investigator triples, Spark 1.3 over ${P.kinds.triples_spark13all}. Spark 1.3 helps most where Glimmer reads worst, words on screen and positions, and not at all with counts.</p>` : ''}</div>`;
}
function heldoutHTML(H) {                       // audit 021: the pre-registered held-out check
  const g = H.groups['all held-out'], c = H.groups['question not in shards 3-4'], acc = H.tiers.accept || {};
  const ci = (x) => `${x[0].toFixed(1)}% <span class="small muted">[${x[1].toFixed(1)}, ${x[2].toFixed(1)}]</span>`;
  return `<div class="card pad" style="margin-top:16px"><div class="row" style="align-items:center;gap:18px;flex-wrap:wrap">
      <div class="big-num">${g.portia[0].toFixed(1)}%</div>
      <div class="grow" style="min-width:240px"><b>Held-out confirmation: Portia on Muse Glimmer alone, ${H.n} contests never used for any choice</b>
        <p class="small muted" style="margin:4px 0 0">Pre-registered before it ran: the same three Muse Glimmer agents and the Glimmer adjudicator on the untouched shards 5-6. Portia ${ci(g.portia)} against ${ci(g.vote)} for the majority vote (development: ${H.dev.local}% and ${H.dev.vote}%). On the ${c.n} contests whose question never appears in development: ${ci(c.portia)}. "Safe to accept" covers ${acc.share}% of held-out cases at ${acc.pct}% right, as calibrated (88.7% in development). The held-out splits went better than development's (76.7% against 63.7%; 86 splits, so partly chance).</p></div></div></div>`;
}
function heldoutSparkHTML(H) {                  // audit 022: Muse Spark 1.3 on the same held-out contests
  const g = H.groups['all held-out'], c = H.groups['question not in shards 3-4'], u = H.unanimous;
  const ci = (x) => `${x[0].toFixed(1)}% <span class="small muted">[${x[1].toFixed(1)}, ${x[2].toFixed(1)}]</span>`;
  const row = (label, k) => `<tr><td>${label}</td><td class="num">${ci(g[k])}</td><td class="num">${ci(c[k])}</td></tr>`;
  return `<div class="card pad" style="margin-top:16px"><div class="h3">Held-out, with Muse Spark 1.3 (audit 022, pre-registered)</div>
    <div class="tablewrap" style="margin-top:8px"><table class="t"><tr><th>Setup</th><th class="num">All ${g.n} contests</th><th class="num">Question never in development (${c.n})</th></tr>
      ${row('Majority vote', 'vote')}${row('Portia on Muse Glimmer alone', 'glimmer')}${row('Muse Spark 1.3 on splits', 'spark13')}${row('Muse Spark 1.3 checking every verdict', 'spark13all')}</table></div>
    <p class="small muted" style="margin:8px 0 0">One run of the development settings on the same held-out contests, reported as it came out. On the ${u.n} verdicts all three agents agreed on (${u.wrong} of them wrong), Muse Spark 1.3 fixed ${u.fixed} and broke ${u.broke}.</p></div>`;
}
async function proofPage() {
  const P = await api('/api/proof');
  S.trust = P.trust || S.trust || null;
  const o = P.overall, k = P.by_kind;
  const rows = [{ label: 'All cases', ...o, bold: true }, ...P.by_domain.map((d) => ({ label: d.domain, ...d }))];
  $('#app').innerHTML = `<div class="h3">Proof</div><h1 class="display" style="font-size:clamp(34px,4vw,52px);margin:8px 0 12px">How often Portia is right</h1>
    <p class="lede">The library's 220 cases each pair an original answer with an edited copy that gets a few visual details wrong. Every number below pools five independent sets of three investigators over all 220 cases (1,100 runs; development set, recorded runs).</p>
    <div class="kpis4">
      <div class="card pad"><div class="big-num">${o.jury.toFixed(1)}%</div><b>Portia on Muse Glimmer alone</b><p class="small muted">three Muse Glimmer agents + Glimmer adjudicator, $0 API</p></div>
      <div class="card pad"><div class="big-num">${o.spark13.toFixed(1)}%</div><b>Portia + Muse Spark 1.3</b><p class="small muted">Meta Model API on splits only: $${P.cost.spark13_usd_per_case.toFixed(4)} per case</p></div>
      <div class="card pad"><div class="big-num">${o.spark.toFixed(1)}%</div><b>Portia + Muse Spark Open</b><p class="small muted">Baseten on splits only: $${P.cost.spark_usd_per_case.toFixed(3)} per case</p></div>
      <div class="card pad"><div class="big-num">${k.split.jury.toFixed(1)}% → ${k.split.spark.toFixed(1)}%</div><b>On the hard cases</b><p class="small muted">${k.split.n} runs where the agents split (Spark 1.3: ${k.split.spark13.toFixed(1)}%)</p></div>
    </div>
    ${P.heldout && P.heldout.groups ? heldoutHTML(P.heldout) : ''}${P.heldout_spark && P.heldout_spark.groups ? heldoutSparkHTML(P.heldout_spark) : ''}
    ${P.check_all && P.check_all.n ? `<div class="card pad callout" style="margin-top:16px"><div class="row" style="align-items:center;gap:18px;flex-wrap:wrap">
      <div class="big-num">${P.check_all.pct.toFixed(1)}%</div>
      <div class="grow" style="min-width:240px"><b>Best in development: Muse Spark 1.3 checks every verdict</b><p class="small muted" style="margin:4px 0 0">Even when all three agents agree, they are sometimes wrong together. Re-checking agreed verdicts on the agents' own evidence, Spark 1.3 fixed ${P.check_all.fixed} unanimous mistakes and broke ${P.check_all.broken} right answers: ${P.check_all.pct.toFixed(1)}% overall, against ${P.check_all.splits_only.toFixed(1)}% when it only rules on splits, for about $${P.check_all.usd_per_case.toFixed(3)} per case. Measured on ${P.check_all.triples} of the 5 investigator sets (${P.check_all.n.toLocaleString()} runs). On the held-out shards it was right ${P.heldout_spark && P.heldout_spark.groups ? P.heldout_spark.groups['all held-out'].spark13all[0].toFixed(1) : '81.6'}%, about the same as Muse Glimmer alone (table above).</p></div></div></div>` : ''}
    ${P.trust && P.trust.modes ? trustSectionHTML(P) : ''}
    <div class="card pad" style="margin-top:16px"><div class="row" style="align-items:baseline"><h2 class="h2 grow" style="font-size:24px">Accuracy by domain</h2><button class="btn" id="tbl" style="padding:6px 12px">Table view</button></div>
      ${legendHTML(P)}<div id="chart1">${dotPlot(rows, P, 50, 90)}</div>
      <div class="small muted">Each dot is one setup; hover a dot for its value. The number is the row's best setup. Spark 1.3 checking every verdict (82.0%) was measured on 4 of the 5 investigator sets, so it is shown above rather than here. Muse Spark Open as the adjudicator is the best setup, or tied for it, in ${P.by_domain.filter((d) => SERIES.every((s) => d.spark >= d[s])).length} of ${P.by_domain.length} domains.</div></div>
    <div class="card pad" style="margin-top:16px"><h2 class="h2" style="font-size:24px">Where the gain comes from</h2>
      <p class="small muted" style="margin:6px 0 10px">When the three agents agree (${Math.round(100 * k.agree.n / (k.agree.n + k.split.n))}% of runs) these five setups keep the agreed verdict, so all their gain is on the splits. Re-checking agreed verdicts too is what lifts Spark 1.3 to 82% in development (above); on the held-out shards that re-check fixed 16 agreed verdicts and broke 15, so it added no accuracy there.</p>
      ${legendHTML(P)}<div id="chart2">${dotPlot([{ label: `Agents agree`, ...k.agree }, { label: `Agents split`, ...k.split }], P, 50, 90)}</div></div>
    <div class="card" style="margin-top:16px;display:none" id="tblcard"><div class="tablewrap"><table class="t"><tr><th>Group</th><th class="num">Cases</th>${SERIES.map((s) => `<th class="num">${esc(P.labels[s])}</th>`).join('')}</tr>
      ${rows.map((r) => `<tr${r.bold ? ' class="hl"' : ''}><td>${esc(r.label)}</td><td class="num">${r.n || 220}</td>${SERIES.map((s) => `<td class="num">${r[s]}%</td>`).join('')}</tr>`).join('')}
      ${['agree', 'split'].map((kk) => `<tr><td>Agents ${kk}</td><td class="num">${k[kk].n} runs</td>${SERIES.map((s) => `<td class="num">${k[kk][s]}%</td>`).join('')}</tr>`).join('')}</table></div></div>
    <p class="small muted" style="margin-top:14px">The charts use the development shards (3-4). The held-out card above uses shards 5-6 (316 contests never used for any choice); the Spark modes were not run on held-out data.</p>`;
  $('#tbl').onclick = () => { const c = $('#tblcard'); c.style.display = c.style.display === 'none' ? 'block' : 'none'; };
  S.redrawProof = () => {                                     // redraw at the new width (phone rotation, window resize)
    if (!$('#chart1')) return;
    $('#chart1').innerHTML = dotPlot(rows, P, 50, 90);
    $('#chart2').innerHTML = dotPlot([{ label: `Agents agree`, ...k.agree }, { label: `Agents split`, ...k.split }], P, 50, 90);
  };
}
let resizeTimer = null, lastW = window.innerWidth;
window.addEventListener('resize', () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => {
    if (S.redrawProof) S.redrawProof();
    if (window.innerWidth !== lastW && S.mapResize) S.mapResize();     // the search maps (not on a phone's toolbar scroll)
    lastW = window.innerWidth;
  }, 200);
});

// ------------------------------------------------------------------ how it works
async function howPage() {
  $('#app').innerHTML = `<div class="h3">How it works</div><h1 class="display" style="font-size:clamp(34px,4vw,52px);margin:8px 0 12px">Cheap agents search. The vote shows when to look harder.</h1>
    <p class="lede">Every number below comes from the 220 development cases (two-hop questions over long videos; one answer is the original, the other was edited to contain wrong details), with five independent sets of three investigators.</p>
    <div class="card flow" style="margin:24px 0">${FLOW}</div>
    <div class="how-grid">
      <div class="card pad"><div class="big-num">79.6% vs 57.8%</div><h3>Agreement is a free confidence signal</h3><p>When the three investigators agree (three cases in four), they are right 79.6% of the time. When they split, the majority is right only 57.8%, close to a coin flip. So extra effort goes exactly where the agents are unreliable.</p></div>
      <div class="card pad"><div class="big-num">285k tokens</div><h3>The investigators do the expensive part</h3><p>Finding the right moments in about 100 hours of footage takes each agent around eight turns and 285,000 tokens, on Muse Glimmer at no API cost. In a split, at least one agent has usually found the decisive moment: the minority was right in 42% of split cases.</p></div>
      <div class="card pad"><div class="big-num">61% → 23%</div><h3>The adjudicator sees evidence, not votes</h3><p>Shown the agents' reports, an adjudicator sided with a wrong majority 61% of the time. Shown only their looks, Glimmer did so 43% of the time and Spark Open 23%. Hiding the votes removes peer pressure; a stronger model removes shared blind spots.</p></div>
      <div class="card pad"><div class="big-num">No API cost by default</div><h3>Open weights first, stronger on demand</h3><p>By default everything runs on Muse Glimmer, open weights deployed on Modal and Fireworks, so the footage never leaves that deployment. Splits can escalate to Muse Spark 1.3 on the Meta Model API (78.8% for about $0.001 per case; the Contributor tier may train on what is sent) or to Muse Spark Open on Baseten (80.5%, about $0.017 per case, 11 times cheaper than letting it investigate alone).</p></div>
    </div>
    <div class="card" style="margin-top:16px"><div class="pad" style="padding-bottom:6px"><div class="h3">Development results</div></div><div class="tablewrap"><table class="t">
      <tr><th>Setup</th><th class="num">Accuracy</th><th class="num">API cost per case</th></tr>
      <tr><td>One Muse Glimmer investigator</td><td class="num">72.9%</td><td class="num">$0</td></tr>
      <tr><td>Three investigators, majority vote</td><td class="num">74.0%</td><td class="num">$0</td></tr>
      <tr class="hl"><td><b>Three investigators + Muse Glimmer adjudicator</b> (Portia's default)</td><td class="num">75.2%</td><td class="num">$0</td></tr>
      <tr class="hl"><td><b>Three investigators + Muse Spark 1.3 Contributor adjudicator</b> (Meta Model API)</td><td class="num">78.8%</td><td class="num">$0.001</td></tr>
      <tr class="hl"><td><b>Three investigators + Muse Spark Open adjudicator</b> (Baseten)</td><td class="num">80.5%</td><td class="num">$0.017</td></tr>
      <tr class="hl"><td><b>Three investigators + Muse Spark 1.3 checks every verdict</b> (Meta Model API; 4 of the 5 investigator sets)</td><td class="num"><b>82.0%</b></td><td class="num">$0.004</td></tr>
      <tr><td>Muse Spark Open doing the whole investigation</td><td class="num">untested at scale</td><td class="num">$0.185</td></tr></table></div>
      <div class="pad small muted" style="padding-top:8px">Development shards (220 cases × 5 investigator sets). On development the Glimmer adjudicator's gain over the vote is small and did not hold on every investigator set; on the held-out shards 5-6 (316 contests, pre-registered), Portia on Muse Glimmer alone was right 81.0% against 75.3% for the vote; run once on the same contests (audit 022), Muse Spark 1.3 was right 81.3% on splits and 81.6% checking every verdict, about the same (Proof page).</div></div>
    <div class="card pad" style="margin-top:16px"><div class="h3">The Meta stack</div>
      <div class="tablewrap" style="margin-top:8px"><table class="t"><tr><th>Meta model</th><th>What it does in Portia</th><th>Measured (development set)</th></tr>
        <tr><td><b>Muse Glimmer 30B</b><br><span class="small muted">open weights; deployed on a Modal Endpoint and on Fireworks, both tested with the same investigations</span></td><td>The three investigators: search, contact sheets, zoom, up to 8 turns each. Also the default adjudicator.</td><td>72.9% for one agent, 75.2% as a jury, no API cost per case.</td></tr>
        <tr><td><b>Muse Spark 1.3</b><br><span class="small muted">Meta Model API</span></td><td>Re-checks every verdict on the investigators' own evidence, agreed verdicts included.</td><td>82.0% right in development (fixed 59 unanimous mistakes, broke 29; 880 runs); 81.6% on the held-out shards, where it fixed 16 and broke 15; about $0.004 per case.</td></tr>
        <tr><td><b>Muse Spark Open</b><br><span class="small muted">open weights, hosted on Baseten</span></td><td>Adjudicates the cases where the investigators split.</td><td>80.5% right, $0.017 per case: 11× cheaper than letting it investigate alone ($0.185).</td></tr>
        <tr><td><b>Perception Encoder (PE-Core)</b><br><span class="small muted">Meta FAIR</span></td><td>Tested as a Meta-only search index, with Muse Glimmer writing the scene queries.</td><td>Found the evidence in the top 8 for 57.7% of cases against 78.2% for the current index, so not used yet.</td></tr>
      </table></div></div>
    <div class="card pad" style="margin-top:16px"><div class="h3">Built during the hackathon</div>
      <ul class="built">
        <li><b>The long-video tools and the multi-turn agent:</b> searching hours of footage or one video, reading and grepping transcripts, frames, contact sheets, zoom and bursts, used turn by turn by each investigator, so every verdict can cite the moments it rests on.</li>
        <li><b>Muse Glimmer 30B deployed on a Modal Endpoint and on Fireworks</b> (both tested with the same two investigations, both right), and an agent tuned for it (reasoning kept across tool turns, a turns-left note, a full-strength final answer): 67.0% → 76.6% on the tuning shard.</li>
        <li><b>The jury:</b> three independent investigators, the agreement signal, and an evidence-only adjudicator that re-checks disputed details on the investigators' looks without seeing their votes.</li>
        <li><b>Muse Spark Open as the adjudicator</b> (Baseten): +6.5 points over the vote on all five investigator sets; measured to be 11× cheaper than letting Spark Open investigate alone.</li>
        <li><b>Muse Spark 1.3 as the adjudicator</b> (Meta Model API): +4.8 points over the vote on all five investigator sets, at about $0.004 per split.</li>
        <li><b>Spark 1.3 re-checks agreed verdicts:</b> all three agents are sometimes wrong together (15% of cases). Spark 1.3 fixed 59 of these and broke 29 right answers over 880 development runs, which lifts Portia to 82.0% there, for about $0.004 per case. On the held-out shards it fixed 16 and broke 15, so the re-check of agreed verdicts added no accuracy there (81.6% against 81.0% for Muse Glimmer alone).</li>
        <li><b>Trust tiers:</b> every verdict says how far to trust it, from the measured accuracy of the path that produced it; History filters what needs review.</li>
        <li><b>Batch audits and an API:</b> upload an eval run as CSV/JSON lines, get verdicts, tiers and costs back as CSV or JSON.</li>
        <li><b>Check one answer:</b> paste a single AI answer; Muse Glimmer writes a variant with 2 or 3 checkable details changed, and the jury rules which one the footage supports.</li>
        <li><b>This app:</b> live streaming of every agent turn and frame, the verdict with the evidence it cites, cinematic replay, the proof page, history.</li>
      </ul>
      <p class="small muted" style="margin:10px 0 0">Before the hackathon: only the video database of our playlist-eval paper (videos, questions, answer keys) and its segment index. That index is the one non-Meta model in Portia: Qwen3-VL-Embedding-8B vectors. A Meta-only index (Perception Encoder on keyframes, with Muse Glimmer writing the scene queries) found the evidence clearly less often (57.7% against 78.2% in the top 8), so we kept it.</p></div>
    <div class="card pad" style="margin-top:16px"><div class="h3">What we tried that did not help (measured, development set)</div>
      <ul class="built">
        <li><b>Handing Glimmer the right evidence:</b> given the ground-truth frames, it is no more accurate than the agent that searches for them (71% vs 73%). Its limit is reading fine detail, which is why escalating splits to Muse Spark Open is the step up.</li>
        <li><b>An adjudicator that reads the agents' reports:</b> it followed a wrong majority 61% of the time. Hiding the verdicts (evidence only) is the design we kept.</li>
        <li><b>More Glimmer votes on a split</b> (five or seven agents): 60% right on splits, against 63% for the adjudicator.</li>
        <li><b>Asking the Glimmer adjudicator three times:</b> no gain; its mistakes are systematic, not random.</li>
        <li><b>Letting the adjudicator search:</b> it found evidence the investigators missed in 12% of splits, but its verdicts were no more accurate.</li>
        <li><b>Making the adjudicator describe every frame before it compares:</b> no gain.</li>
        <li><b>30 turns instead of 8</b> and <b>higher-resolution zooms:</b> no gain beyond the tuning shard.</li>
      </ul></div>
    <p class="small muted" style="margin-top:14px">Why "Portia": in Shakespeare's <i>The Merchant of Venice</i>, Portia wins the trial on one exact detail of the bond. Here too, every verdict turns on a detail the footage shows.</p>`;
}

route();
