"""ui/polish.py
Performance mode, mobile layout, readability masking for the 3D scene, and a shared
data-refresh helper.

Public API
    perf_enabled() -> bool                 is the sidebar's Performance mode switched on?
    inject_polish_css(perf=False)          mobile rules, scene masking, lighter visuals when perf is on
    disable_3d_background()                tear down the globe and stop the typing animation
    refresh_data()                         drop cached market data and retry-timers (used by Retry buttons)
"""
import uuid

import streamlit as st

from ui.inject import inject_html

_MOBILE_CSS = """
@media (max-width: 640px) {
  .block-container { padding: .8rem .75rem 6rem !important; }
  .stApp .hero .hero-sub { font-size: .92rem; }
  .tape-item { padding: 0 .9rem; font-size: .76rem; }
  [data-testid="stChatMessage"] { padding: .75rem .65rem; }
  .sm { padding: .9rem; }
  .sm-name { font-size: 1.12rem; }
  .sm-px { text-align: left; flex-basis: 100%; }
  .sm-price { font-size: 1.45rem; }
  .sm-stats { grid-template-columns: repeat(2, 1fr); }
  .rm-grid { grid-template-columns: repeat(2, 1fr); }
  .rm-v { font-size: 1.05rem; }
  .land-title { font-size: 1.1rem; }
  .sc-big { font-size: 1.7rem; }
}
"""

# Keep the 3D scene a backdrop: the canvas is brightest at the left and right edges and
# softer behind the centre column where the text sits. Once a report or comparison is open
# it is softer still, and the globe itself drifts to the right edge (see ui/background.py).
# Tune the 0.6 / 0.3 stops (lower = dimmer behind the text), or delete the block to disable.
_SCENE_CSS = """
#fin-bg-canvas {
  -webkit-mask-image: linear-gradient(90deg, #000 0%, rgba(0,0,0,.6) 24%, rgba(0,0,0,.6) 66%, #000 92%);
  mask-image: linear-gradient(90deg, #000 0%, rgba(0,0,0,.6) 24%, rgba(0,0,0,.6) 66%, #000 92%);
}
body:has([data-testid="stChatMessage"]) #fin-bg-canvas,
body:has(.cp-heads) #fin-bg-canvas {
  opacity: .85 !important;
  -webkit-mask-image: linear-gradient(90deg, #000 0%, rgba(0,0,0,.3) 26%, rgba(0,0,0,.3) 68%, #000 92%);
  mask-image: linear-gradient(90deg, #000 0%, rgba(0,0,0,.3) 26%, rgba(0,0,0,.3) 68%, #000 92%);
}
body:has([data-testid="stChatMessage"]) #fin-bg-hud,
body:has(.cp-heads) #fin-bg-hud { opacity: .6 !important; }
@media (max-width: 760px) {
  #fin-bg-canvas,
  body:has([data-testid="stChatMessage"]) #fin-bg-canvas,
  body:has(.cp-heads) #fin-bg-canvas {
    -webkit-mask-image: none;
    mask-image: none;
    opacity: .4 !important;
  }
}
"""

# Blur, endless and decorative animations are the expensive parts of the theme.
_PERF_CSS = """
*, *::before, *::after { backdrop-filter: none !important; -webkit-backdrop-filter: none !important; }
.tape-track, .pulse-dot, .gradient-text { animation: none !important; }
.sm::after { animation: none !important; display: none; }
[data-testid="stChatMessage"], .sm, .sm-st, .tape { animation: none !important; }
"""

_DISABLE_JS = """
<script>
(function () {
  var P = window.parent;
  if (!P) return;
  try { if (P.__finBg && P.__finBg.destroy) P.__finBg.destroy(); } catch (e) {}
  P.__finBg = null;
  P.__finBgLoading = 0;
  P.__finTyperPhrases = [];
  var D = P.document;
  ['fin-bg-canvas', 'fin-bg-hud', 'fin-bg-tag'].forEach(function (id) {
    var el = D.getElementById(id);
    if (el) el.remove();
  });
  var box = D.querySelector('textarea[data-testid="stChatInputTextArea"]') ||
            D.querySelector('[data-testid="stChatInput"] textarea');
  if (box) box.placeholder = "Ask about a stock (e.g., 'Is Nvidia a good buy right now?')";
})();
/*__NONCE__*/
</script>
"""


def perf_enabled() -> bool:
    return bool(st.session_state.get("perf_mode", False))


def inject_polish_css(perf: bool = False) -> None:
    css = _MOBILE_CSS + _SCENE_CSS + (_PERF_CSS if perf else "")
    # strip indentation + blank lines so Streamlit's markdown parser never treats it as code
    compact = "\n".join(line.strip() for line in css.splitlines() if line.strip())
    st.markdown(f"<style>{compact}</style>", unsafe_allow_html=True)


def disable_3d_background() -> None:
    """Remove the globe + HUD and stop the typing animation (used in Performance mode)."""
    inject_html(_DISABLE_JS.replace("__NONCE__", uuid.uuid4().hex))


def refresh_data() -> None:
    """Drop cached market data and any 'retry later' timers (works as a button callback)."""
    st.cache_data.clear()
    for k in [k for k in st.session_state if k.startswith("_retry") or k.endswith("_retry_at")]:
        del st.session_state[k]