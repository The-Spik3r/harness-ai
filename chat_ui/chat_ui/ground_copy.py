"""Wording for the ground toggle — the one control that appears on both surfaces.

A third copy module needs a reason, because the repo already has two and the
boundary between them is deliberate: `copy.py` is the chat's wording,
`admin_copy.py` is the console's, and strings that happen to coincide are
declared twice rather than shared (`SHELL_LOGOUT_LABEL` and `SIGN_OUT_LABEL` are
the same four letters and stay separate, because they end two different
sessions).

The ground toggle is not that. It is *literally the same control* — same effect,
same stored preference — rendered in four places across both surfaces. Declaring
it twice would not be honouring the boundary, it would be claiming a difference
that does not exist, and the two copies would drift the first time one of them
was reworded.

There is also a hard constraint, and it points the same way: `tests/test_copy.py`
closes `admin_copy` with a `declared == asserted` set comparison, and PRD-006
Section 15 lists that file among the ones that must pass unmodified. A constant
added to `admin_copy.py` fails it. So the strings live here, outside both
surfaces, which is where a genuinely shared control's wording belongs anyway.

The module is deliberately not named `admin_*` and holds no component, so it
falls outside `tests/test_admin_palette.py`'s glob — correct, since it is not an
admin module.

**Both strings are accessible names, and nothing is drawn.** The control is a
single icon, so there is no visible text anywhere in it and the `aria-label` is
the *only* name it has — which is why these two carry more weight than a normal
label and why they name the action rather than the state. A blind reader gets
"Switch to dark"; a sighted one gets a moon. Both learn the same thing: what
happens if this is pressed.
"""

# The two directions, chosen by the ground currently on screen. Not one static
# "Theme": an icon-only control gives a screen reader nothing else to go on, and
# "Theme" would announce the topic while withholding the verb — the reader would
# know what the button is about and not what pressing it does.
#
# Plain verbs, sentence case, no filler — the register `copy.py` keeps throughout.
# Not "Paper" and "Slate": the rest of this design is happy to be idiosyncratic,
# but a control is where idiosyncrasy costs the reader something, and these are
# the words every other application on the machine uses.
GROUND_TO_DARK_LABEL = "Switch to dark"
GROUND_TO_LIGHT_LABEL = "Switch to light"
