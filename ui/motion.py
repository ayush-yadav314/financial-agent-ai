"""ui/motion.py
Small motion helpers that run in the browser.

Public API:
    scroll_to_latest()                  smoothly scrolls the newest chat message into view
    animate_chat_placeholder(phrases)   typewriter animation in the chat box placeholder
"""
from ui.inject import inject_html as _inject
import json
import uuid

import streamlit as st
import streamlit.components.v1 as components


_SCROLL_JS = """
<script>
(function () {
  var P = window.parent;
  var reduce = false;
  try { reduce = P.matchMedia('(prefers-reduced-motion: reduce)').matches; } catch (e) {}
  setTimeout(function () {
    try {
      var msgs = P.document.querySelectorAll('[data-testid="stChatMessage"]');
      if (!msgs.length) return;
      msgs[msgs.length - 1].scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'start' });
    } catch (e) {}
  }, 350);
})();
/*__NONCE__*/
</script>
"""

# Runs inside the MAIN page (not the iframe), so its timers survive Streamlit reruns.
_TYPER_JS = r"""
(function () {
  if (window.__finTyper) return;
  var D = document;
  var reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var st = { i: 0, j: 0, del: false };
  window.__finTyper = st;

  function box() {
    return D.querySelector('textarea[data-testid="stChatInputTextArea"]') ||
           D.querySelector('[data-testid="stChatInput"] textarea');
  }

  function step() {
    var list = window.__finTyperPhrases || [];
    var el = box();
    // pause while: no box yet, reduced motion, user is typing/focused, or tab hidden
    if (!list.length || !el || reduce || el.value !== '' || D.activeElement === el || D.hidden) {
      setTimeout(step, 500);
      return;
    }
    var text = list[st.i % list.length];
    var delay = 60;
    if (!st.del) {
      st.j++;
      el.placeholder = text.slice(0, st.j) + '\u258C';
      if (st.j >= text.length) { st.del = true; el.placeholder = text; delay = 1900; }
      else { delay = 50 + Math.random() * 40; }
    } else {
      st.j = Math.max(0, st.j - 2);
      el.placeholder = (st.j ? text.slice(0, st.j) : '') + '\u258C';
      if (st.j === 0) { st.del = false; st.i++; delay = 380; }
      else { delay = 22; }
    }
    setTimeout(step, delay);
  }
  step();
})();
"""

_TYPER_LOADER = """
<script>
(function () {
  var P = window.parent;
  if (!P) return;
  P.__finTyperPhrases = __PHRASES__;
  if (P.__finTyper) return;
  var D = P.document;
  var s = D.createElement('script');
  s.id = 'fin-typer-script';
  s.textContent = __SRC__;
  D.head.appendChild(s);
})();
</script>
"""


  # fallback for Streamlit versions without components.html


def scroll_to_latest() -> None:
    """Smooth-scroll to the newest chat message. Call right after rendering a fresh answer."""
    # unique nonce so Streamlit never reuses an identical iframe (which would skip the script)
    _inject(_SCROLL_JS.replace("__NONCE__", uuid.uuid4().hex))


def animate_chat_placeholder(phrases: list) -> None:
    """Type and erase example questions in the chat box placeholder.
    Safe to call on every rerun: the animation starts once and just picks up new phrases."""
    html = (
        _TYPER_LOADER
        .replace("__PHRASES__", json.dumps(list(phrases)))
        .replace("__SRC__", json.dumps(_TYPER_JS))
    )
    _inject(html)