"""Init script shared by capture.py and probe.py: manual rAF clock and skip-intro flags."""
INIT = """
localStorage.setItem('pe_tutorial_done','1'); localStorage.setItem('pe_intro_seen','1');
localStorage.setItem('pe_tut_voice','off');
window.__rafQ = []; window.__ts = 1000;
window.requestAnimationFrame = cb => { window.__rafQ.push(cb); return window.__rafQ.length; };
window.cancelAnimationFrame = () => {};
window.__step = (n, dtms) => { for (let i = 0; i < n; i++) { window.__ts += dtms; const q = window.__rafQ; window.__rafQ = [];
  q.forEach(c => { try { c(window.__ts) } catch (e) { console.error('raf', e) } }); } };
"""
