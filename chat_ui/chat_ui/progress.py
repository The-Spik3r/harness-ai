"""The pending entry's word, and the browser-side tick that shows it (PRD-021 STORY-012).

`progress_word` is pure: `(stage, phase, action)` in, one English word out, every
string from `copy.py` (T4). `PROGRESS_TICK_JS` is the script that owns the
elapsed-seconds counter and the 300 ms no-flicker rule in the browser, so the
server sends no per-second deltas (D19: the only server updates are STORY-011's
100 ms batches). No Reflex import and no I/O, as `live_batch.py`.

The epoch values the state carries (`progress_sent_at`, `progress_since`) are
used as *change keys*: a new key resets the client clock, which is read with
`performance.now()` from the first tick that saw the key. Subtracting a server
epoch from the browser's `Date.now()` would be wrong under client clock skew.
"""

import json

from .copy import (
    PROGRESS_ELAPSED_TEMPLATE,
    PROGRESS_KIND_FALLBACK,
    PROGRESS_KIND_WORDS,
    PROGRESS_PHASE_WORDS,
    PROGRESS_PREPARING_TEMPLATE,
    PROGRESS_SEPARATOR,
    PROGRESS_STAGE_WORDS,
)

# A stage the reader should see even while the model phase is still set: these
# run after the model, so the phase word would be stale.
_LATE_STAGES = ("evaluating_actions", "masking_output")

# PRD-021 7.1: a word is shown only if its stage is still current this long
# after it started.
WORD_HOLD_MS = 300


def progress_word(stage: str, phase: str, action: str) -> str:
    """The one word the pending entry shows.

    A late stage wins when set; otherwise the model phase if one is set;
    otherwise the stage word; otherwise `waiting`. `action` is the closed
    `OperationKind` of a `preparing_action` phase; anything else becomes the
    fallback, so a model's raw tool name can never reach the screen.
    """
    if stage in _LATE_STAGES and stage in PROGRESS_STAGE_WORDS:
        return PROGRESS_STAGE_WORDS[stage]
    if phase == "preparing_action":
        return PROGRESS_PREPARING_TEMPLATE.format(
            kind=PROGRESS_KIND_WORDS.get(action, PROGRESS_KIND_FALLBACK)
        )
    if phase in PROGRESS_PHASE_WORDS:
        return PROGRESS_PHASE_WORDS[phase]
    if stage in PROGRESS_STAGE_WORDS:
        return PROGRESS_STAGE_WORDS[stage]
    return PROGRESS_PHASE_WORDS["waiting"]


# `hxProgressTick(nowMs, root)`: a no-op without the pending entry. Reads the
# wrapper's `data-sent-at` / `data-since` / `data-word`, writes the word span's
# and the seconds span's `textContent`. React never re-renders those two spans'
# children, so the script's text is not overwritten.
PROGRESS_TICK_JS = (
    """
var hxProgressElapsed = %(elapsed)s;
var hxProgressSep = %(sep)s;
var hxProgressHoldMs = %(hold)d;
var hxProgressState = {sent: null, t0: 0, shown: null, key: null, keyAt: 0, secs: -1};
function hxProgressTick(nowMs, root) {
  var st = hxProgressState;
  var el = root.querySelector('[data-hx-progress]');
  if (!el) { st.sent = null; return; }
  var wordEl = el.querySelector('[data-hx-word]');
  var secsEl = el.querySelector('[data-hx-secs]');
  if (!wordEl || !secsEl) { return; }
  var sent = el.getAttribute('data-sent-at');
  if (sent !== st.sent) {
    st.sent = sent; st.t0 = nowMs; st.secs = -1; st.key = null;
    st.shown = wordEl.textContent;
  }
  var target = el.getAttribute('data-word');
  if (target && target !== st.shown) {
    var key = target + '|' + el.getAttribute('data-since');
    if (key !== st.key) { st.key = key; st.keyAt = nowMs; }
    if (nowMs - st.keyAt >= hxProgressHoldMs) {
      wordEl.textContent = target; st.shown = target; st.key = null;
    }
  } else {
    st.key = null;
  }
  var n = Math.floor((nowMs - st.t0) / 1000);
  if (n !== st.secs) {
    st.secs = n;
    secsEl.textContent = hxProgressSep + hxProgressElapsed.replace('{n}', n);
  }
}
"""
    % {
        "elapsed": json.dumps(PROGRESS_ELAPSED_TEMPLATE),
        "sep": json.dumps(PROGRESS_SEPARATOR),
        "hold": WORD_HOLD_MS,
    }
)
