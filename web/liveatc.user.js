// ==UserScript==
// @name         livescope: play the frequency on LiveATC
// @namespace    https://livescope.kyleboas.com
// @version      1.0
// @description  Clicking a frequency in livescope's airport card opens LiveATC's page for the airport with #livescope=<MHz>; this plays the feed that carries that frequency, on LiveATC's own page.
// @match        https://www.liveatc.net/search/*
// @grant        none
// @run-at       document-end
// ==/UserScript==
(() => {
  'use strict';
  if (/just a moment/i.test(document.title)) return;            // Cloudflare's check: the real page comes next
  // the airport's feeds, in page order: each listen link's table, then its "Facility | Frequency" table
  function feeds() {
    const out = [];
    document.querySelectorAll('a[onclick*="myHTML5Popup"]').forEach(a => {
      const m = /myHTML5Popup\('([^']+)'/.exec(a.getAttribute('onclick')), t = a.closest('table');
      if (!m || !t) return;
      const name = (t.querySelector('td[bgcolor] strong') || {}).textContent || m[1];
      const st = t.textContent, up = /Feed Status:\s*UP/i.test(st), ls = +((/Listeners:\s*(\d+)/i.exec(st) || [])[1] || 0);
      let n = t.nextElementSibling;
      while (n && !(n.matches('table') && (n.classList.contains('freqTable') || n.querySelector('a[onclick*="myHTML5Popup"]')))) n = n.nextElementSibling;
      const fq = n && n.classList.contains('freqTable') ? [...n.querySelectorAll('td b')].map(b => parseFloat(b.textContent)).filter(f => f > 100) : [];
      out.push({ mount: m[1], name: name.trim(), up, ls, fq, el: t });
    });
    return out;
  }
  let bar = null, audio = null;
  function show(html) {
    if (!bar) {
      bar = document.createElement('div');
      bar.style.cssText = 'position:fixed;top:0;left:0;right:0;z-index:2147483647;background:#111;color:#eee;font:14px/1.4 -apple-system,system-ui,sans-serif;padding:8px 12px;display:flex;gap:12px;align-items:center;box-shadow:0 2px 8px #0008';
      document.body.appendChild(bar);
      document.body.style.marginTop = '56px';
    }
    bar.innerHTML = html;
    return bar;
  }
  function stop() { if (audio) { audio.pause(); audio.removeAttribute('src'); audio.load(); audio = null; } }
  function go() {
    const h = /[#&]livescope=([\d.]+)/.exec(location.hash);
    if (!h) return;
    const want = parseFloat(h[1]), mhz = want.toFixed(3);
    const hits = feeds().filter(f => f.fq.some(x => Math.abs(x - want) < 0.003));
    // a feed that's up first, then the one with fewest other frequencies on it, then the most listened to
    hits.sort((a, b) => (b.up - a.up) || (a.fq.length - b.fq.length) || (b.ls - a.ls));
    stop();
    document.querySelectorAll('[data-livescope]').forEach(e => { e.style.outline = ''; e.removeAttribute('data-livescope'); });
    const f = hits[0];
    if (!f) { show(`<b>${mhz}</b>&nbsp;No LiveATC feed for this airport lists this frequency.`); return; }
    f.el.setAttribute('data-livescope', ''); f.el.style.outline = '2px solid #3a8ee6'; f.el.scrollIntoView({ block: 'center' });
    const b = show(`<b>${mhz}</b><span>${f.name.replace(/</g, '&lt;')}${f.up ? '' : ' (feed down)'}${f.fq.length > 1 ? ` · also ${f.fq.filter(x => Math.abs(x - want) >= 0.003).map(x => x.toFixed(3)).join(', ')}` : ''}</span><audio controls style="height:32px"></audio><span class="ls-note" style="color:#f90"></span>`);
    audio = b.querySelector('audio');
    audio.src = 'https://d.liveatc.net/' + encodeURIComponent(f.mount);
    audio.play().catch(() => {
      b.querySelector('.ls-note').textContent = 'Press ▶ to start. To skip this: Safari ▸ Settings for www.liveatc.net ▸ Auto-Play ▸ Allow All Auto-Play.';
    });
    audio.onplaying = () => { b.querySelector('.ls-note').textContent = ''; };
  }
  window.addEventListener('hashchange', go);
  go();
})();
