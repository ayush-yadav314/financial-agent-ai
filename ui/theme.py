"""ui/theme.py
Global design system: tokens, fonts, glass surfaces, motion.
Call inject_theme() once, right after st.set_page_config().

Fonts: Manrope for headings and numbers, Inter for body text.
Look:  dark glass over a faint terminal grid, with cyan / blue / violet accents.
Motion is tasteful and switched off entirely when the user prefers reduced motion.
"""
import streamlit as st

# ---------------------------------------------------------------
# Design tokens: change a color/font here and the whole app follows
# ---------------------------------------------------------------
TOKENS = {
    "bg": "#080C15",
    "surface": "rgba(255,255,255,0.04)",
    "surface-strong": "rgba(255,255,255,0.07)",
    "glass": "rgba(14,20,34,.62)",
    "glass-strong": "rgba(14,20,34,.80)",
    "border": "rgba(255,255,255,0.08)",
    "border-strong": "rgba(255,255,255,0.15)",
    "text": "#E8ECF4",
    "muted": "#9AA3B8",
    "accent": "#22D3EE",     # cyan
    "accent-2": "#8B5CF6",   # violet
    "accent-3": "#3B82F6",   # electric blue
    "success": "#10B981",
    "danger": "#F43F5E",
    "warning": "#F59E0B",
    "radius": "16px",
    "font-display": "'Manrope', 'Inter', sans-serif",
    "font-body": "'Inter', sans-serif",
}

_FONTS = (
    "@import url('https://fonts.googleapis.com/css2?"
    "family=Inter:wght@400;500;600;700&"
    "family=Manrope:wght@500;600;700;800&display=swap');"
)

