"""Init script shared by capture.py and probe.py: manual rAF clock and skip-intro flags."""
INIT = """
(() => { let a = (window.__SEED || 1337) >>> 0;   // seeded Math.random: the same map and the same takes on every run
  Math.random = () => { a = (a + 0x6D2B79F5) >>> 0; let t = a; t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; })();
localStorage.setItem('pe_tutorial_done','1'); localStorage.setItem('pe_intro_seen','1');
localStorage.setItem('pe_tut_voice','off');
window.__rafQ = []; window.__ts = 1000;
window.requestAnimationFrame = cb => { window.__rafQ.push(cb); return window.__rafQ.length; };
window.cancelAnimationFrame = () => {};
window.__step = (n, dtms) => { for (let i = 0; i < n; i++) { window.__ts += dtms; const q = window.__rafQ; window.__rafQ = [];
  q.forEach(c => { try { c(window.__ts) } catch (e) { console.error('raf', e) } }); } };
"""