_BASE_CSS = """
/* ---------- Base: faint terminal grid + soft cyan / violet / blue light ---------- */
html {
    background:
        linear-gradient(rgba(148,163,184,.035) 1px, transparent 1px) 0 0 / 56px 56px,
        linear-gradient(90deg, rgba(148,163,184,.035) 1px, transparent 1px) 0 0 / 56px 56px,
        radial-gradient(1200px 600px at 10% -10%, rgba(139,92,246,.17), transparent 60%),
        radial-gradient(900px 500px at 95% 0%, rgba(34,211,238,.12), transparent 55%),
        radial-gradient(800px 600px at 50% 112%, rgba(59,130,246,.09), transparent 60%),
        var(--bg);
    background-attachment: fixed;
    min-height: 100%;
}
body { background: transparent !important; }
.stApp,
[data-testid="stAppViewContainer"],
[data-testid="stMain"],
[data-testid="stBottom"],
[data-testid="stBottomBlockContainer"] {
    background: transparent !important;
}
.stApp {
    color: var(--text);
    font-family: var(--font-body);
    -webkit-font-smoothing: antialiased;
    text-rendering: optimizeLegibility;
}
.stApp :is(p, li, label, input, textarea, button, select, a, td, th, summary, small) { font-family: var(--font-body); }
.stApp :is(h1, h2, h3, h4, h5, h6) {
    font-family: var(--font-display) !important;
    font-weight: 700;
    letter-spacing: -0.02em;
}
[data-testid="stMarkdownContainer"] p { line-height: 1.65; }
[data-testid="stHeader"] { background: transparent; }
.block-container { padding-top: 1.6rem; max-width: 1180px; }
::selection { background: rgba(34,211,238,.3); }

/* ---------- Zero-height script iframes (3D scene injectors) must not take up layout space ---------- */
[data-testid="stElementContainer"]:has(iframe[height="0"]),
.element-container:has(iframe[height="0"]) {
    position: absolute;
    width: 0;
    height: 0;
    margin: 0;
    overflow: hidden;
}

/* ---------- Scrollbar ---------- */
::-webkit-scrollbar { width: 10px; height: 10px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: rgba(255,255,255,.12); border-radius: 10px; }
::-webkit-scrollbar-thumb:hover { background: rgba(34,211,238,.4); }

/* ---------- Divider ---------- */
.stApp hr {
    border: none;
    height: 1px;
    background: linear-gradient(90deg, transparent, var(--border-strong), transparent);
}

/* ---------- Sidebar ---------- */
[data-testid="stSidebar"] {
    background: rgba(9,13,24,.84);
    backdrop-filter: blur(16px);
    -webkit-backdrop-filter: blur(16px);
    border-right: 1px solid var(--border);
}

/* ---------- Chat messages (dark glass; no blur on these: they can be very tall) ---------- */
[data-testid="stChatMessage"] {
    background: rgba(12,17,29,.66);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 1rem 1.1rem;
    margin-bottom: .7rem;
    box-shadow: 0 14px 44px -28px rgba(0,0,0,.9), inset 0 1px 0 rgba(255,255,255,.04);
    animation: fadeUp .45s cubic-bezier(.2,.8,.2,1) both;
}
[data-testid="stChatMessageAvatarUser"] {
    background: rgba(255,255,255,.08) !important;
    color: var(--text) !important;
}
[data-testid="stChatMessageAvatarAssistant"] {
    background: linear-gradient(135deg, rgba(34,211,238,.28), rgba(139,92,246,.28)) !important;
    color: #fff !important;
}

/* ---------- Buttons ---------- */
.stButton > button, .stDownloadButton > button {
    border-radius: 10px;
    border: 1px solid var(--border-strong);
    background: rgba(255,255,255,.045);
    color: var(--text);
    font-weight: 500;
    transition: transform .18s ease, border-color .18s ease, background .18s ease, box-shadow .18s ease;
}
.stButton > button:hover, .stDownloadButton > button:hover {
    transform: translateY(-1px);
    border-color: var(--accent);
    background: linear-gradient(135deg, rgba(139,92,246,.18), rgba(34,211,238,.14));
    box-shadow: 0 8px 22px -12px rgba(34,211,238,.6);
    color: #fff;
}
.stButton > button:active, .stDownloadButton > button:active { transform: translateY(0) scale(.99); }

/* ---------- Inputs ---------- */
[data-testid="stChatInput"] {
    border-radius: 16px;
    border: 1px solid var(--border-strong);
    background: var(--surface-strong);
    transition: border-color .2s ease, box-shadow .2s ease;
}
[data-testid="stChatInput"]:focus-within {
    border-color: var(--accent);
    box-shadow: 0 0 0 3px rgba(34,211,238,.12), 0 0 26px -8px rgba(34,211,238,.45);
}
[data-testid="stTextInput"] input { border-radius: 10px; transition: box-shadow .2s ease, border-color .2s ease; }
[data-testid="stTextInput"] input:focus {
    border-color: var(--accent);
    box-shadow: 0 0 0 1px var(--accent), 0 0 18px -6px rgba(34,211,238,.5);
}

/* ---------- Radio buttons as pills (chart type / range) ---------- */
[data-testid="stRadio"] [role="radiogroup"] { gap: .4rem; flex-wrap: wrap; }
[data-testid="stRadio"] label {
    padding: .2rem .8rem;
    border: 1px solid var(--border);
    border-radius: 999px;
    background: var(--surface);
    transition: border-color .18s ease, background .18s ease, transform .18s ease;
}
[data-testid="stRadio"] label:hover { border-color: rgba(34,211,238,.5); transform: translateY(-1px); }
[data-testid="stRadio"] label:has(input:checked) {
    border-color: var(--accent);
    background: rgba(34,211,238,.14);
}
[data-testid="stRadio"] label > div:first-child { display: none; }

/* ---------- Expanders (collapsible report sections) ---------- */
[data-testid="stExpander"] {
    border: 1px solid var(--border);
    border-radius: 12px;
    background: rgba(12,17,29,.62);
    backdrop-filter: blur(10px);
    -webkit-backdrop-filter: blur(10px);
    margin: .4rem 0;
    overflow: hidden;
    transition: border-color .2s ease, box-shadow .2s ease;
}
[data-testid="stExpander"]:hover { border-color: rgba(34,211,238,.35); box-shadow: 0 10px 28px -20px rgba(34,211,238,.5); }
[data-testid="stExpander"] summary { padding: .65rem .95rem; }
[data-testid="stExpander"] summary:hover { background: rgba(34,211,238,.05); }
[data-testid="stExpander"] summary p { font-weight: 600; font-size: .95rem; }
[data-testid="stExpander"] details[open] > summary { border-bottom: 1px solid var(--border); }
[data-testid="stExpanderDetails"] { padding: .9rem 1rem 1rem; }

/* ---------- Hero ---------- */
.hero { display: flex; flex-direction: column; align-items: center; text-align: center; width: 100%; padding: 1.8rem 0 .9rem; animation: fadeUp .7s cubic-bezier(.2,.8,.2,1) both; }
.hero-eyebrow {
    display: inline-flex; align-items: center; gap: .55rem;
    padding: .3rem .85rem; border-radius: 999px;
    border: 1px solid var(--border-strong); background: var(--glass);
    color: var(--muted); font-size: .7rem; font-weight: 600; letter-spacing: .14em;
}
.pulse-dot {
    width: 8px; height: 8px; border-radius: 50%;
    background: var(--success); box-shadow: 0 0 0 0 rgba(16,185,129,.55);
    animation: pulse 2.2s infinite;
}
.stApp .hero .hero-title {
    display: block; width: 100%; text-align: center;
    font-family: var(--font-display) !important; font-weight: 800; letter-spacing: -0.03em;
    font-size: clamp(2.1rem, 5vw, 3.4rem); line-height: 1.1;
    margin: .9rem 0 .5rem; padding: 0;
}
.gradient-text {
    background: linear-gradient(100deg, var(--accent), var(--accent-3), var(--accent-2), var(--accent));
    background-size: 240% auto;
    -webkit-background-clip: text; background-clip: text;
    -webkit-text-fill-color: transparent;
    animation: gradientShift 9s linear infinite;
}
.stApp .hero .hero-sub { display: block; color: var(--muted); font-size: 1rem; line-height: 1.6; margin: 0 auto 1rem; width: 100%; max-width: 620px; text-align: center; }
.hero-chips { display: flex; flex-wrap: wrap; gap: .45rem; justify-content: center; max-width: 100%; }
.hero-chip {
    padding: .24rem .75rem; border-radius: 999px;
    border: 1px solid var(--border); background: var(--glass);
    color: var(--muted); font-size: .74rem;
    transition: transform .18s ease, border-color .18s ease, color .18s ease;
}
.hero-chip:hover { transform: translateY(-2px); border-color: var(--accent); color: var(--text); }
/* once a conversation or comparison is open, shrink the hero to a slim header (the gradient stays) */
.stApp:has([data-testid="stChatMessage"]) .hero,
.stApp:has(.cp-heads) .hero { padding: .3rem 0 .2rem; }
.stApp:has([data-testid="stChatMessage"]) .hero :is(.hero-sub, .hero-chips, .hero-eyebrow),
.stApp:has(.cp-heads) .hero :is(.hero-sub, .hero-chips, .hero-eyebrow) { display: none; }
.stApp:has([data-testid="stChatMessage"]) .hero .hero-title,
.stApp:has(.cp-heads) .hero .hero-title { font-size: 1.8rem; margin: .2rem 0; }

/* ---------- Agent pipeline tracker (shown while the agents work) ---------- */
.pipe { display: flex; align-items: flex-start; justify-content: space-between; gap: .2rem; padding: .6rem .2rem .2rem; }
.pipe-node { flex: 0 0 auto; width: 150px; text-align: center; }
.pipe-icon { width: 46px; height: 46px; margin: 0 auto .5rem; border-radius: 50%; display: grid; place-items: center; font-size: 1.15rem; background: var(--surface-strong); border: 1px solid var(--border-strong); color: var(--muted); transition: all .35s ease; }
.pipe-title { font-weight: 600; font-size: .9rem; color: var(--muted); }
.pipe-sub { font-size: .74rem; color: var(--muted); margin-top: .15rem; min-height: 1.1rem; }
.pipe-node.active .pipe-icon { border-color: var(--accent); color: #fff; background: radial-gradient(circle, rgba(34,211,238,.35), rgba(139,92,246,.22)); animation: nodePulse 1.7s ease-in-out infinite; }
.pipe-node.active .pipe-title { color: var(--text); }
.pipe-node.done .pipe-icon { border-color: var(--success); color: var(--success); background: rgba(16,185,129,.14); box-shadow: 0 0 16px -5px var(--success); font-weight: 700; }
.pipe-node.done .pipe-title { color: var(--text); }
.pipe-link { flex: 1 1 auto; height: 2px; margin-top: 22px; min-width: 24px; border-radius: 2px; background: rgba(255,255,255,.1); position: relative; overflow: hidden; }
.pipe-link.done { background: linear-gradient(90deg, var(--success), var(--accent)); }
.pipe-link.active::after { content: ""; position: absolute; inset: 0; background: linear-gradient(90deg, transparent, var(--accent), var(--accent-2), transparent); background-size: 60% 100%; background-repeat: no-repeat; animation: flowDash 1.1s linear infinite; }
.pipe-chip { display: inline-block; margin: .15rem .15rem 0; padding: .1rem .5rem; border-radius: 999px; border: 1px solid var(--border); font-size: .68rem; color: var(--muted); }
.pipe-node.active .pipe-chip { border-color: var(--accent); color: var(--text); animation: chipBlink 1.2s ease-in-out infinite alternate; }
@media (max-width: 700px) { .pipe-node { width: 80px; } .pipe-sub { display: none; } }

/* ---------- Live market tape ---------- */
.tape { position: relative; overflow: hidden; margin: .2rem 0 1rem; padding: .5rem 0; border: 1px solid var(--border); border-radius: 999px; background: var(--glass); backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px); -webkit-mask-image: linear-gradient(90deg, transparent, #000 6%, #000 94%, transparent); mask-image: linear-gradient(90deg, transparent, #000 6%, #000 94%, transparent); animation: fadeUp .6s cubic-bezier(.2,.8,.2,1) both; }
.tape-track { display: flex; width: max-content; animation: tapeScroll 60s linear infinite; }
.tape:hover .tape-track { animation-play-state: paused; }
.tape-item { display: inline-flex; align-items: center; gap: .55rem; padding: 0 1.5rem; font-size: .8rem; white-space: nowrap; }
.tape-item::after { content: "◆"; margin-left: 1.5rem; font-size: .5rem; color: rgba(255,255,255,.16); }
.tape-sym { font-family: var(--font-display); font-weight: 700; letter-spacing: .03em; color: var(--text); }
.tape-px { color: var(--muted); font-variant-numeric: tabular-nums; }
.tape-chg { font-weight: 600; font-variant-numeric: tabular-nums; }
.tape-chg.up { color: var(--success); }
.tape-chg.down { color: var(--danger); }
@media (prefers-reduced-motion: reduce) { .tape { overflow-x: auto; } }

/* ---------- AI report text (the keyed container made by render_report: "rpt_<tone>_<anim|still>_<uid>") ---------- */
[class*="st-key-rpt_"] {
    border-left: 3px solid var(--rc, var(--border-strong));
    padding-left: 1rem;
    box-shadow: -14px 0 34px -26px var(--rc, transparent);
}
[class*="st-key-rpt_bullish_"] { --rc: #10B981; }
[class*="st-key-rpt_neutral_"] { --rc: #F59E0B; }
[class*="st-key-rpt_bearish_"] { --rc: #F43F5E; }
[class*="st-key-rpt_"] h2 {
    position: relative; font-size: 1.08rem !important; line-height: 1.4 !important;
    margin: 1.2rem 0 .5rem; padding: 0 0 .45rem; border-bottom: 1px solid var(--border);
}
[class*="st-key-rpt_"] h2::after {
    content: ""; position: absolute; left: 0; bottom: -1px; height: 2px; width: 56px;
    background: linear-gradient(90deg, var(--rc, var(--accent)), transparent);
}
[class*="st-key-rpt_"] h2:first-child { margin-top: .2rem; }
[class*="st-key-rpt_"] strong { color: #fff; font-weight: 600; }
[class*="st-key-rpt_"] li::marker { color: var(--rc, var(--accent)); }
[class*="st-key-rpt_"] li { margin: .25rem 0; line-height: 1.65; }
[class*="st-key-rpt_"] p { line-height: 1.7; }
[class*="st-key-rpt_"] blockquote {
    border-left: 3px solid var(--rc, var(--accent)); background: var(--surface);
    border-radius: 0 10px 10px 0; padding: .5rem 1rem;
}
/* fresh answers reveal section by section (opacity + movement only, so it stays cheap); replays stay still */
[class*="st-key-rpt_"][class*="_anim_"] [data-testid="stMarkdownContainer"] > :is(h2, p, ul, ol, blockquote, table) {
    animation: fadeUp .6s cubic-bezier(.2,.8,.2,1) both;
    animation-delay: .9s;
}
[class*="st-key-rpt_"][class*="_anim_"] [data-testid="stMarkdownContainer"] > :nth-child(1) { animation-delay: .1s; }
[class*="st-key-rpt_"][class*="_anim_"] [data-testid="stMarkdownContainer"] > :nth-child(2) { animation-delay: .2s; }
[class*="st-key-rpt_"][class*="_anim_"] [data-testid="stMarkdownContainer"] > :nth-child(3) { animation-delay: .3s; }
[class*="st-key-rpt_"][class*="_anim_"] [data-testid="stMarkdownContainer"] > :nth-child(4) { animation-delay: .4s; }
[class*="st-key-rpt_"][class*="_anim_"] [data-testid="stMarkdownContainer"] > :nth-child(5) { animation-delay: .5s; }
[class*="st-key-rpt_"][class*="_anim_"] [data-testid="stMarkdownContainer"] > :nth-child(6) { animation-delay: .6s; }
[class*="st-key-rpt_"][class*="_anim_"] [data-testid="stMarkdownContainer"] > :nth-child(7) { animation-delay: .7s; }
[class*="st-key-rpt_"][class*="_anim_"] [data-testid="stMarkdownContainer"] > :nth-child(8) { animation-delay: .8s; }

/* ---------- Keyframes ---------- */
@keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
@keyframes fadeUp { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
@keyframes gradientShift { to { background-position: 240% center; } }
@keyframes sheen { to { left: 120%; } }
@keyframes tapeScroll { to { transform: translateX(-50%); } }
@keyframes flowDash { from { background-position: -150% 0; } to { background-position: 250% 0; } }
@keyframes chipBlink { from { opacity: .6; } to { opacity: 1; } }
@keyframes needleSwing { from { transform: rotate(-90deg); } }
@keyframes nodePulse { 0%, 100% { box-shadow: 0 0 0 0 rgba(34,211,238,.5); } 50% { box-shadow: 0 0 0 10px rgba(34,211,238,0); } }
@keyframes pulse {
    0% { box-shadow: 0 0 0 0 rgba(16,185,129,.55); }
    70% { box-shadow: 0 0 0 8px rgba(16,185,129,0); }
    100% { box-shadow: 0 0 0 0 rgba(16,185,129,0); }
}

/* ---------- Accessibility: reduced motion switches every animation and transition off ---------- */
@media (prefers-reduced-motion: reduce) {
    *, *::before, *::after { animation: none !important; transition: none !important; }
}
"""


def _compile_css() -> str:
    root = ":root{" + "".join(f"--{k}:{v};" for k, v in TOKENS.items()) + "}"
    css = _FONTS + "\n" + root + "\n" + _BASE_CSS
    # Strip indentation + blank lines so Streamlit's markdown parser
    # never mistakes the CSS block for a code block.
    return "\n".join(line.strip() for line in css.splitlines() if line.strip())


def inject_theme() -> None:
    """Inject the global stylesheet. Call once, right after st.set_page_config()."""
    st.markdown(f"<style>{_compile_css()}</style>", unsafe_allow_html=True)